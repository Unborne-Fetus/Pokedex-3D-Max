from __future__ import annotations

import importlib
import json
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
        result = getattr(bpy.ops, "import").gfmdl(filepath=str(source))
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
            result = bpy.ops.import_scene.gfbanm(filepath=str(source))
            if "FINISHED" in result:
                imported += 1
                action = armature.animation_data.action if armature.animation_data else None
                if action and not action.name:
                    action.name = clip.get("name") or source.stem
            else:
                print(f"Animation importer returned {result} for {source.name}", flush=True)
        except Exception:
            print(f"Animation import failed for {source.name}", flush=True)
            traceback.print_exc()

    if imported:
        print(f"Imported {imported}/{len(clips)} animation clip(s).", flush=True)
    return imported


def export_glb(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(destination),
        export_format="GLB",
        export_animations=True,
        export_skins=True,
        export_morph=True,
        export_materials="EXPORT",
        export_yup=True,
    )


for index, job in enumerate(jobs, start=1):
    source = Path(job["source"]).resolve()
    destination = Path(job["output"]).resolve()
    print(f"[{index}/{len(jobs)}] {source.name} -> {destination.name}", flush=True)
    try:
        clear_scene()
        import_model(source)
        import_animations(job)
        export_glb(destination)
    except Exception as exc:
        failures.append({"source": str(source), "error": str(exc)})
        traceback.print_exc()

if failures:
    failure_path = jobs_path.with_name("switch-model-failures.json")
    failure_path.write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    print(f"{len(failures)} conversions failed; details: {failure_path}")
    if len(failures) == len(jobs):
        raise SystemExit(2)
