import bpy
import json
import math
import sys
from pathlib import Path

argv = sys.argv
argv = argv[argv.index("--") + 1 :]
job_file = Path(argv[0]).resolve()
payload = json.loads(job_file.read_text(encoding="utf-8"))
jobs = payload["jobs"]
manifest_jobs = payload["manifestJobs"]
manifest_json = Path(payload["manifestJson"])
manifest_js = Path(payload["manifestJs"])


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def try_relink_textures(source_dir: Path):
    # FBX imports often retain image basenames but lose absolute paths.
    candidates = {
        p.name.lower(): p
        for p in source_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tga"}
    }

    for image in bpy.data.images:
        if not image.name:
            continue
        wanted = candidates.get(Path(image.name).name.lower())
        if wanted:
            image.filepath = str(wanted)

    # If a material has no image node, use the likely Body texture as a safe fallback.
    body = next((p for p in candidates.values() if "body" in p.name.lower()), None)
    if body is None:
        return

    for material in bpy.data.materials:
        material.use_nodes = True
        nodes = material.node_tree.nodes
        if any(node.type == "TEX_IMAGE" and node.image for node in nodes):
            continue

        principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not principled:
            continue

        image = bpy.data.images.load(str(body), check_existing=True)
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        material.node_tree.links.new(tex.outputs["Color"], principled.inputs["Base Color"])
        if "Alpha" in principled.inputs:
            material.node_tree.links.new(tex.outputs["Alpha"], principled.inputs["Alpha"])


def export_job(job):
    source = Path(job["fbx"]).resolve()
    output = Path(job["output"]).resolve()
    source_dir = Path(job["sourceDir"]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    reset_scene()
    bpy.ops.import_scene.fbx(
        filepath=str(source),
        use_anim=True,
        automatic_bone_orientation=False,
    )
    try_relink_textures(source_dir)

    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        export_animations=True,
        export_skins=True,
        export_morph=True,
        export_materials="EXPORT",
        export_yup=True,
        export_image_format="AUTO",
        export_texcoords=True,
        export_normals=True,
        export_tangents=True,
        export_apply=False,
    )

    animations = []
    for action in bpy.data.actions:
        start, end = action.frame_range
        fps = bpy.context.scene.render.fps or 30
        duration = max(0.0, float(end - start) / float(fps))
        animations.append({
            "name": action.name,
            "duration": round(duration, 4),
        })

    return {
        "dex": job["dex"],
        "form": job["form"],
        "url": "web/models/pokeminers/%04d/%s.glb" % (job["dex"], job["form"]),
        "source": "PokeMiners/pogo_assets",
        "sourceRig": Path(job["fbx"]).name,
        "animations": animations,
        "idleAnimation": animations[0]["name"] if animations else None,
        "idleBreaks": [],
        "valid": output.is_file() and output.stat().st_size > 1000,
        "warnings": [] if animations else ["No embedded animation actions found"],
    }


results = {}

# Keep prior successful output metadata for models skipped because they were already converted.
if manifest_json.is_file():
    try:
        for item in json.loads(manifest_json.read_text(encoding="utf-8")):
            results[(item.get("dex"), item.get("form"))] = item
    except Exception:
        pass

for index, job in enumerate(jobs, 1):
    print("[%d/%d] Converting #%04d %s" % (
        index, len(jobs), job["dex"], job["form"]
    ), flush=True)

    try:
        result = export_job(job)
    except Exception as exc:
        print("  FAILED:", exc, flush=True)
        result = {
            "dex": job["dex"],
            "form": job["form"],
            "url": "web/models/pokeminers/%04d/%s.glb" % (job["dex"], job["form"]),
            "source": "PokeMiners/pogo_assets",
            "sourceRig": Path(job["fbx"]).name,
            "animations": [],
            "idleAnimation": None,
            "idleBreaks": [],
            "valid": False,
            "warnings": [str(exc)],
        }

    results[(job["dex"], job["form"])] = result

# Add placeholders for source rigs not converted yet only if no prior record exists.
for job in manifest_jobs:
    key = (job["dex"], job["form"])
    if key not in results:
        output = Path(job["output"])
        results[key] = {
            "dex": job["dex"],
            "form": job["form"],
            "url": "web/models/pokeminers/%04d/%s.glb" % (job["dex"], job["form"]),
            "source": "PokeMiners/pogo_assets",
            "sourceRig": Path(job["fbx"]).name,
            "animations": [],
            "idleAnimation": None,
            "idleBreaks": [],
            "valid": output.is_file() and output.stat().st_size > 1000,
            "warnings": [],
        }

manifest = sorted(
    results.values(),
    key=lambda item: (item["dex"], item["form"]),
)
manifest_json.parent.mkdir(parents=True, exist_ok=True)
manifest_json.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
manifest_js.write_text(
    "window.POKEDEX3D_POKEMINERS_MODELS = " +
    json.dumps([item for item in manifest if item.get("valid")], separators=(",", ":")) +
    ";\n",
    encoding="utf-8",
)
print("Wrote", manifest_json, flush=True)
print("Wrote", manifest_js, flush=True)
