#!/usr/bin/env python3
"""Import a Blender-free GFPAK Pokémon ZIP without disturbing existing models.

Accepts the versioned archive emitted by GFPAK Open's Export Pokémon action.
A raw-assets-only ZIP is preserved as a source archive, but it cannot be
installed as a finished Pokédex model until a valid GLB is included.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from import_switch_game_assets import (
    WEB_ROOT, canonical_regular_form, choose_idle, glb_textures_complete,
    install_desktop, load_existing_manifest, material_texture_coverage,
    national_dex_for_model_id, parse_glb_doc, write_manifest,
)

EXPORT_MANIFEST = "gfpak-pokemon-export.json"
EXPORT_GLb = "pokedex3d/regular.glb"
MODEL_ID = re.compile(r"(?<![a-z0-9])pm(\d{4})(?!\d)", re.I)
GAMES = {"lgpe", "swsh", "la", "sv", "za", "bdsp"}
GAME_ALIASES = {"pla": "la"}
MAX_GLB_SIZE = 256 * 1024 * 1024
MAX_MANIFEST_SIZE = 64 * 1024


class ImportErrorWithAdvice(ValueError):
    pass


def read_export_metadata(archive: zipfile.ZipFile) -> dict:
    members = archive.namelist()
    if len(members) != len(set(members)) or len(members) > 100000:
        raise ImportErrorWithAdvice("Duplicate archive member names or too many files")
    for name in members:
        parts = name.replace("\\", "/").split("/")
        if name.startswith(("/", "\\")) or ".." in parts or re.match(r"^[A-Za-z]:", name):
            raise ImportErrorWithAdvice("Unsafe path inside archive: " + name)
    try:
        info = archive.getinfo(EXPORT_MANIFEST)
    except KeyError as exc:
        raise ImportErrorWithAdvice(
            "No GFPAK export manifest found. Re-export from the updated GFPAK Open app."
        ) from exc
    if info.file_size > MAX_MANIFEST_SIZE:
        raise ImportErrorWithAdvice("Export manifest is too large")
    try:
        data = json.loads(archive.read(info).decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ImportErrorWithAdvice("Invalid GFPAK export manifest") from exc
    if not isinstance(data, dict) or data.get("format") != "gfpak-pokemon-export" or data.get("version") != 1:
        raise ImportErrorWithAdvice("Unsupported GFPAK Pokémon export version")
    return data


def resolve_identity(metadata: dict, game_override: str | None, dex_override: int | None) -> tuple[int, int, str]:
    selected = metadata.get("selectedModel")
    if not isinstance(selected, str) or not selected:
        raise ImportErrorWithAdvice("Export manifest has no selected model filename")
    matches = MODEL_ID.findall(selected.replace("\\", "/"))
    if len(set(matches)) != 1:
        raise ImportErrorWithAdvice(
            "Selected model does not uniquely identify a pm#### Pokémon. "
            "Use a game asset with a recognizable Pokémon model filename."
        )
    model_id = int(matches[0])
    raw_game = game_override or metadata.get("sourceGame", "auto")
    game = GAME_ALIASES.get(raw_game, raw_game)
    if game not in GAMES and dex_override is None:
        raise ImportErrorWithAdvice(
            "Unknown source game. Select the correct game in GFPAK before export, "
            "or pass --game sv|za|swsh|lgpe|la|bdsp (or --dex N for a verified ID)."
        )
    # pm0000 is a Sword/Shield Pokémon Egg, not species #0000.
    # Only an explicit --dex 494 request can install it as Victini's Egg placeholder.
    egg_placeholder = model_id == 0 and game == "swsh" and dex_override == 494
    if model_id == 0 and not egg_placeholder:
        raise ImportErrorWithAdvice(
            "pm0000 is a Pokémon Egg, not Victini. Use --dex 494 explicitly "
            "to install this Sword/Shield Egg as a placeholder for Victini."
        )
    if game in GAMES:
        dex = 494 if egg_placeholder else national_dex_for_model_id(model_id, game)
        if not 1 <= dex <= 1025:
            raise ImportErrorWithAdvice(
                f"Internal model ID pm{model_id:04d} has no verified National Dex mapping for {game}."
            )
        if dex_override is not None and dex_override != dex:
            raise ImportErrorWithAdvice(
                f"Dex override #{dex_override} conflicts with verified {game} mapping #{dex} "
                f"for pm{model_id:04d}."
            )
    else:
        dex = dex_override
    if not isinstance(dex, int) or not 1 <= dex <= 1025:
        raise ImportErrorWithAdvice("National Dex number must be between 1 and 1025")
    if game in GAMES and not egg_placeholder:
        form, _form_key = canonical_regular_form(Path(selected), dex, game)
        if form != "regular":
            raise ImportErrorWithAdvice(
                f"This Pokédex baseline only accepts regular-form Pokémon (found {form})."
            )
    return dex, model_id, game


def inspect_converted_glb(path: Path) -> tuple[list[dict], str]:
    doc = parse_glb_doc(path)
    if not doc.get("meshes") or not doc.get("nodes"):
        raise ImportErrorWithAdvice("GLB has no model geometry or scene nodes")
    if not glb_textures_complete(path):
        raise ImportErrorWithAdvice(
            "GLB is missing base-color textures. Existing Pokédex models were preserved."
        )
    # The strict baseline needs embedded images, not URLs pointing to GFPAK's
    # local filesystem or a transient preview server.
    images = doc.get("images") or []
    textures = doc.get("textures") or []
    if not images or not textures:
        raise ImportErrorWithAdvice("GLB has no embedded texture images")
    for tex in textures:
        index = tex.get("source") if isinstance(tex, dict) else None
        if not isinstance(index, int) or index < 0 or index >= len(images):
            raise ImportErrorWithAdvice("GLB texture has no valid embedded image")
        image = images[index]
        if not isinstance(image, dict) or not isinstance(image.get("bufferView"), int):
            raise ImportErrorWithAdvice("GLB texture references an external image")
    animations = [
        {"name": animation.get("name") or f"animation_{index}"}
        for index, animation in enumerate(doc.get("animations") or [])
        if isinstance(animation, dict) and animation.get("channels") and animation.get("samplers")
    ]
    idle = choose_idle([animation["name"] for animation in animations])
    if not idle:
        raise ImportErrorWithAdvice(
            "Converted model has no verified idle animation. Export after GFPAK finishes "
            "loading companion animations; the existing Pokédex model was preserved."
        )
    return animations, idle


def import_archive(
    source: Path,
    *,
    game_override: str | None = None,
    dex_override: int | None = None,
    replace: bool = False,
    desktop: bool = True,
) -> dict:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ImportErrorWithAdvice(f"ZIP not found: {source}")

    with zipfile.ZipFile(source) as archive:
        metadata = read_export_metadata(archive)
        dex, model_id, game = resolve_identity(metadata, game_override, dex_override)
        glb_name = metadata.get("convertedModel")
        if glb_name != EXPORT_GLb:
            raise ImportErrorWithAdvice(
                "This ZIP contains original assets, but not a converted Pokédex GLB. "
                "Wait for textures/animations to finish loading in GFPAK and export again. "
                "You can still keep this ZIP as an original asset backup."
            )
        try:
            info = archive.getinfo(glb_name)
        except KeyError as exc:
            raise ImportErrorWithAdvice("Converted GLB was listed but is missing") from exc
        if info.file_size <= 1024 or info.file_size > MAX_GLB_SIZE:
            raise ImportErrorWithAdvice("Converted GLB is empty or exceeds the safe import limit")
        if info.compress_size and info.file_size / info.compress_size > 1000:
            raise ImportErrorWithAdvice("Converted GLB has a suspicious compression ratio")

        target = WEB_ROOT / f"{dex:04d}" / "regular.glb"
        previous = next(
            (row for row in load_existing_manifest()
             if int(row.get("dex", -1)) == dex and row.get("form") == "regular"),
            None,
        )
        if not replace and previous and previous.get("ready") is not False and target.is_file():
            raise ImportErrorWithAdvice(
                f"#{dex:04d} is already installed. Add --replace to explicitly replace it."
            )

        with tempfile.TemporaryDirectory(prefix="pokedex-gfpak-") as temporary:
            validated = Path(temporary) / "regular.glb"
            with archive.open(info) as data, validated.open("wb") as output:
                shutil.copyfileobj(data, output, length=1024 * 1024)
            animations, idle = inspect_converted_glb(validated)
            entry = {
                "dex": dex,
                "modelId": model_id,
                "eggPlaceholder": model_id == 0 and dex == 494 and game == "swsh",
                "form": "regular",
                "formKey": "regular",
                "url": f"web/models/switch/{dex:04d}/regular.glb",
                "source": f"gfpak-pokemon-export:{game}",
                "sourceGame": game,
                "sourceFormat": "gfpak-zip",
                "animationMatch": "embedded-in-converted-glb",
                "animationRejected": False,
                "animations": animations,
                "idleAnimation": idle,
                "idleBreaks": [],
                "ready": True,
                "valid": True,
                "warnings": [],
            }
            prior_entries = load_existing_manifest()
            updated = [row for row in prior_entries
                       if not (int(row.get("dex", -1)) == dex and row.get("form") == "regular")]
            updated.append(entry)
            updated.sort(key=lambda row: (int(row["dex"]), str(row["form"])))

            target.parent.mkdir(parents=True, exist_ok=True)
            backup = Path(temporary) / "previous.glb"
            if target.is_file():
                shutil.copy2(target, backup)
            staged = target.with_suffix(".glb.gfpak-tmp")
            try:
                shutil.copy2(validated, staged)
                staged.replace(target)
                write_manifest(updated)
                if desktop:
                    install_desktop([entry], prune_missing=False)
            except Exception:
                if backup.exists():
                    backup.replace(target)
                else:
                    target.unlink(missing_ok=True)
                write_manifest(prior_entries)
                raise
    return {"dex": dex, "modelId": model_id, "game": game,
            "animations": len(animations), "idle": idle, "model": str(target)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import GFPAK Pokémon ZIP into Pokédex 3D Max (no Blender)")
    parser.add_argument("zip", type=Path, help="GFPAK Export Pokémon ZIP")
    parser.add_argument("--game", choices=sorted(GAMES | set(GAME_ALIASES)),
                        help="source game when auto-detection is unknown")
    parser.add_argument("--dex", type=int,
                        help="verified National Dex ID; --dex 494 permits SWSH pm0000 as an Egg placeholder")
    parser.add_argument("--replace", action="store_true", help="replace an existing working Pokémon")
    parser.add_argument("--no-desktop-install", action="store_true",
                        help="write web catalog only (do not install to desktop runtime)")
    args = parser.parse_args()
    try:
        result = import_archive(args.zip, game_override=args.game, dex_override=args.dex,
                                replace=args.replace, desktop=not args.no_desktop_install)
    except (ImportErrorWithAdvice, ValueError, zipfile.BadZipFile, OSError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 2
    print(f"Imported #{result['dex']:04d} from {result['game']} (internal pm{result['modelId']:04d})")
    print(f"Verified {result['animations']} animations; idle: {result['idle']}")
    print(f"GLB: {result['model']}")
    print("Refresh or reopen Pokédex 3D Max to see the model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
