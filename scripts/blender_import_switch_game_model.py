from __future__ import annotations

import importlib
import json
import os
import re
import struct
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Matrix

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
results = []
MIN_ANIMATION_MATCHED_TRACKS = 3
MIN_ANIMATION_MATCH_RATIO = 0.20


class AnimationCompatibilityError(RuntimeError):
    """Animation data parsed, but no candidate safely matches this model rig."""



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
    active = bpy.context.view_layer.objects.active
    if active is not None and active.type == "ARMATURE":
        armature = active
    else:
        armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
        if not armatures:
            return None
        # Importers can create helper armatures. The Pokémon rig is normally
        # the one with the largest pose-bone set.
        armature = max(armatures, key=lambda obj: len(obj.pose.bones))

    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    return armature


def clear_animation_state(armature) -> None:
    if armature.animation_data is None:
        armature.animation_data_create()
    animation_data = armature.animation_data
    animation_data.action = None
    for track in list(animation_data.nla_tracks):
        animation_data.nla_tracks.remove(track)


def reset_pose_to_rest(armature) -> None:
    """Clear evaluated pose transforms before exporting a static fallback."""
    for pose_bone in armature.pose.bones:
        pose_bone.matrix_basis = Matrix.Identity(4)
    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    bpy.context.view_layer.update()


def remove_new_actions(before_actions: set[int]) -> None:
    for action in list(bpy.data.actions):
        if action.as_pointer() in before_actions:
            continue
        try:
            bpy.data.actions.remove(action)
        except Exception:
            pass


def recover_imported_action(armature, before_actions: set[int], source: Path):
    if armature.animation_data is None:
        armature.animation_data_create()
    animation_data = armature.animation_data

    if animation_data.action is not None:
        return animation_data.action

    new_actions = [
        candidate
        for candidate in bpy.data.actions
        if candidate.as_pointer() not in before_actions
    ]
    if new_actions:
        exact = next(
            (candidate for candidate in new_actions if candidate.name == source.stem),
            None,
        )
        return exact or new_actions[-1]

    for track in reversed(list(animation_data.nla_tracks)):
        for strip in reversed(list(track.strips)):
            if strip.action is not None:
                return strip.action
    return None


def import_animations(job: dict) -> int:
    clips = job.get("animations") or []
    if not clips:
        return 0

    armature = active_armature()
    if armature is None:
        raise RuntimeError("Animation candidates exist, but imported model has no armature")

    errors: list[str] = []
    for clip in clips:
        source = Path(clip["source"]).resolve()
        if not source.is_file():
            errors.append(f"{source.name}: source file missing")
            continue

        clear_animation_state(armature)
        bpy.ops.object.select_all(action="DESELECT")
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        before_actions = {action.as_pointer() for action in bpy.data.actions}

        try:
            print(f"Trying animation: {source.name}", flush=True)
            result = bpy.ops.import_scene.gfbanm(
                filepath=str(source),
                set_scene_end=True,
                nla_import=False,
            )
            if "FINISHED" not in result:
                errors.append(f"{source.name}: importer returned {result}")
                remove_new_actions(before_actions)
                continue

            action = recover_imported_action(armature, before_actions, source)
            if action is None:
                errors.append(f"{source.name}: importer created no Action")
                remove_new_actions(before_actions)
                continue

            matched_tracks = int(action.get("pokedex3d_matched_tracks", 0) or 0)
            named_tracks = int(action.get("pokedex3d_named_tracks", 0) or 0)
            match_ratio = (
                float(action.get("pokedex3d_match_ratio", 0.0) or 0.0)
                if named_tracks
                else 0.0
            )
            if (
                matched_tracks < MIN_ANIMATION_MATCHED_TRACKS
                or match_ratio < MIN_ANIMATION_MATCH_RATIO
            ):
                errors.append(
                    f"{source.name}: rig compatibility too low "
                    f"({matched_tracks}/{named_tracks} tracks, {match_ratio:.1%})"
                )
                clear_animation_state(armature)
                remove_new_actions(before_actions)
                continue

            animation_data = armature.animation_data
            for track in list(animation_data.nla_tracks):
                animation_data.nla_tracks.remove(track)
            animation_data.action = action
            action.name = clip.get("name") or source.stem
            action.use_fake_user = True
            bpy.context.view_layer.update()

            frame_range = tuple(float(value) for value in action.frame_range)
            print(
                f"Using active animation: {action.name}; "
                f"rig match {matched_tracks}/{named_tracks} ({match_ratio:.1%}); "
                f"frames {frame_range}",
                flush=True,
            )
            return 1
        except AnimationCompatibilityError:
            raise
        except Exception:
            remove_new_actions(before_actions)
            raise

    bone_sample = ", ".join(bone.name for bone in list(armature.pose.bones)[:20])
    raise AnimationCompatibilityError(
        "No compatible animation clip could be imported for "
        f"{Path(job['source']).name}. Tried {len(clips)} clip(s). "
        f"Armature has {len(armature.pose.bones)} bones"
        + (f" (sample: {bone_sample})" if bone_sample else "")
        + ". "
        + " | ".join(errors)
    )


