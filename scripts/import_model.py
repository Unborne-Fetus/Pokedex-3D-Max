#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_MODELS = ROOT / "web" / "models"
MANIFEST_JSON = WEB_MODELS / "manifest.json"
MANIFEST_JS = WEB_MODELS / "manifest.js"

SAFE = re.compile(r"[^a-z0-9_-]+")


def slug(value: str) -> str:
    value = value.strip().lower().replace(" ", "-")
    value = SAFE.sub("-", value).strip("-")
    return value or "regular"


def parse_glb(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("Not a valid GLB file")

    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2 or total > len(data):
        raise ValueError("Unsupported or damaged GLB")

    offset = 12
    doc = None
    while offset + 8 <= total:
        length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + length]
        offset += length
        if chunk_type == 0x4E4F534A:
            doc = json.loads(chunk.rstrip(b" \t\r\n\x00").decode("utf-8"))
            break

    if not isinstance(doc, dict):
        raise ValueError("GLB JSON chunk missing")
    return doc


def animation_duration(doc: dict, animation: dict) -> float:
    accessors = doc.get("accessors") or []
    duration = 0.0
    for sampler in animation.get("samplers") or []:
        index = sampler.get("input")
        if not isinstance(index, int) or index >= len(accessors):
            continue
        maximum = accessors[index].get("max")
        if isinstance(maximum, list) and maximum:
            try:
                duration = max(duration, float(maximum[0]))
            except (TypeError, ValueError):
                pass
    return duration


def model_bounds(doc: dict) -> dict | None:
    accessors = doc.get("accessors") or []
    meshes = doc.get("meshes") or []
    indices: set[int] = set()

    for mesh in meshes:
        for primitive in mesh.get("primitives") or []:
            index = (primitive.get("attributes") or {}).get("POSITION")
            if isinstance(index, int):
                indices.add(index)

    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]

    for index in indices:
        if not (0 <= index < len(accessors)):
            continue
        accessor = accessors[index]
        amin = accessor.get("min")
        amax = accessor.get("max")
        if not (
            isinstance(amin, list)
            and isinstance(amax, list)
            and len(amin) >= 3
            and len(amax) >= 3
        ):
            continue
        for axis in range(3):
            mins[axis] = min(mins[axis], float(amin[axis]))
            maxs[axis] = max(maxs[axis], float(amax[axis]))

    if not all(math.isfinite(v) for v in mins + maxs):
        return None

    center = [(mins[i] + maxs[i]) / 2 for i in range(3)]
    size = [maxs[i] - mins[i] for i in range(3)]
    radius = math.sqrt(sum(v * v for v in size)) / 2
    return {
        "min": mins,
        "max": maxs,
        "center": center,
        "size": size,
        "radius": radius,
    }


def pick_idle(animation_names: list[str]) -> str | None:
    patterns = [
        re.compile(r"(^|[|_])a?idle($|[|_])", re.I),
        re.compile(r"wait|stand|breath", re.I),
        re.compile(r"fight[_-]?b", re.I),
    ]
    for pattern in patterns:
        for name in animation_names:
            if pattern.search(name):
                return name
    return animation_names[0] if animation_names else None


def validate(doc: dict) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []

    if not doc.get("meshes"):
        errors.append("No meshes found")

    required = set(doc.get("extensionsRequired") or [])
    browser_safe_required = {
        "KHR_draco_mesh_compression",
        "EXT_texture_webp",
        "KHR_materials_unlit",
        "KHR_texture_transform",
    }
    unsupported = sorted(required - browser_safe_required)
    if unsupported:
        warnings.append("Required GLTF extensions need review: " + ", ".join(unsupported))

    if doc.get("skins") and not doc.get("animations"):
        warnings.append("Skinned model has no animations; it may display in bind/T-pose")

    for material in doc.get("materials") or []:
        if material.get("alphaMode") == "BLEND" and not material.get("doubleSided", False):
            warnings.append("Transparent single-sided material may vanish at some angles")
            break

    bounds = model_bounds(doc)
    if bounds:
        biggest = max(bounds["size"])
        smallest = min(v for v in bounds["size"] if v > 0) if any(v > 0 for v in bounds["size"]) else 0
        if smallest and biggest / smallest > 40:
            warnings.append("Extreme model proportions; camera framing should be reviewed")

    return warnings, errors


