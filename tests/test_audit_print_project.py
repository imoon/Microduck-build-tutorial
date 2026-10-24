"""Geometric fixtures and the checked-in print-project regression."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("audit_print_project", ROOT / "scripts/audit_print_project.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def model(resources, build="", unit="millimeter"):
    return (f'<model xmlns="{MODULE.CORE}" xmlns:p="{MODULE.PRODUCTION}" unit="{unit}">'
            f'<resources>{resources}</resources><build>{build}</build></model>')


class PrintProjectAuditTests(unittest.TestCase):
    def fixture(self, files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "fixture.3mf"
        with zipfile.ZipFile(path, "w") as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        return path

    def test_external_nested_transform_units_and_build_instances(self):
        # Child centimetres -> millimetres, parent rotation/translation, then
        # root build translation. A second instance intentionally has no plate.
        child = model('<object id="9"><mesh><vertices><vertex x="0" y="0" z="0"/>'
                      '<vertex x="1" y="2" z="3"/></vertices></mesh></object>', unit="centimeter")
        parent = model('<object id="2"><components><component p:path="/3D/child.model" '
                       'objectid="9" transform="0 1 0 -1 0 0 0 0 1 2 3 4"/></components></object>', unit="inch")
        root = model('<object id="1"><components><component p:path="/3D/parent.model" '
                     'objectid="2" transform="1 0 0 0 1 0 0 0 1 5 0 0"/></components></object>',
                     '<item objectid="1" transform="1 0 0 0 1 0 0 0 1 0 7 0"/>'
                     '<item objectid="1" printable="0"/>')
        config = '<config><object id="1"><metadata key="name" value="fixture"/>'
        config += '<metadata key="extruder" value="2"/><part id="9">'
        config += '<metadata key="extruder" value="3"/></part></object>'
        config += '<plate><metadata key="plater_id" value="1"/>'
        config += '<model_instance><metadata key="object_id" value="1"/>'
        config += '<metadata key="instance_id" value="0"/></model_instance></plate></config>'
        path = self.fixture({"3D/3dmodel.model": root, "3D/parent.model": parent,
                             "3D/child.model": child, "Metadata/model_settings.config": config})
        result = MODULE.audit(path)
        self.assertEqual(result["build_instances"][0]["bounds"], {
            "min_mm": [35.8, 83.2, 101.6], "max_mm": [55.8, 93.2, 131.6],
            "size_mm": [20.0, 10.0, 30.0]})
        self.assertEqual(result["build_instances"][0]["plate_ids"], [1])
        self.assertFalse(result["build_instances"][1]["printable"])
        self.assertEqual(result["unassigned_object_ids"], [1])
        self.assertEqual(result["objects"][0]["parts"][0]["effective_extruder"], "3")
        self.assertEqual(result, MODULE.audit(path))

    def test_cyclic_components_fail_clearly(self):
        root = model('<object id="1"><components><component objectid="1"/></components></object>')
        path = self.fixture({"3D/3dmodel.model": root})
        with self.assertRaisesRegex(ValueError, "Cyclic component"):
            MODULE.audit(path)

    def test_external_build_path_rejected_by_audit_and_export(self):
        root = model('<object id="1"><mesh><vertices><vertex x="0" y="0" z="0"/>'
                     '</vertices></mesh></object>',
                     '<item objectid="1" p:path="/3D/external.model"/>')
        path = self.fixture({"3D/3dmodel.model": root})
        with self.assertRaisesRegex(ValueError, "External build p:path"):
            MODULE.audit(path)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "External build p:path"):
                MODULE.export_fit_stls(path, directory, object_ids=(1,))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_mirrored_build_and_component_exports_rejected(self):
        mesh = ('<object id="1"><mesh><vertices><vertex x="0" y="0" z="0"/>'
                '<vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/>'
                '</vertices><triangles><triangle v1="0" v2="1" v3="2"/>'
                '</triangles></mesh></object>')
        reflection = '-1 0 0 0 1 0 0 0 1 0 0 0'
        fixtures = [
            model(mesh, f'<item objectid="1" transform="{reflection}"/>'),
            model(mesh + '<object id="2"><components>'
                  f'<component objectid="1" transform="{reflection}"/>'
                  '</components></object>', '<item objectid="2"/>'),
        ]
        for index, root in enumerate(fixtures):
            with self.subTest(transform_location=index):
                path = self.fixture({"3D/3dmodel.model": root})
                # Envelope auditing remains valid for mirrors; STL export refuses
                # them until winding-preserving reflection handling is implemented.
                MODULE.audit(path)
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(ValueError, "Mirrored transforms"):
                        MODULE.export_fit_stls(path, directory, object_ids=(index+1,))
                    self.assertEqual(list(Path(directory).iterdir()), [])

    def test_checked_in_project_inventory_and_bounds(self):
        path = ROOT / "microduck3D打印.3mf"
        result = MODULE.audit(path)
        self.assertEqual(result["counts"], {"objects": 67, "build_instances": 67,
                         "plates": 5, "assigned_instances": 65, "unassigned_instances": 2})
        self.assertEqual(result["unassigned_object_ids"], [55, 56])
        self.assertEqual([len(p["instances"]) for p in result["plates"]], [4, 5, 19, 34, 3])
        self.assertEqual(result["profile"]["printer_model"], "Bambu Lab P1S")
        objects = {o["object_id"]: o for o in result["objects"]}
        self.assertEqual(objects[57]["name"], "idle_horn.stl")
        self.assertEqual(objects[57]["local_bounds"]["size_mm"], [16.0, 16.0, 4.15])
        for actual, expected in zip(objects[59]["local_bounds"]["size_mm"], [6.8, 6.8, 4.6]):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertEqual(len(result["source"]["sha256"]), 64)
        # Canonical JSON serialization is stable and contains no non-finite floats.
        self.assertEqual(json.dumps(result, sort_keys=True, allow_nan=False),
                         json.dumps(MODULE.audit(path), sort_keys=True, allow_nan=False))

    def test_exported_fit_stls_retain_source_envelopes(self):
        path = ROOT / "microduck3D打印.3mf"
        result = MODULE.audit(path)
        instances = {i["object_id"]: i for i in result["build_instances"]}
        with tempfile.TemporaryDirectory() as directory:
            exports = MODULE.export_fit_stls(path, directory)
            self.assertEqual([f["object_id"] for f in exports["files"]], [57, 59, 53, 50])
            for entry in exports["files"]:
                data = (Path(directory) / entry["filename"]).read_bytes()
                count = struct.unpack_from("<I", data, 80)[0]
                self.assertGreater(count, 0)
                self.assertEqual(len(data), 84 + 50*count)
                points = []
                for index in range(count):
                    facet = struct.unpack_from("<12fH", data, 84+50*index)
                    points.extend((facet[3:6], facet[6:9], facet[9:12]))
                measured = MODULE.bounds(points)
                self.assertEqual(measured["min_mm"], [0.0, 0.0, 0.0])
                expected = instances[entry["object_id"]]["bounds"]["size_mm"]
                for actual, target in zip(measured["size_mm"], expected):
                    self.assertAlmostEqual(actual, target, places=5)
            with self.assertRaises(FileExistsError):
                MODULE.export_fit_stls(path, directory)


if __name__ == "__main__":
    unittest.main()
