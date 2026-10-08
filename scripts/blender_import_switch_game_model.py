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

            animation_data = armature.animation_data
            for track in list(animation_data.nla_tracks):
                animation_data.nla_tracks.remove(track)
            animation_data.action = action
            action.name = clip.get("name") or source.stem
            action.use_fake_user = True
            bpy.context.view_layer.update()

            frame_range = tuple(float(value) for value in action.frame_range)
            print(
                f"Using active animation: {action.name}; frames {frame_range}",
                flush=True,
            )
            return 1
        except Exception as exc:
            errors.append(f"{source.name}: {type(exc).__name__}: {exc}")
            remove_new_actions(before_actions)

    bone_sample = ", ".join(bone.name for bone in list(armature.pose.bones)[:20])
    raise RuntimeError(
        "No compatible animation clip could be imported for "
        f"{Path(job['source']).name}. Tried {len(clips)} clip(s). "
        f"Armature has {len(armature.pose.bones)} bones"
        + (f" (sample: {bone_sample})" if bone_sample else "")
        + ". "
        + " | ".join(errors)
    )


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
    print(f"[{index}/{len(jobs)}] {source.name} -> {destination.name}", flush=True)

    try:
        if temporary.exists():
            temporary.unlink()

        clear_scene()
        import_model(source)
        wants_animation = bool(job.get("animations"))
        imported_animations = import_animations(job)

        if wants_animation and imported_animations <= 0:
            raise RuntimeError("Animation candidates were selected but none were imported")

        # Never overwrite a known-good GLB until the replacement has exported
        # and passed validation.
        export_glb(temporary)
        if not temporary.is_file() or temporary.stat().st_size <= 1024:
            raise RuntimeError("GLB exporter did not produce a valid-sized output file")

        embedded = glb_animation_count(temporary)
        if wants_animation and embedded <= 0:
            raise RuntimeError(
                f"Imported {imported_animations} animation clip(s), but exported GLB contains no animations"
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(destination)
        if wants_animation:
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
        })
        traceback.print_exc()
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except Exception:
                pass

if failures:
    failure_path = jobs_path.with_name("switch-model-failures.json")
    failure_path.write_text(json.dumps(failures, indent=2) + "\n", encoding="utf-8")
    print(f"{len(failures)} conversions failed; details: {failure_path}")
    raise SystemExit(2)