def find_blender(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    return shutil.which("blender")


def convert_with_blender(source: Path, destination: Path, blender: str) -> None:
    helper = ROOT / "scripts" / "blender_convert_model.py"
    cmd = [
        blender,
        "--background",
        "--python",
        str(helper),
        "--",
        str(source),
        str(destination),
    ]
    print("Running:", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode:
        raise RuntimeError(f"Blender conversion failed with code {result.returncode}")


def load_manifest() -> list[dict]:
    if MANIFEST_JSON.is_file():
        try:
            value = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
            if isinstance(value, list):
                return value
        except Exception:
            pass
    return []


def save_manifest(entries: list[dict]) -> None:
    WEB_MODELS.mkdir(parents=True, exist_ok=True)
    entries.sort(key=lambda x: (x["dex"], x["form"]))
    MANIFEST_JSON.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    MANIFEST_JS.write_text(
        "window.POKEDEX3D_LOCAL_MODELS = " + json.dumps(entries, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a clean model into Pokedex 3D Max")
    parser.add_argument("source", type=Path)
    parser.add_argument("--dex", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--form", default="regular")
    parser.add_argument("--blender", default=None)
    parser.add_argument("--force", action="store_true", help="overwrite an already imported valid GLB")
    parser.add_argument("--idle", default=None, help="verified base idle animation name")
    parser.add_argument(
        "--idle-break",
        action="append",
        default=[],
        help="verified idle break animation; repeat for multiple clips",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Source model does not exist: {source}")

    form = slug(args.form)
    target_dir = WEB_MODELS / f"{args.dex:04d}"
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / f"{form}.glb"

    suffix = source.suffix.lower()
    reuse_existing = False
    if destination.is_file() and not args.force:
        try:
            parse_glb(destination)
            reuse_existing = True
        except Exception:
            reuse_existing = False

    if reuse_existing:
        print(f"Already imported; reusing {destination.relative_to(ROOT)}")
    elif suffix == ".glb":
        shutil.copy2(source, destination)
    else:
        blender = find_blender(args.blender)
        if not blender:
            raise SystemExit(
                f"{suffix or 'This format'} requires Blender. Install Blender or pass --blender PATH."
            )
        convert_with_blender(source, destination, blender)

    doc = parse_glb(destination)
    warnings, errors = validate(doc)
    animations = [
        {
            "name": animation.get("name") or f"animation_{index}",
            "duration": round(animation_duration(doc, animation), 4),
        }
        for index, animation in enumerate(doc.get("animations") or [])
    ]
    names = [item["name"] for item in animations]
    bounds = model_bounds(doc)

    idle = args.idle or pick_idle(names)
    verified_breaks = [name for name in args.idle_break if name in names]

    entry = {
        "dex": args.dex,
        "name": args.name,
        "form": form,
        "url": f"web/models/{args.dex:04d}/{form}.glb",
        "source": source.name,
        "animations": animations,
        "idleAnimation": idle,
        "idleBreaks": verified_breaks,
        "bounds": bounds,
        "warnings": warnings,
        "valid": not errors,
        "errors": errors,
    }

    entries = [
        item
        for item in load_manifest()
        if not (item.get("dex") == args.dex and item.get("form") == form)
    ]
    entries.append(entry)
    save_manifest(entries)

    print()
    print(f"Imported #{args.dex:04d} {args.name} [{form}]")
    print(f"  Output: {destination.relative_to(ROOT)}")
    print(f"  Animations: {len(animations)}")
    print(f"  Base idle: {idle or 'none'}")
    print(f"  Verified idle breaks: {', '.join(verified_breaks) or 'none'}")
    print(f"  Validation: {'PASS' if not errors else 'FAIL'}")
    for warning in warnings:
        print(f"  WARNING: {warning}")
    for error in errors:
        print(f"  ERROR: {error}")

    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
