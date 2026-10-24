#!/usr/bin/env python3
"""Read a Bambu 3MF project and emit a deterministic geometric inventory.

Uses only the standard library. Bounds are vertex envelopes, not a slice,
mechanical fit assessment, or proof that a part can be manufactured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import struct
import xml.etree.ElementTree as ET
import zipfile


CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PRODUCTION = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
NS = {"c": CORE}
UNIT_MM = {
    "micron": 0.001, "millimeter": 1.0, "centimeter": 10.0,
    "inch": 25.4, "foot": 304.8, "meter": 1000.0,
}
IDENTITY = (1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.)
PROFILE_KEYS = (
    "printer_model", "printer_variant", "printer_settings_id",
    "print_settings_id", "default_print_profile", "nozzle_diameter",
    "layer_height", "wall_loops", "sparse_infill_density",
    "filament_type", "filament_settings_id", "filament_colour",
    "enable_support", "support_type", "support_filament",
    "support_interface_filament",
)
FIT_OBJECTS = (57, 59, 53, 50)


def metadata(element: ET.Element) -> dict[str, str]:
    return {
        item.attrib["key"]: item.attrib["value"]
        for item in element.findall("metadata")
        if "key" in item.attrib and "value" in item.attrib
    }


def transform(points, raw: str | None, unit_mm: float):
    """Apply a 3MF row-vector affine transform to points already in mm."""
    values = tuple(map(float, raw.split())) if raw else IDENTITY
    if len(values) != 12 or not all(math.isfinite(v) for v in values):
        raise ValueError("A 3MF transform must contain 12 finite numbers")
    a = values
    return tuple(
        (
            a[0]*x + a[3]*y + a[6]*z + a[9]*unit_mm,
            a[1]*x + a[4]*y + a[7]*z + a[10]*unit_mm,
            a[2]*x + a[5]*y + a[8]*z + a[11]*unit_mm,
        )
        for x, y, z in points
    )


def bounds(points):
    if not points:
        return None
    low = [min(p[axis] for p in points) for axis in range(3)]
    high = [max(p[axis] for p in points) for axis in range(3)]
    def rounded(values):
        return [0.0 if abs(v) < 0.0000005 else round(v, 6) for v in values]
    return {"min_mm": rounded(low), "max_mm": rounded(high),
            "size_mm": rounded([b-a for a, b in zip(low, high)])}


def archive_path(raw: str) -> str:
    path = PurePosixPath(raw.lstrip("/"))
    if ".." in path.parts or "\\" in raw:
        raise ValueError(f"Unsafe package path: {raw!r}")
    return str(path)


def reject_external_build_path(item: ET.Element) -> None:
    if f"{{{PRODUCTION}}}path" in item.attrib:
        raise ValueError("External build p:path references are not supported")


def reject_mirrored_export_transform(raw: str | None) -> None:
    values = tuple(map(float, raw.split())) if raw else IDENTITY
    if len(values) != 12 or not all(math.isfinite(v) for v in values):
        raise ValueError("A 3MF transform must contain 12 finite numbers")
    a = values
    determinant = (a[0]*(a[4]*a[8]-a[7]*a[5])
                   - a[3]*(a[1]*a[8]-a[7]*a[2])
                   + a[6]*(a[1]*a[5]-a[4]*a[2]))
    if determinant < 0:
        raise ValueError("Mirrored transforms are not supported by STL export")


class Project:
    def __init__(self, archive: zipfile.ZipFile):
        self.archive = archive
        self.models = {}
        self.cache = {}
        self.triangle_cache = {}

    def model(self, path):
        if path not in self.models:
            root = ET.fromstring(self.archive.read(path))
            unit = root.attrib.get("unit", "millimeter")
            if unit not in UNIT_MM:
                raise ValueError(f"Unsupported 3MF unit {unit!r} in {path}")
            resources = {o.attrib["id"]: o
                         for o in root.findall("c:resources/c:object", NS)}
            self.models[path] = root, UNIT_MM[unit], resources
        return self.models[path]

    def vertices(self, path, object_id, active=()):
        key = path, object_id
        if key in active:
            raise ValueError(f"Cyclic component reference: {path} object {object_id}")
        if key in self.cache:
            return self.cache[key]
        _, scale, resources = self.model(path)
        if object_id not in resources:
            raise ValueError(f"Missing object {object_id} in {path}")
        obj = resources[object_id]
        points = []
        for vertex in obj.findall("c:mesh/c:vertices/c:vertex", NS):
            point = tuple(float(vertex.attrib[k])*scale for k in ("x", "y", "z"))
            if not all(math.isfinite(v) for v in point):
                raise ValueError("Mesh contains a non-finite vertex")
            points.append(point)
        for component in obj.findall("c:components/c:component", NS):
            raw_path = component.attrib.get(f"{{{PRODUCTION}}}path")
            # Production-extension paths are package-root references.
            child_path = archive_path(raw_path) if raw_path else path
            child_points = self.vertices(child_path, component.attrib["objectid"],
                                         active + (key,))
            points.extend(transform(child_points, component.attrib.get("transform"), scale))
        self.cache[key] = tuple(points)
        return self.cache[key]

    def triangles(self, path, object_id, active=()):
        key = path, object_id
        if key in active:
            raise ValueError(f"Cyclic component reference: {path} object {object_id}")
        if key in self.triangle_cache:
            return self.triangle_cache[key]
        _, scale, resources = self.model(path)
        obj = resources[object_id]
        vertices = [tuple(float(v.attrib[k])*scale for k in ("x", "y", "z"))
                    for v in obj.findall("c:mesh/c:vertices/c:vertex", NS)]
        triangles = [tuple(vertices[int(t.attrib[k])] for k in ("v1", "v2", "v3"))
                     for t in obj.findall("c:mesh/c:triangles/c:triangle", NS)]
        for component in obj.findall("c:components/c:component", NS):
            raw_path = component.attrib.get(f"{{{PRODUCTION}}}path")
            child_path = archive_path(raw_path) if raw_path else path
            children = self.triangles(child_path, component.attrib["objectid"], active + (key,))
            reject_mirrored_export_transform(component.attrib.get("transform"))
            triangles.extend(transform(t, component.attrib.get("transform"), scale) for t in children)
        self.triangle_cache[key] = tuple(triangles)
        return self.triangle_cache[key]


def export_fit_stls(path, directory, object_ids=FIT_OBJECTS):
    """Export selected first build instances; keep orientation/scale, shift to origin.

    Source geometry and its existing licensing are inherited unchanged. Exporting
    creates no new geometry licence grant. Existing output files are never replaced.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    exported = []
    with zipfile.ZipFile(path) as archive:
        project = Project(archive)
        main_path = "3D/3dmodel.model"
        root, scale, _ = project.model(main_path)
        first_instances = {}
        for item in root.findall("c:build/c:item", NS):
            reject_external_build_path(item)
            first_instances.setdefault(int(item.attrib["objectid"]), item)
        # Prepare everything before writing, including overwrite checks.
        prepared = []
        for object_id in object_ids:
            item = first_instances[object_id]
            reject_mirrored_export_transform(item.attrib.get("transform"))
            triangles = project.triangles(main_path, str(object_id))
            triangles = [transform(t, item.attrib.get("transform"), scale) for t in triangles]
            if not triangles:
                raise ValueError(f"Object {object_id} has no triangles")
            minimum = [min(v[axis] for t in triangles for v in t) for axis in range(3)]
            triangles = [tuple(tuple(v[axis]-minimum[axis] for axis in range(3)) for v in t)
                         for t in triangles]
            filename = f"fit-object-{object_id}.stl"
            output = directory / filename
            if output.exists():
                raise FileExistsError(f"Refusing to replace {output}")
            prepared.append((object_id, filename, output, triangles))
        for object_id, filename, output, triangles in prepared:
            header = f"3MF object {object_id}; inherited source geometry; no new license grant".encode("ascii")
            content = bytearray(header[:80].ljust(80, b" "))
            content.extend(struct.pack("<I", len(triangles)))
            for a, b, c in triangles:
                u = tuple(y-x for x, y in zip(a, b))
                v = tuple(y-x for x, y in zip(a, c))
                normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                length = math.sqrt(sum(x*x for x in normal))
                normal = tuple(x/length for x in normal) if length else (0., 0., 0.)
                content.extend(struct.pack("<12fH", *normal, *a, *b, *c, 0))
            with output.open("xb") as stream:
                stream.write(content)
            exported.append({"object_id": object_id, "filename": filename,
                             "triangle_count": len(triangles),
                             "sha256": hashlib.sha256(content).hexdigest(),
                             "bounds": bounds([v for t in triangles for v in t])})
    return {"geometry_provenance": "Inherited source 3MF geometry; no new license grant; no resizing or fit validation.",
            "coordinate_change": "Source build orientation retained; bounding-box minimum translated to zero in millimeters.",
            "files": exported}


