"""Hardware-free failure injection for startup and scheduler cleanup ownership.

These checks prove attempted API calls and ordering, not that a real bus delivers
torque-off or that cleanup can run after power loss/SIGKILL.
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "microduck/src"


def module(name, **attributes):
    result = types.ModuleType(name)
    result.__dict__.update(attributes)
    return result


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class MainCleanupTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.failure = None
        self.cleanup_failures = set()
        self.primary = RuntimeError("injected primary failure")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pid = Path(self.temp.name) / "control.pid"
        self.stop_flag = Path(self.temp.name) / "control.stop"
        owner = self

        def event(name):
            owner.events.append(name)
            if owner.failure == name:
                raise owner.primary
            if name in owner.cleanup_failures:
                raise OSError(f"injected {name} failure")

        class Controller:
            def __init__(self):
                event("controller init")

            def sync_write_torque_enable(self, ids, values):
                owner.assertEqual(ids, [1])
                event("torque on" if all(values) else "torque off")

            def sync_write_status_return_level(self, ids, values):
                event("status")

            def sync_write_kp(self, ids, values):
                event("gain")

            def sync_read_present_position(self, ids):
                return [0.0]

            def close(self):
                event("close")

        class Input:
            def start(self):
                event("input start")

            def stop(self):
                event("input stop")

        class Walk:
            def __init__(self, controller=None):
                event("policy init")

            def preload(self):
                event("preload")

        constants = dict(MOTOR_TO_ID={"joint": 1}, NEUTRAL_POSE={"joint": 0.0}, KP_DEFAULT=400)
        constants.update({name: 1 for name in (
            "BAM_MAX_CURRENT", "OVERCURRENT_CUTOFF_A", "OVERCURRENT_DEBOUNCE_TICKS",
            "OVERCURRENT_PROXY_DELAY_TICKS", "PROXY_KT", "PROXY_R", "PROXY_VIN",
            "PROXY_ERROR_GAIN", "PROXY_MAX_PWM", "PROXY_KP")})
        stubs = {
            "numpy": module("numpy"),
            "constants": module("constants", **constants),
            "robot_controller": module("robot_controller", RobotController=Controller),
            "controller": module("controller", ControllerProtocol=object),
            "observer": module("observer", Observer=lambda controller: object(), Observation=object),
            "imu_reader": module("imu_reader", imu_quat_to_body=lambda value: value),
            "input": module("input", __path__=[]),
            "input.input_source": module("input.input_source", InputSource=object,
                                         UserInput=object, scale_velocity=lambda value: value),
            "input.keyboard_input": module("input.keyboard_input", KeyboardInputSource=Input),
            "moves": module("moves", __path__=[]),
            "moves.move": module("moves.move", MotorCommand=object, Move=object, MoveState=object),
            "moves.rotate_head": module("moves.rotate_head", RotateHeadMove=Walk),
            "moves.squat": module("moves.squat", SquatMove=Walk),
            "moves.walk": module("moves.walk", WalkMove=Walk),
        }
        self.modules = patch.dict(sys.modules, stubs)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.scheduler_module = load_source("scheduler", SRC / "scheduler.py")
        sys.modules["scheduler"] = self.scheduler_module
        self.main_module = load_source("microduck_main_cleanup_test", SRC / "main.py")
        self.main_module.PID_FILE = self.pid
        self.input = Input()
        self.controller_class = Controller
        self.event = event

        def build_input():
            event("input init")
            return self.input

        self.main_module.build_input_source = build_input
        self.main_module.ramp_to_neutral = lambda controller: event("ramp")
        original_scheduler = self.scheduler_module.Scheduler

        class StartupScheduler(original_scheduler):
            def __init__(self, **kwargs):
                kwargs["stop_flag_path"] = str(owner.stop_flag)
                super().__init__(**kwargs)

            def run(self):
                try:
                    event("run")
                finally:
                    self.cleanup()

        self.main_module.Scheduler = StartupScheduler
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def assert_cleanup(self, input_created=True):
        self.assertFalse(self.pid.exists())
        self.assertEqual(self.events.count("torque off"), 1)
        self.assertEqual(self.events.count("close"), 1)
        self.assertLess(self.events.index("torque off"), self.events.index("close"))
        if input_created:
            self.assertEqual(self.events.count("input stop"), 1)
            self.assertLess(self.events.index("torque off"), self.events.index("input stop"))

    def test_policy_and_input_failures_are_cleaned_before_any_arming(self):
        for failure in ("input init", "policy init", "preload"):
            with self.subTest(failure=failure):
                self.events.clear()
                self.failure = failure
                with self.assertRaises(RuntimeError) as caught:
                    self.main_module.main()
                self.assertIs(caught.exception, self.primary)
                self.assertNotIn("torque on", self.events)
                self.assert_cleanup(input_created=failure != "input init")

    def test_arming_ramp_and_run_failures_all_cleanup(self):
        for failure in ("status", "gain", "torque on", "ramp", "run"):
            with self.subTest(failure=failure):
                self.events.clear()
                self.failure = failure
                with self.assertRaises(RuntimeError) as caught:
                    self.main_module.main()
                self.assertIs(caught.exception, self.primary)
                self.assert_cleanup()

    def test_normal_return_has_one_cleanup_owner(self):
        self.main_module.main()
        self.assert_cleanup()
        self.assertLess(self.events.index("preload"), self.events.index("torque on"))
        self.assertLess(self.events.index("gain"), self.events.index("torque on"))

    def test_cleanup_failures_preserve_primary_and_attempt_every_action(self):
        self.failure = "preload"
        self.cleanup_failures = {"torque off", "input stop", "close"}
        self.stop_flag.touch()
        with self.assertRaises(RuntimeError) as caught:
            self.main_module.main()
        self.assertIs(caught.exception, self.primary)
        self.assert_cleanup()
        self.assertFalse(self.stop_flag.exists())
        self.assertEqual(len(caught.exception.__notes__), 3)

    def test_cleanup_failure_without_primary_is_reported_after_other_cleanup(self):
        self.cleanup_failures = {"torque off", "input stop"}
        with self.assertRaisesRegex(OSError, "torque off"):
            self.main_module.main()
        self.assert_cleanup()

    def test_controller_constructor_failure_still_removes_pid(self):
        self.failure = "controller init"
        with self.assertRaises(RuntimeError) as caught:
            self.main_module.main()
        self.assertIs(caught.exception, self.primary)
        self.assertFalse(self.pid.exists())
        self.assertEqual(self.events, ["controller init"])

    def test_real_scheduler_input_start_failure_cleans_up(self):
        controller = self.controller_class()
        scheduler = self.scheduler_module.Scheduler(
            controller=controller, input_source=self.input,
            stop_flag_path=str(self.stop_flag), moves={})
        self.failure = "input start"
        with self.assertRaises(RuntimeError) as caught:
            scheduler.run()
        self.assertIs(caught.exception, self.primary)
        scheduler.cleanup()  # A caller can safely finalize after run already did.
        self.assert_cleanup()

    def test_real_scheduler_preserves_loop_failure_when_cleanup_also_fails(self):
        controller = self.controller_class()
        scheduler = self.scheduler_module.Scheduler(
            controller=controller, input_source=self.input,
            stop_flag_path=str(self.stop_flag), moves={})

        def fail_read(dt):
            raise ValueError("observer failed")

        scheduler.observer = types.SimpleNamespace(read_state=fail_read)
        self.cleanup_failures = {"torque off", "input stop", "close"}
        with self.assertRaisesRegex(ValueError, "observer failed") as caught:
            scheduler.run()
        self.assert_cleanup()
        self.assertEqual(len(caught.exception.__notes__), 3)


if __name__ == "__main__":
    unittest.main()
