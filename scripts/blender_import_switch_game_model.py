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

sys.path.insert(0, str(addon_parent))
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