def _linked_base_color_image(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None

    tagged_name = str(material.get("pokedex3d_basecolor_image", "") or "")
    if tagged_name:
        tagged = bpy.data.images.get(tagged_name)
        if tagged is not None:
            return tagged

    tagged_path = str(material.get("pokedex3d_basecolor_path", "") or "")
    if tagged_path:
        tagged_abs = os.path.abspath(tagged_path)
        for image in bpy.data.images:
            image_path = str(getattr(image, "filepath", "") or "")
            if image_path and os.path.abspath(bpy.path.abspath(image_path)) == tagged_abs:
                return image

    # The upstream importer wires the real albedo image into the custom
    # PokemonShader Group socket named "Albedo". Prefer that exact semantic
    # link instead of guessing from filenames.
    for node in material.node_tree.nodes:
        if node.type != "TEX_IMAGE" or node.image is None:
            continue
        for output in node.outputs:
            for link in output.links:
                socket_name = str(getattr(link.to_socket, "name", "") or "").casefold()
                if socket_name in {"albedo", "base color", "basecolor"}:
                    return node.image

    # Conservative fallback for importer variants that lost the semantic link
    # but still loaded image nodes. Avoid obvious non-color maps.
    candidates = []
    rejected_tokens = (
        "normal", "nrm", "rough", "rgh", "metal", "mtl", "mask", "msk",
        "ao", "occlusion", "lym", "emission", "emi", "spec", "height",
    )
    for node in material.node_tree.nodes:
        if node.type != "TEX_IMAGE" or node.image is None:
            continue
        name = (str(node.image.name) + " " + os.path.basename(str(getattr(node.image, "filepath", "")))).casefold()
        tokens = re.split(r"[^a-z0-9]+", name)
        if any(token in tokens for token in rejected_tokens):
            continue
        candidates.append(node.image)
    return candidates[0] if candidates else None


def _material_base_color_factor(material):
    tagged = material.get("pokedex3d_basecolor_factor")
    if tagged is not None:
        try:
            values = tuple(float(value) for value in tagged)
            if len(values) >= 3:
                return (
                    max(0.0, min(1.0, values[0])),
                    max(0.0, min(1.0, values[1])),
                    max(0.0, min(1.0, values[2])),
                    max(0.0, min(1.0, values[3] if len(values) > 3 else 1.0)),
                )
        except Exception:
            pass

    if material.use_nodes and material.node_tree is not None:
        for node in material.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                socket = node.inputs.get("Base Color")
                if socket is not None:
                    try:
                        value = tuple(float(v) for v in socket.default_value)
                        if len(value) >= 4:
                            return value[:4]
                    except Exception:
                        pass

        for node in material.node_tree.nodes:
            if node.type != "GROUP":
                continue
            for socket_name in ("BaseColor", "Base Color", "Albedo"):
                socket = node.inputs.get(socket_name)
                if socket is None:
                    continue
                try:
                    value = tuple(float(v) for v in socket.default_value)
                    if len(value) >= 4:
                        return value[:4]
                except Exception:
                    pass

    return (0.8, 0.8, 0.8, 1.0)


def bake_switch_shader_colors(source: Path) -> None:
    """Bake the original Nintendo material graph into portable glTF albedo.

    Merely copying the imported *_alb image loses PokémonShader's per-layer
    colors and mask lookup. Cycles' color-only diffuse bake evaluates the
    original graph on the original UVs before it is replaced by PBR nodes.
    Never generate a substitute texture when baking is impossible.
    """
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("Cannot bake Switch colors: no mesh objects")
    for obj in meshes:
        if not getattr(obj.data, "uv_layers", None) or not obj.data.uv_layers.active:
            raise RuntimeError(
                f"Cannot bake original Switch shader: missing UVs on {obj.name}"
            )

    originals = {}
    targets = {}
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or mat in targets:
                continue
            base = _linked_base_color_image(mat)
            if base is None or not base.has_data:
                raise RuntimeError(
                    f"Cannot bake original Switch shader: missing source albedo on {mat.name}"
                )
            width = int(base.size[0])
            height = int(base.size[1])
            if width <= 0 or height <= 0:
                raise RuntimeError(f"Invalid original texture resolution on {mat.name}")
            # Preserve native texel detail when feasible; avoid enormous masks.
            scale = min(1.0, 2048.0 / max(width, height))
            width = max(1, int(width * scale))
            height = max(1, int(height * scale))
            image = bpy.data.images.new(
                f"POKEDEX3D_SHADER_BAKE_{len(targets)}",
                width=width, height=height, alpha=True,
            )
            mat.use_nodes = True
            node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            node.name = "POKEDEX3D_SHADER_BAKE_TARGET"
            node.image = image
            mat.node_tree.nodes.active = node
            targets[mat] = image
            originals[mat] = base

    if not targets:
        raise RuntimeError("Cannot bake Switch colors: no usable mesh materials")

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.margin = 2
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    print(
        f"Baking original layered Switch material colors for {len(targets)} material(s)...",
        flush=True,
    )
    result = bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"})
    if "FINISHED" not in result:
        raise RuntimeError(f"Switch color bake returned {result}")

    bake_dir = jobs_path.parent / "shader-baked" / source.stem
    bake_dir.mkdir(parents=True, exist_ok=True)
    from array import array
    for index, (mat, image) in enumerate(targets.items()):
        base = originals[mat]
        # Bake writes RGB. Preserve any original albedo transparency instead
        # of turning feathers, fur cutouts, and eyelashes into opaque polygons.
        if int(base.size[0]) == int(image.size[0]) and int(base.size[1]) == int(image.size[1]):
            count = int(image.size[0]) * int(image.size[1]) * 4
            original_pixels = array("f", [0.0]) * count
            baked_pixels = array("f", [0.0]) * count
            base.pixels.foreach_get(original_pixels)
            image.pixels.foreach_get(baked_pixels)
            for offset in range(3, count, 4):
                baked_pixels[offset] = original_pixels[offset]
            image.pixels.foreach_set(baked_pixels)
            image.update()

        image.alpha_mode = "CHANNEL_PACKED"
        image.filepath_raw = str(bake_dir / f"material-{index:03d}.png")
        image.file_format = "PNG"
        image.save()
        mat["pokedex3d_basecolor_image"] = image.name
        mat["pokedex3d_basecolor_path"] = image.filepath_raw
        mat["pokedex3d_shader_baked"] = True
        print(f"Switch shader baked: {mat.name} -> {image.filepath_raw}", flush=True)


def prepare_materials_for_gltf() -> tuple[int, int, list[dict]]:
    """Flatten imported Pokémon materials into glTF-compatible PBR nodes.

    Both the newer TRMDL importer and the legacy GFBMDL importer can build
    Blender graphs that do not serialize cleanly to glTF. Preserve the selected
    albedo image (or authored base-color factor) and replace the graph with a
    standard Principled BSDF before export.
    """
    total = 0
    textured = 0
    missing: list[dict] = []

    for material in bpy.data.materials:
        if material is None:
            continue
        users = [
            obj
            for obj in bpy.context.scene.objects
            if obj.type == "MESH"
            and any(slot.material == material for slot in obj.material_slots)
        ]
        if not users:
            continue

        total += 1
        image = _linked_base_color_image(material)
        # The bake already contains Nintendo's original shader tints/layers.
        # Applying the old base-color factor would multiply those colors twice.
        base_factor = (
            (1.0, 1.0, 1.0, 1.0)
            if material.get("pokedex3d_shader_baked")
            else _material_base_color_factor(material)
        )
        original_images = []
        original_albedo_links = []
        if material.use_nodes and material.node_tree is not None:
            for node in material.node_tree.nodes:
                if node.type == "TEX_IMAGE":
                    original_images.append(
                        str(node.image.name) if node.image is not None else "<unassigned>"
                    )
                    for output in node.outputs:
                        for link in output.links:
                            socket_name = str(getattr(link.to_socket, "name", "") or "")
                            if "albedo" in socket_name.casefold() or "base color" in socket_name.casefold():
                                original_albedo_links.append(socket_name)

        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()

        output = nodes.new("ShaderNodeOutputMaterial")
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        base_socket = principled.inputs.get("Base Color")
        alpha_socket = principled.inputs.get("Alpha")
        if base_socket is None:
            raise RuntimeError(
                f"Principled BSDF Base Color socket missing for {material.name}"
            )

        base_socket.default_value = base_factor
        if alpha_socket is not None:
            alpha_socket.default_value = base_factor[3]

        if image is not None:
            tex = nodes.new("ShaderNodeTexImage")
            tex.name = "POKEDEX3D_ALBEDO"
            tex.label = "Pokedex3D Albedo"
            tex.image = image
            tex.interpolation = "Linear"
            try:
                image.colorspace_settings.name = "sRGB"
            except Exception:
                pass

            links.new(tex.outputs["Color"], base_socket)
            if alpha_socket is not None and "Alpha" in tex.outputs:
                links.new(tex.outputs["Alpha"], alpha_socket)

        links.new(principled.outputs["BSDF"], output.inputs["Surface"])

        roughness = principled.inputs.get("Roughness")
        if roughness is not None:
            roughness.default_value = 0.65
        metallic = principled.inputs.get("Metallic")
        if metallic is not None:
            metallic.default_value = 0.0

        if image is not None:
            material["pokedex3d_gltf_basecolor"] = image.name
            textured += 1
            print(
                f"GLTF material flatten: {material.name} -> {image.name}",
                flush=True,
            )
        else:
            # Record the imported material graph before flattening, so it is
            # possible to diagnose exactly which original texture was absent.
            # This never substitutes a made-up material or relaxes validation.
            missing.append({
                "material": material.name,
                "authoredBaseColor": list(base_factor),
                "importerBaseColorImage": str(material.get("pokedex3d_basecolor_image", "") or ""),
                "importerBaseColorPath": str(material.get("pokedex3d_basecolor_path", "") or ""),
                "sourceImages": original_images,
                "sourceAlbedoLinks": original_albedo_links,
            })
            print(
                f"GLTF material flatten: {material.name} -> color {base_factor} "
                f"(source images: {original_images[:5]}; original albedo links: {original_albedo_links[:5]})",
                flush=True,
            )

    print(
        f"GLTF material flatten summary: {textured}/{total} mesh material(s) "
        "have standard base-color textures.",
        flush=True,
    )
    return total, textured, missing


def glb_base_color_texture_count(path: Path) -> int:
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
        if chunk_type != 0x4E4F534A:
            continue

        doc = json.loads(chunk.rstrip(b" \t\r\n\x00").decode("utf-8"))
        textures = doc.get("textures") or []
        count = 0
        for material in doc.get("materials") or []:
            if not isinstance(material, dict):
                continue
            pbr = material.get("pbrMetallicRoughness") or {}
            slot = pbr.get("baseColorTexture")
            if not isinstance(slot, dict):
                continue
            index = slot.get("index")
            if isinstance(index, int) and 0 <= index < len(textures):
                count += 1
        return count

    return 0


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
            return sum(
                1
                for animation in (doc.get("animations") or [])
                if isinstance(animation, dict)
                and bool(animation.get("channels"))
                and bool(animation.get("samplers"))
            )
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

    # Legacy Switch animation imports are most reliable as the armature's
    # active Action. Export that explicitly instead of NLA tracks; if this
    # Blender only supports scene baking, use SCENE as the fallback.
    try:
        props = bpy.ops.export_scene.gltf.get_rna_type().properties
        prop_names = set(props.keys())
    except Exception:
        props = None
        prop_names = set()

    if "export_animation_mode" in prop_names:
        enum_items = {
            item.identifier
            for item in props["export_animation_mode"].enum_items
        }
        if "ACTIVE_ACTIONS" in enum_items:
            kwargs["export_animation_mode"] = "ACTIVE_ACTIONS"
        elif "ACTIONS" in enum_items:
            kwargs["export_animation_mode"] = "ACTIONS"
        elif "SCENE" in enum_items:
            kwargs["export_animation_mode"] = "SCENE"

    if "export_nla_strips" in prop_names:
        kwargs["export_nla_strips"] = False

    bpy.ops.export_scene.gltf(**kwargs)


for index, job in enumerate(jobs, start=1):
    source = Path(job["source"]).resolve()
    destination = Path(job["output"]).resolve()
    temporary = destination.with_name(destination.stem + ".partial.glb")

    bake_enabled = bool(job.get("bakeSwitchShaders"))
    bake_directory = jobs_path.parent / "shader-baked" / source.stem

    job_texture_roots = [
        str(Path(path).resolve())
        for path in (job.get("textureRoots") or [])
        if Path(path).exists()
    ]
    if job_texture_roots:
        os.environ["POKEDEX3D_TEXTURE_ROOTS"] = os.pathsep.join(job_texture_roots)
    else:
        os.environ.pop("POKEDEX3D_TEXTURE_ROOTS", None)

    warning = job.get("textureRootWarning")
    if warning:
        print("Texture dependency warning: " + str(warning), flush=True)

    print(
        f"[{index}/{len(jobs)}] {source.name} -> {destination.name} "
        f"(texture roots: {len(job_texture_roots)})",
        flush=True,
    )

    missing_materials = []
    try:
        if temporary.exists():
            temporary.unlink()

        clear_scene()
        import_model(source)
        wants_animation = bool(job.get("animations"))
        imported_animations = 0
        animation_rejection = None

        if wants_animation:
            try:
                imported_animations = import_animations(job)
            except AnimationCompatibilityError as exc:
                animation_rejection = str(exc)
                armature = active_armature()
                if armature is not None:
                    clear_animation_state(armature)
                    reset_pose_to_rest(armature)
                print(
                    "Animation candidates rejected as rig-incompatible; "
                    "exporting a verified static model and keeping it staged. "
                    + animation_rejection,
                    flush=True,
                )

        if wants_animation and animation_rejection is None and imported_animations <= 0:
            raise RuntimeError("Animation candidates were selected but none were imported")

        if bake_enabled:
            bake_switch_shader_colors(source)

        # The upstream importer uses a custom PokemonShader node group. Flatten
        # it to standard PBR nodes before GLB export or Filament/model-viewer
        # will receive an untextured/white material.
        allow_broken_textures = os.environ.get("POKEDEX3D_ALLOW_BROKEN_TEXTURES") == "1"
        try:
            total_materials, textured_materials, missing_materials = prepare_materials_for_gltf()
        except Exception as error:
            if not allow_broken_textures:
                raise
            print(f"Keeping imported geometry with unfinished materials: {error}", flush=True)
            total_materials, textured_materials = 0, 0
        if not any(obj.type == "MESH" for obj in bpy.context.scene.objects):
            raise RuntimeError("Imported model contains no mesh geometry")
        if total_materials <= 0 and not allow_broken_textures:
            raise RuntimeError("Imported model contains no mesh materials")
        if textured_materials != total_materials and not allow_broken_textures:
            raise RuntimeError(
                f"Imported model has incomplete albedo coverage: "
                f"{textured_materials}/{total_materials} mesh materials textured. "
                "Check the companion texture archive and texture resolver output."
            )

        # Never overwrite a known-good GLB until the replacement has exported
        # and passed validation.
        export_glb(temporary)
        if not temporary.is_file() or temporary.stat().st_size <= 1024:
            raise RuntimeError("GLB exporter did not produce a valid-sized output file")

        base_color_textures = glb_base_color_texture_count(temporary)
        if base_color_textures != total_materials and not allow_broken_textures:
            raise RuntimeError(
                f"Exported GLB has incomplete baseColorTexture coverage: "
                f"{base_color_textures}/{total_materials} mesh materials"
            )

        embedded = glb_animation_count(temporary)
        if wants_animation and animation_rejection is None and embedded <= 0:
            raise RuntimeError(
                f"Imported {imported_animations} animation clip(s), but exported GLB contains no animations"
            )
        if animation_rejection is not None and embedded > 0:
            raise RuntimeError(
                "Rejected animation left animation data in the supposedly static GLB"
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(destination)

        result = {
            "source": str(source),
            "output": str(destination),
            "animationRequested": wants_animation,
            "animationEmbedded": embedded > 0,
            "animationRejected": animation_rejection is not None,
            "animationRejectionReason": animation_rejection,
            "baseColorTextures": base_color_textures,
        }
        results.append(result)

        if animation_rejection is not None:
            print("Verified static fallback; model is quarantined/staged.", flush=True)
        elif wants_animation:
            print(f"Verified {embedded} embedded GLB animation(s).", flush=True)
        else:
            print("Verified static GLB; model remains staged until a compatible animation exists.", flush=True)

    except Exception as exc:
        failures.append({
            "source": str(source),
            "output": str(destination),
            "game": job.get("game"),
            "form": job.get("form"),
            "formKey": job.get("formKey"),
            "modelExtension": job.get("extension"),
            "animations": [
                {
                    "name": clip.get("name"),
                    "game": clip.get("game"),
                    "form": clip.get("form"),
                    "formKey": clip.get("formKey"),
                    "extension": clip.get("extension"),
                    "source": clip.get("source"),
                }
                for clip in (job.get("animations") or [])
            ],
            "error": str(exc),
            "untexturedMaterials": missing_materials,
        })
        traceback.print_exc()
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except Exception:
                pass
        if bake_enabled and bake_directory.is_dir():
            # The validated GLB embeds its final PNGs, so temporary shader
            # renders are not needed in the runtime pack.
            import shutil
            shutil.rmtree(bake_directory, ignore_errors=True)

results_path = jobs_path.with_name("switch-model-results.json")
results_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(f"Conversion results: {results_path}", flush=True)

if failures:
    failure_path = jobs_path.with_name("switch-model-failures.json")
    failure_path.write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    print(f"{len(failures)} conversions failed; details: {failure_path}")
    raise SystemExit(2)

