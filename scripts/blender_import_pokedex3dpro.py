import bpy
import json
import sys
from pathlib import Path
from mathutils import Vector

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


def import_dae(path: Path):
    before_objects = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)

    bpy.ops.wm.collada_import(filepath=str(path))

    new_objects = [obj for obj in bpy.data.objects if obj not in before_objects]
    new_actions = [action for action in bpy.data.actions if action not in before_actions]
    return new_objects, new_actions


def action_duration(action):
    start, end = action.frame_range
    fps = bpy.context.scene.render.fps or 30
    return max(0.0, float(end - start) / float(fps))


def choose_action(actions):
    usable = [action for action in actions if action_duration(action) >= 0.2]
    if not usable:
        return None
    return max(usable, key=action_duration)


def mesh_bounds_world(objects):
    points = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))

    if not points:
        return {}

    mins = Vector((
        min(p.x for p in points),
        min(p.y for p in points),
        min(p.z for p in points),
    ))
    maxs = Vector((
        max(p.x for p in points),
        max(p.y for p in points),
        max(p.z for p in points),
    ))
    center = (mins + maxs) * 0.5
    size = maxs - mins

    return {
        "cameraTarget": [
            round(float(center.x), 5),
            round(float(center.z), 5),
            round(float(-center.y), 5),
        ],
        "boundsSize": [
            round(abs(float(size.x)), 5),
            round(abs(float(size.z)), 5),
            round(abs(float(size.y)), 5),
        ],
    }


def action_bone_names(action):
    names = set()
    marker = 'pose.bones["'
    for curve in action.fcurves:
        path = curve.data_path
        start = path.find(marker)
        if start < 0:
            continue
        start += len(marker)
        end = path.find('"]', start)
        if end > start:
            names.add(path[start:end])
    return names


def best_armature(objects, action):
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    if not armatures:
        return None, 0.0

    animated = action_bone_names(action)
    if not animated:
        armature = max(armatures, key=lambda obj: len(obj.data.bones))
        return armature, 1.0

    ranked = []
    for armature in armatures:
        bones = {bone.name for bone in armature.data.bones}
        coverage = len(animated & bones) / max(1, len(animated))
        ranked.append((coverage, len(bones), armature))

    coverage, _count, armature = max(ranked, key=lambda item: (item[0], item[1]))
    return armature, coverage


def delete_objects(objects):
    for obj in objects:
        if obj and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)


def export_job(job):
    reset_scene()

    model_path = Path(job["modelDae"]).resolve()
    anim_path = Path(job["animDae"]).resolve()
    output = Path(job["output"]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    model_objects, _model_actions = import_dae(model_path)
    if not model_objects:
        raise RuntimeError("model.dae imported no objects")

    bounds = mesh_bounds_world(model_objects)

    anim_objects, anim_actions = import_dae(anim_path)
    authored = choose_action(anim_actions)
    if authored is None:
        raise RuntimeError("anim.dae contained no usable authored animation")

    armature, coverage = best_armature(model_objects, authored)
    if armature is None:
        raise RuntimeError("model.dae contained no armature")

    if coverage < 0.70:
        raise RuntimeError(
            f"animation/model bone coverage too low ({coverage:.1%})"
        )

    # The animation DAE generally imports its own skeleton. The action's
    # F-curves target bone names, so with matching official skeleton names the
    # action can be assigned directly to the textured model armature.
    imported_action_name = authored.name
    authored.name = "Pokedex3DPro_OfficialIdle"

    armature.animation_data_create()
    armature.animation_data.action = authored

    # Remove duplicate geometry/skeleton imported from anim.dae while keeping
    # its action datablock assigned to the actual textured model armature.
    delete_objects(anim_objects)

    scene = bpy.context.scene
    start, end = authored.frame_range
    scene.frame_start = int(start)
    scene.frame_end = max(int(end), int(start) + 1)
    scene.render.fps = 30
    scene.frame_set(scene.frame_start)

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

    return {
        "dex": job["dex"],
        "form": "regular",
        "url": "web/models/pokedex3dpro/%04d/regular.glb" % job["dex"],
        "source": "Pokédex 3D Pro",
        "sourceModel": model_path.name,
        "sourceAnimation": anim_path.name,
        "animations": [
            {
                "name": authored.name,
                "duration": round(action_duration(authored), 4),
            }
        ],
        "idleAnimation": authored.name,
        "idleBreaks": [],
        "officialAuthoredAnimation": True,
        "boneCoverage": round(float(coverage), 4),
        "originalActionName": imported_action_name,
        **bounds,
        "valid": output.is_file() and output.stat().st_size > 1000,
        "warnings": [],
    }


results = {}
if manifest_json.is_file():
    try:
        for item in json.loads(manifest_json.read_text(encoding="utf-8")):
            results[(item.get("dex"), item.get("form"))] = item
    except Exception:
        pass

for index, job in enumerate(jobs, 1):
    print(
        "[%d/%d] Importing official animation #%04d"
        % (index, len(jobs), job["dex"]),
        flush=True,
    )
    try:
        result = export_job(job)
    except Exception as exc:
        print("  FAILED:", exc, flush=True)
        result = {
            "dex": job["dex"],
            "form": "regular",
            "url": "web/models/pokedex3dpro/%04d/regular.glb" % job["dex"],
            "source": "Pokédex 3D Pro",
            "animations": [],
            "idleAnimation": None,
            "idleBreaks": [],
            "officialAuthoredAnimation": False,
            "valid": False,
            "warnings": [str(exc)],
        }

    results[(job["dex"], "regular")] = result

for job in manifest_jobs:
    key = (job["dex"], "regular")
    if key not in results:
        output = Path(job["output"])
        results[key] = {
            "dex": job["dex"],
            "form": "regular",
            "url": "web/models/pokedex3dpro/%04d/regular.glb" % job["dex"],
            "source": "Pokédex 3D Pro",
            "animations": [],
            "idleAnimation": None,
            "idleBreaks": [],
            "officialAuthoredAnimation": False,
            "valid": output.is_file() and output.stat().st_size > 1000,
            "warnings": [],
        }

manifest = sorted(
    results.values(),
    key=lambda item: (int(item["dex"]), str(item["form"])),
)

manifest_json.parent.mkdir(parents=True, exist_ok=True)
manifest_json.write_text(
    json.dumps(manifest, indent=2) + "\n",
    encoding="utf-8",
)
manifest_js.write_text(
    "window.POKEDEX3D_PRO_MODELS = " +
    json.dumps(
        [
            item
            for item in manifest
            if item.get("valid")
            and item.get("officialAuthoredAnimation")
            and item.get("idleAnimation")
        ],
        separators=(",", ":"),
    ) +
    ";\n",
    encoding="utf-8",
)

print("Wrote", manifest_json, flush=True)
print("Wrote", manifest_js, flush=True)
