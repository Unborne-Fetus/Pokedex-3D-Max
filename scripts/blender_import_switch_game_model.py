from __future__ import annotations

import importlib
import json
import struct
import sys
import traceback
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1 :]
jobs_path = Path(argv[0]).resolve()
addon_parent = Path(argv[1]).resolve()
addon_name = argv[2]
blender_deps = Path(argv[3]).resolve()

# Make setup-installed dependencies visible before the add-on registers.
# This avoids Blender's disabled "Online Access" package installer path.
sys.path.insert(0, str(blender_deps))
sys.path.insert(0, str(addon_parent))
try:
    import flatbuffers  # noqa: F401
except Exception as exc:
    raise RuntimeError(
        f"flatbuffers is unavailable in Blender; expected dependency cache at {blender_deps}: {exc}"
    ) from exc

addon = importlib.import_module(addon_name)
addon.register()

jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
failures = []


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        addon.register()
    except Exception:
        pass


def import_model(source: Path) -> None:
    suffix = source.suffix.lower()
    if suffix == ".trmdl":
        result = bpy.ops.import_scene.trmdl(filepath=str(source))
    elif suffix == ".gfbmdl":
        # The upstream GFBMDL add-on reads operator.directory/operator.files,
        # not filepath, when its loader runs. Supplying only filepath leaves
        # files empty and makes execute() return None, which Blender rejects.
        result = getattr(bpy.ops, "import").gfmdl(
            filepath=str(source),
            directory=str(source.parent) + "/",
            files=[{"name": source.name}],
        )
    else:
        raise RuntimeError(f"Unsupported Switch model format: {suffix}")
    if "FINISHED" not in result:
        raise RuntimeError(f"Importer returned {result}")



def active_armature():
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not armatures:
        return None
    armature = armatures[0]
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    return armature


def import_animations(job: dict) -> int:
    clips = job.get("animations") or []
    if not clips:
        return 0

    armature = active_armature()
    if armature is None:
        print("No armature found; animation clips skipped.", flush=True)
        return 0

    imported = 0
    for clip in clips:
        source = Path(clip["source"]).resolve()
        if not source.is_file():
            continue
        try:
            # The cached importer is patched by import_switch_game_assets.py to
            # push each successfully-created Action into NLA before returning.
            # Count operator success here; the exported GLB is verified below.
            result = bpy.ops.import_scene.gfbanm(filepath=str(source))
            if "FINISHED" in result:
                imported += 1
                print(f"Imported animation: {clip.get('name') or source.stem}", flush=True)
            else:
                print(f"Animation importer returned {result} for {source.name}", flush=True)
        except Exception:
            print(f"Animation import failed for {source.name}", flush=True)
            traceback.print_exc()

    if imported:
        print(f"Imported {imported}/{len(clips)} animation clip(s).", flush=True)
    return imported

def glb_animation_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        return 0
    _, version, total = struct.unpack_from("<III", data, 0)
    if version != 2 or total > len(data):
        return 0
    offset = 12
    while offset + 8 <= total:
        length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + length]
        offset += length
        if chunk_type == 0x4E4F534A:
            doc = json.loads(chunk.rstrip(b" \t\r\n\x00").decode("utf-8"))
            return len(doc.get("animations") or [])
    return 0


def export_glb(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "filepath": str(destination),
        "export_format": "GLB",
        "export_animations": True,
        "export_skins": True,
        "export_morph": True,
        "export_materials": "EXPORT",
        "export_yup": True,
    }

    # Blender changed animation-export flags across versions. Enable whichever
    # NLA-specific option this installed Blender actually supports.
    try:
        props = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
    except Exception:
        props = set()
    if "export_animation_mode" in props:
        kwargs["export_animation_mode"] = "NLA_TRACKS"
    if "export_nla_strips" in props:
        kwargs["export_nla_strips"] = True

    bpy.ops.export_scene.gltf(**kwargs)


for index, job in enumerate(jobs, start=1):
    source = Path(job["source"]).resolve()
    destination = Path(job["output"]).resolve()
    print(f"[{index}/{len(jobs)}] {source.name} -> {destination.name}", flush=True)
    try:
        clear_scene()
        import_model(source)
        imported_animations = import_animations(job)
        export_glb(destination)
        if imported_animations:
            embedded = glb_animation_count(destination)
            if embedded <= 0:
                raise RuntimeError(
                    f"Imported {imported_animations} animation clip(s), but exported GLB contains no animations"
                )
            print(f"Verified {embedded} embedded GLB animation(s).", flush=True)
    except Exception as exc:
        failures.append({"source": str(source), "error": str(exc)})
        traceback.print_exc()

if failures:
    failure_path = jobs_path.with_name("switch-model-failures.json")
    failure_path.write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    print(f"{len(failures)} conversions failed; details: {failure_path}")
    raise SystemExit(2)