def audit(path: str | Path) -> dict:
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        project = Project(archive)
        main_path = "3D/3dmodel.model"
        root, scale, resources = project.model(main_path)
        config = (ET.fromstring(archive.read("Metadata/model_settings.config"))
                  if "Metadata/model_settings.config" in archive.namelist()
                  else ET.Element("config"))
        settings = (json.loads(archive.read("Metadata/project_settings.config"))
                    if "Metadata/project_settings.config" in archive.namelist() else {})
        configs = {o.attrib["id"]: o for o in config.findall("object")}
        plates = []
        memberships = {}
        for plate in config.findall("plate"):
            info = metadata(plate)
            plate_id = int(info["plater_id"])
            members = []
            for instance in plate.findall("model_instance"):
                values = metadata(instance)
                key = (int(values["object_id"]), int(values.get("instance_id", "0")))
                memberships.setdefault(key, []).append(plate_id)
                members.append({"object_id": key[0], "instance_id": key[1]})
            plates.append({"plate_id": plate_id, "name": info.get("plater_name", ""),
                           "instances": sorted(members, key=lambda x: (x["object_id"], x["instance_id"]))})

        objects = []
        for object_id in sorted(resources, key=int):
            cfg = configs.get(object_id, ET.Element("object"))
            info = metadata(cfg)
            mesh = project.vertices(main_path, object_id)
            parts = []
            for part in cfg.findall("part"):
                part_info = metadata(part)
                parts.append({"part_id": int(part.attrib["id"]),
                              "name": part_info.get("name"),
                              "source_file": part_info.get("source_file"),
                              "extruder": part_info.get("extruder"),
                              "effective_extruder": part_info.get("extruder", info.get("extruder", "1"))})
            objects.append({"object_id": int(object_id),
                            "name": info.get("name", resources[object_id].attrib.get("name")),
                            "extruder": info.get("extruder"),
                            "parts": sorted(parts, key=lambda x: x["part_id"]),
                            "vertex_count": len(mesh), "local_bounds": bounds(mesh)})

        instances = []
        counts = {}
        for item in root.findall("c:build/c:item", NS):
            reject_external_build_path(item)
            object_id = item.attrib["objectid"]
            instance_id = counts.get(object_id, 0)
            counts[object_id] = instance_id + 1
            points = project.vertices(main_path, object_id)
            points = transform(points, item.attrib.get("transform"), scale)
            instances.append({"object_id": int(object_id), "instance_id": instance_id,
                              "printable": item.attrib.get("printable", "1") != "0",
                              "plate_ids": sorted(memberships.get((int(object_id), instance_id), [])),
                              "bounds": bounds(points)})
        instances.sort(key=lambda x: (x["object_id"], x["instance_id"]))
        unassigned = [i for i in instances if not i["plate_ids"]]
        return {
            "schema_version": 1,
            "source": {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "size_bytes": path.stat().st_size, "unit": root.attrib.get("unit", "millimeter")},
            "limitations": ["Vertex bounds do not establish slicer acceptance, fit, tolerances, or strength.",
                            "Plate membership and filament assignments are source metadata, not validated print instructions."],
            "profile": {key: settings[key] for key in PROFILE_KEYS if key in settings},
            "counts": {"objects": len(objects), "build_instances": len(instances), "plates": len(plates),
                       "assigned_instances": len(instances)-len(unassigned), "unassigned_instances": len(unassigned)},
            "plates": sorted(plates, key=lambda x: x["plate_id"]),
            "objects": objects, "build_instances": instances,
            "unassigned_object_ids": sorted({i["object_id"] for i in unassigned}),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[1] / "microduck3D打印.3mf")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout")
    parser.add_argument("--export-fit-stls", type=Path, metavar="DIRECTORY",
                        help="Export source objects 57,59,53,50 as binary STL; no existing files replaced")
    args = parser.parse_args()
    if args.output and args.output.resolve() == args.project.resolve():
        parser.error("Output must not overwrite the source project")
    try:
        result = audit(args.project)
        if args.export_fit_stls:
            result["fit_exports"] = export_fit_stls(args.project, args.export_fit_stls)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
