# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import time
import numpy as np
import os
import sys
from pathlib import Path

from constants import MOTOR_TO_ID, NEUTRAL_POSE, KP_DEFAULT
from robot_controller import RobotController
from scheduler import Scheduler
from input.input_source import InputSource
from input.keyboard_input import KeyboardInputSource
from moves.walk import WalkMove

PID_FILE = Path("/tmp/microduck_scheduler.pid")


def _another_session_running() -> bool:
    """True if a live control loop already owns the PID file (e.g. launched by the
    gamepad daemon). Avoids two instances fighting over the motor bus."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="ascii").strip())
        os.kill(pid, 0)
    except (ValueError, OSError):
        return False
    return True

# Which moves can be toggled from the gamepad / keyboard.
MOVE_KEYS = {"v": "walk"}
GAMEPAD_BUTTON_MOVES = {"A": "walk"}


def build_input_source() -> InputSource:
    """Use the gamepad when one is connected, otherwise fall back to the keyboard.

    Override with MICRODUCK_INPUT=keyboard|gamepad.
    """
    requested = os.environ.get("MICRODUCK_INPUT", "auto").lower()

    if requested in ("auto", "gamepad"):
        from input.gamepad_input import GamepadInputSource, find_gamepad_path

        if find_gamepad_path() is not None:
            return GamepadInputSource(button_moves=GAMEPAD_BUTTON_MOVES)
        if requested == "gamepad":
            raise RuntimeError("MICRODUCK_INPUT=gamepad but no gamepad was found.")
        print("No gamepad detected; using keyboard input.")

    return KeyboardInputSource(move_keys=MOVE_KEYS)


def ramp_to_neutral(controller: RobotController, duration_s: float = 2.0) -> None:
    """Ramp all motors smoothly to neutral position before starting the control loop."""
    motor_ids = list(MOTOR_TO_ID.values())
    initial_positions = np.array(controller.sync_read_present_position(motor_ids))
    target_neutral = np.array([NEUTRAL_POSE[name] for name in MOTOR_TO_ID])

    print("Ramping all motors to neutral position...")
    start_time = time.perf_counter()
    elapsed_time = 0.0

    while elapsed_time < duration_s:
        elapsed_time = time.perf_counter() - start_time
        progress = min(elapsed_time / duration_s, 1.0)
        target_positions = initial_positions + progress * (target_neutral - initial_positions)
        controller.sync_write_goal_position(motor_ids, target_positions.flatten().tolist())

    controller.sync_write_goal_position(motor_ids, target_neutral.tolist())
    print("All motors reached neutral position.")


def main() -> None:
    if _another_session_running():
        print("A control loop is already running (see the PID file); aborting.")
        return

    PID_FILE.write_text(f"{os.getpid()}\n", encoding="ascii")

    controller = None
    input_source = None
    scheduler = None
    motor_ids = list(MOTOR_TO_ID.values())

    try:
        controller = RobotController()
        input_source = build_input_source()
        scheduler = Scheduler(
            frequency_hz=50.0,
            controller=controller,
            input_source=input_source,
            moves={
                "walk": WalkMove(controller=controller),
            },
        )

        for move in scheduler.registered_moves.values():
            move.preload()

        # Validate inputs and load the policy before arming any motor.
        controller.sync_write_status_return_level(motor_ids, [1] * len(motor_ids))
        controller.sync_write_kp(motor_ids, [KP_DEFAULT] * len(motor_ids))
        controller.sync_write_torque_enable(motor_ids, [True] * len(motor_ids))
        ramp_to_neutral(controller)

        # Flush stale UART bytes accumulated during preload
        for _ in range(10):
            try:
                controller.sync_read_present_position(motor_ids)
            except RuntimeError:
                pass

        scheduler.run()

    finally:
        primary_error = sys.exception()
        cleanup_errors = []
        if scheduler is not None:
            # The scheduler owns controller/input cleanup once constructed.
            actions = [("scheduler cleanup", scheduler.cleanup)]
        else:
            actions = []
            if controller is not None:
                actions.append(("torque off", lambda: controller.sync_write_torque_enable(
                    motor_ids, [False] * len(motor_ids))))
            if input_source is not None:
                actions.append(("input stop", input_source.stop))
            if controller is not None:
                actions.append(("controller close", controller.close))
        actions.append(("PID cleanup", lambda: PID_FILE.unlink(missing_ok=True)))
        for name, action in actions:
            try:
                action()
            except BaseException as exc:
                cleanup_errors.append((name, exc))
        if cleanup_errors:
            error = primary_error or cleanup_errors[0][1]
            for name, exc in cleanup_errors:
                error.add_note(f"{name} failed: {type(exc).__name__}: {exc}")
            if primary_error is None:
                raise error


if __name__ == "__main__":
    main()
