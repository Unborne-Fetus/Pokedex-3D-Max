import bpy
import json
import math
import re
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


def texture_candidates(source_dir: Path):
    return {
        p.name.lower(): p
        for p in source_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tga"}
    }


def normalized_words(value: str):
    return {
        word
        for word in re.split(r"[^a-z0-9]+", value.lower())
        if len(word) >= 3 and word not in {"mat", "material", "tex", "texture", "png"}
    }


def best_texture_for_material(material_name: str, candidates):
    mat_words = normalized_words(material_name)
    ranked = []

    for path in candidates.values():
        stem_words = normalized_words(path.stem)
        overlap = len(mat_words & stem_words)
        score = overlap * 20

        low = path.stem.lower()
        mat_low = material_name.lower()
        for token in ("body", "face", "eye", "mouth", "wing", "flame", "fire", "hair"):
            if token in mat_low and token in low:
                score += 50

        if score:
            ranked.append((score, path))

    if not ranked:
        return None

    ranked.sort(key=lambda item: (-item[0], item[1].name.lower()))
    return ranked[0][1]


def configure_alpha(material, image_path: Path):
    name = image_path.stem.lower()
    if not any(token in name for token in ("eye", "face", "mouth", "flame", "fire", "wing", "mask")):
        return

    try:
        material.surface_render_method = "DITHERED"
    except Exception:
        try:
            material.blend_method = "BLEND"
        except Exception:
            pass

    try:
        material.use_transparency_overlap = False
    except Exception:
        pass


def attach_image_to_principled(material, image_path: Path):
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if not principled:
        return False

    image = bpy.data.images.load(str(image_path), check_existing=True)
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.name = "Pokedex3DMax_AutoTexture"

    links.new(tex.outputs["Color"], principled.inputs["Base Color"])
    if "Alpha" in tex.outputs and "Alpha" in principled.inputs:
        links.new(tex.outputs["Alpha"], principled.inputs["Alpha"])

    configure_alpha(material, image_path)
    return True


def try_relink_textures(source_dir: Path):
    candidates = texture_candidates(source_dir)

    # First restore any image references that survived FBX import by basename.
    for image in bpy.data.images:
        if not image.name:
            continue
        wanted = candidates.get(Path(image.name).name.lower())
        if wanted:
            image.filepath = str(wanted)

    # Never paint every missing material with Body.png. That caused special
    # surfaces such as flames/eyes to receive the body texture.
    materials = list(bpy.data.materials)
    only_material = len(materials) == 1
    body = next((p for p in candidates.values() if "body" in p.stem.lower()), None)

    for material in materials:
        material.use_nodes = True
        nodes = material.node_tree.nodes

        existing = next(
            (node for node in nodes if node.type == "TEX_IMAGE" and node.image),
            None,
        )
        if existing:
            wanted = candidates.get(Path(existing.image.name).name.lower())
            if wanted:
                existing.image.filepath = str(wanted)
                configure_alpha(material, wanted)
            continue

        best = best_texture_for_material(material.name, candidates)
        if best is None and body is not None:
            # Body is a safe fallback only for an explicitly body-like material
            # or a one-material model.
            if only_material or "body" in material.name.lower():
                best = body

        if best is not None:
            attach_image_to_principled(material, best)


def mesh_bounds_world():
    points = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))

    if not points:
        return None

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

    # Blender is Z-up. glTF export_yup maps this to X, Y, -Z.
    gltf_center = [float(center.x), float(center.z), float(-center.y)]
    gltf_size = [abs(float(size.x)), abs(float(size.z)), abs(float(size.y))]

    return {
        "cameraTarget": [round(v, 5) for v in gltf_center],
        "boundsSize": [round(v, 5) for v in gltf_size],
    }


def action_duration(action):
    start, end = action.frame_range
    fps = bpy.context.scene.render.fps or 30
    return max(0.0, float(end - start) / float(fps))


def idle_score(name: str):
    value = (name or "").lower()
    score = 0

    if re.search(r"idle|wait|stand|breath|loop", value):
        score += 100
    if re.search(r"fight[_ -]?a|battle[_ -]?a", value):
        score += 80
    if re.search(r"default|base", value):
        score += 30

    if re.search(r"attack|move|damage|hit|faint|die|death|sleep|eat|jump|run|walk|cry|emote", value):
        score -= 100
    if re.search(r"fight[_ -]?[bc]|battle[_ -]?[bc]", value):
        score -= 20

    return score


def choose_idle(animations):
    usable = [a for a in animations if a["duration"] >= 0.2]
    if not usable:
        return None

    ranked = sorted(
        enumerate(usable),
        key=lambda pair: (-idle_score(pair[1]["name"]), pair[0]),
    )
    return ranked[0][1]["name"]


def choose_idle_breaks(animations, idle):
    preferred = []
    for animation in animations:
        name = animation["name"]
        low = name.lower()
        duration = animation["duration"]

        if name == idle or duration < 0.2 or duration > 12:
            continue

        if re.search(r"idle[_ -]?[bc]|wait[_ -]?[bc]|fight[_ -]?[bc]|battle[_ -]?[bc]|look|roar|special", low):
            preferred.append(name)

    return preferred[:4]



def scan_animations():
    animations = []
    for action in bpy.data.actions:
        animations.append({
            "name": action.name,
            "duration": round(action_duration(action), 4),
        })
    return animations


