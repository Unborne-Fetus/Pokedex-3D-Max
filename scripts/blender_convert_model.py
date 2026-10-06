import bpy
import sys
from pathlib import Path

argv = sys.argv
argv = argv[argv.index("--") + 1 :]
source = Path(argv[0]).resolve()
destination = Path(argv[1]).resolve()
destination.parent.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)

suffix = source.suffix.lower()
if suffix == ".fbx":
    bpy.ops.import_scene.fbx(filepath=str(source))
elif suffix == ".dae":
    bpy.ops.wm.collada_import(filepath=str(source))
elif suffix == ".obj":
    bpy.ops.wm.obj_import(filepath=str(source))
elif suffix in {".gltf", ".glb"}:
    bpy.ops.import_scene.gltf(filepath=str(source))
else:
    raise RuntimeError(f"Unsupported source format: {suffix}")

# Do not alter armatures, transforms, animation clips, materials, or textures here.
# The goal is faithful conversion first; model-specific normalization is metadata-driven.
bpy.ops.export_scene.gltf(
    filepath=str(destination),
    export_format="GLB",
    export_animations=True,
    export_skins=True,
    export_morph=True,
    export_materials="EXPORT",
    export_yup=True,
)

print(f"Exported {destination}")