def is_upper_limb(pose_bone):
    name = pose_bone.name.lower()
    parent = pose_bone.parent.name.lower() if pose_bone.parent else ""

    if "shoulder" in name:
        return True
    if "upperarm" in name or "upper_arm" in name:
        return True
    if "wing" in name and "wing" not in parent:
        return True
    if (
        re.search(r"(^|[^a-z])(?:l|r)?arm(?:[0-9_]|$)", name)
        and not any(token in parent for token in ("shoulder", "arm", "wing"))
    ):
        return True
    return False


def relax_bind_pose(armature):
    changed = []

    for pose_bone in armature.pose.bones:
        if not is_upper_limb(pose_bone):
            continue

        rest = pose_bone.bone
        vector = rest.tail_local - rest.head_local
        length = vector.length
        if length < 1e-5:
            continue

        # Only touch limbs that are obviously sticking sideways. This avoids
        # rewriting already-natural quadruped legs or vertically held wings.
        horizontal_ratio = math.sqrt(vector.x * vector.x + vector.y * vector.y) / length
        if horizontal_ratio < 0.72:
            continue

        horizontal = Vector((vector.x, vector.y, 0.0))
        if horizontal.length < 1e-5:
            continue
        horizontal.normalize()

        # Keep a little of the original outward direction while dropping the
        # limb mostly downward. The child forearm/hand inherits this rotation.
        target = horizontal * 0.32 + Vector((0.0, 0.0, -0.95))
        target.normalize()

        armature_delta = vector.normalized().rotation_difference(target)
        rest_rotation = rest.matrix_local.to_quaternion()
        local_delta = (
            rest_rotation.inverted()
            @ armature_delta
            @ rest_rotation
        )

        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.rotation_quaternion = local_delta
        changed.append(pose_bone)

    return changed


def create_procedural_idle(bounds):
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not armatures:
        return None

    # Empty/zero-length FBX animation stacks are common in Pokemon GO rigs.
    # Remove them so the GLB does not advertise a useless clip.
    for action in list(bpy.data.actions):
        if action_duration(action) < 0.2:
            bpy.data.actions.remove(action)

    armature = max(armatures, key=lambda obj: len(obj.data.bones))
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)

    changed = relax_bind_pose(armature)

    action = bpy.data.actions.new("Pokedex3DMax_ProceduralIdle")
    armature.animation_data_create()
    armature.animation_data.action = action

    scene = bpy.context.scene
    scene.render.fps = 30
    scene.frame_start = 1
    scene.frame_end = 80

    # Lock the relaxed pose into the whole loop.
    for frame in (1, 40, 80):
        scene.frame_set(frame)
        for bone in changed:
            bone.keyframe_insert(
                data_path="rotation_quaternion",
                frame=frame,
                group=bone.name,
            )

    # A small whole-body rise/fall gives models without source animation a
    # visible idle without risking species-specific limb deformation.
    size = bounds.get("boundsSize", [1.0, 1.0, 1.0])
    height = max(float(size[1]) if len(size) > 1 else 1.0, 0.1)
    base_location = armature.location.copy()
    bob = min(max(height * 0.012, 0.003), 0.03)

    for frame, offset in ((1, 0.0), (20, bob * 0.45), (40, bob), (60, bob * 0.45), (80, 0.0)):
        scene.frame_set(frame)
        armature.location = base_location + Vector((0.0, 0.0, offset))
        armature.keyframe_insert(data_path="location", frame=frame)

    armature.location = base_location
    scene.frame_set(1)

    return {
        "name": action.name,
        "relaxedBones": [bone.name for bone in changed],
        "generated": True,
    }


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
        use_prepost_rot=True,
    )

    try_relink_textures(source_dir)
    bounds = mesh_bounds_world() or {}

    animations = scan_animations()
    idle = choose_idle(animations)
    procedural = None

    if idle is None:
        procedural = create_procedural_idle(bounds)
        animations = scan_animations()
        idle = choose_idle(animations)

    idle_breaks = choose_idle_breaks(animations, idle)

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

    warnings = []
    if not animations:
        warnings.append("No embedded animation actions found")
    elif not idle:
        warnings.append("No safe idle animation selected")

    return {
        "dex": job["dex"],
        "form": job["form"],
        "formCode": job.get("formCode"),
        "url": "web/models/pokeminers/%04d/%s.glb" % (job["dex"], job["form"]),
        "source": "PokeMiners/pogo_assets",
        "sourceRig": Path(job["fbx"]).name,
        "animations": animations,
        "idleAnimation": idle,
        "idleBreaks": idle_breaks,
        "proceduralIdle": bool(procedural),
        "relaxedBones": procedural["relaxedBones"] if procedural else [],
        **bounds,
        "valid": output.is_file() and output.stat().st_size > 1000,
        "warnings": warnings,
    }


results = {}

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
            "formCode": job.get("formCode"),
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

for job in manifest_jobs:
    key = (job["dex"], job["form"])
    if key not in results:
        output = Path(job["output"])
        results[key] = {
            "dex": job["dex"],
            "form": job["form"],
            "formCode": job.get("formCode"),
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
    json.dumps([
        item for item in manifest
        if item.get("valid") and item.get("idleAnimation")
    ], separators=(",", ":")) +
    ";\n",
    encoding="utf-8",
)
print("Wrote", manifest_json, flush=True)
print("Wrote", manifest_js, flush=True)
