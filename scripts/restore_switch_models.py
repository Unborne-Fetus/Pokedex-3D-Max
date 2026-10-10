"""Restore animated Switch GLBs by verified species identity, not folder number.

Old Scarlet/Violet archives use internal IDs; stale numbered folders may hold a
completely different Pokémon. No source files are deleted by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from import_switch_game_assets import (
    parse_glb_doc, choose_idle, glb_textures_complete,
    national_dex_for_model_id,
)
from sync_switch_web import ROOT, default_pack, sync_pack

MODEL_ID = re.compile(r"(?<![a-z0-9])pm(\d{4})(?!\d)", re.I)

def git_blob_hash(path: Path) -> str:
    """Match GitHub's SHA1 of the exact GLB bytes, not its folder name."""
    digest = hashlib.sha1()
    digest.update(f"blob {path.stat().st_size}".encode() + bytes((0,)))
    with path.open("rb") as inp:
        for block in iter(lambda: inp.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()



def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def glb_internal_id(doc: dict) -> int | None:
    """Recover original pmNNNN from imported GLB names, if unambiguous."""
    groups = [
        doc.get("images") or [],
        doc.get("meshes") or [],
        doc.get("nodes") or [],
        doc.get("materials") or [],
    ]
    for group in groups:
        found = set()
        for item in group:
            if isinstance(item, dict):
                for value in (item.get("name", ""),):
                    found.update(int(n) for n in MODEL_ID.findall(str(value)))
        if len(found) == 1:
            return next(iter(found))
        if len(found) > 1:
            return None
    return None


def source_game(value: str) -> str | None:
    label = str(value or "").casefold()
    if label.startswith(("sv", "scarlet", "violet")):
        return "sv"
    if label.startswith(("swsh", "sword", "shield")):
        return "swsh"
    if label.startswith(("la", "pla", "legends-arceus")):
        return "la"
    if label.startswith(("za", "legends-za")):
        return "za"
    if label.startswith("lgpe"):
        return "lgpe"
    return None


def known_identity(
    slot: int, doc: dict, entry: dict, historical: dict
) -> tuple[int, int, str] | None:
    """Returns (canonical Dex, internal ID, source game) only on real evidence."""
    embedded = glb_internal_id(doc)
    reported = entry.get("sourceModelId", entry.get("modelId"))
    try:
        reported = int(reported) if reported is not None else None
    except (TypeError, ValueError):
        reported = None
    game = source_game(entry.get("sourceGame") or
                       str(entry.get("source", "")).replace("official-game-assets:", ""))
    if embedded is not None and reported is not None and embedded != reported:
        # Metadata from an earlier model at this folder is stale.
        reported = None
    internal = embedded if embedded is not None else reported
    if internal is None:
        return None

    old = historical.get(slot)
    if old:
        old_id = MODEL_ID.search(str(old.get("source", "")))
        if old_id and int(old_id.group(1)) == internal and reported is None:
            # This exact binary source ID is documented by the texture audit;
            # stale model-metadata.json game labels must not override it.
            game = source_game(old.get("game", "")) or game
    if game is None:
        # Early internal model IDs coincide with National Dex. Higher source
        # IDs overlap between games, so do not guess the game.
        if internal <= 649 and internal == slot:
            return slot, internal, "unknown"
        return None
    dex = national_dex_for_model_id(internal, game)
    if not 1 <= dex <= 1025:
        return None
    return dex, internal, game


def restore(target: Path, repo: Path = ROOT) -> int:
    target = target.resolve()
    roots = [
        target / "switch",
        repo / "web/models/switch",
        repo / ".cache/switch-game-assets/original-glbs",
    ]
    metadata = {}
    # The installed metadata is first-choice for installed GLBs; only fallback
    # to repository entries when no installed record exists.
    for path in [repo / "web/models/switch-manifest.json",
                 target / "switch-model-metadata.json"]:
        if path.is_file():
            for e in json.loads(path.read_text(encoding="utf-8")):
                metadata[(int(e["dex"]), str(e.get("form", "regular")))] = e
    provenance_path = repo / "data/verified_switch_glb_provenance.json"
    provenance = {}
    if provenance_path.is_file():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8")).get("models", {})
    history_path = repo / "data/switch-texture-repair-report.json"
    historical = {}
    if history_path.is_file():
        for e in json.loads(history_path.read_text(encoding="utf-8")).get("repaired", []):
            historical[int(e["dex"])] = e

    # Always use the official National Dex table over stale installed names.
    names = {}
    name_path = repo / "data/species_names.tsv"
    if name_path.is_file():
        for line in name_path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) >= 2 and fields[0].isdigit():
                names[int(fields[0])] = fields[1]
    found = {}
    mismatches = 0
    uncertain = 0
    for rank, root in enumerate(roots):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("regular.glb")):
            if not path.parent.name.isdigit():
                continue
            slot = int(path.parent.name)
            if not 1 <= slot <= 1025:
                continue
            source_entry = dict(metadata.get((slot, "regular"), {}))
            try:
                doc = parse_glb_doc(path)
                if not isinstance(doc, dict) or not doc.get("meshes") or not doc.get("scenes"):
                    continue
                clips = [
                    clip.get("name") or f"animation_{i}"
                    for i, clip in enumerate(doc.get("animations", []))
                    if isinstance(clip, dict) and clip.get("channels") and clip.get("samplers")
                ]
                idle = source_entry.get("idleAnimation")
                if idle not in clips:
                    idle = choose_idle(clips)
                if not idle or not glb_textures_complete(path):
                    continue
                # An exact historical Git blob hash is stronger than any
                # stale metadata or an ambiguous scene node name.
                fingerprint = provenance.get(git_blob_hash(path))
                identity = (
                    (national_dex_for_model_id(
                        int(fingerprint["sourceModelId"]),
                        source_game(fingerprint["sourceGame"]) or "unknown"
                    ), int(fingerprint["sourceModelId"]),
                     source_game(fingerprint["sourceGame"]) or "unknown")
                    if fingerprint else known_identity(slot, doc, source_entry, historical)
                )
            except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                print(f"Skipping damaged Switch GLB {path}: {error}")
                continue
            if identity is None:
                # S/V internal IDs overlap the modern National Dex. An old
                # pm1012 GLB cannot claim Poltchageist's #1012 merely because
                # an obsolete installation stored it in switch/1012/.
                uncertain += 1
                if slot >= 1001:
                    print(f"Skipping unverified high-Dex model {path}: source species unknown")
                    continue
                # Only retain an unverified early slot when its number does
                # not occupy the known high S/V internal-ID range.
                dex, internal, game = slot, None, None
            else:
                dex, internal, game = identity
                if not 1 <= dex <= 1025:
                    uncertain += 1
                    continue
                if dex != slot:
                    mismatches += 1
                    print(f"Correcting {path}: internal pm{internal:04d} ({game}) -> National #{dex:04d}")
            original = dict(metadata.get((dex, "regular"), {}))
            # Do not attach metadata for a different species to this GLB.
            if internal is not None and int(original.get("modelId") or original.get("sourceModelId") or internal) != internal:
                original = {}
            candidate = dict(source_entry if dex == slot else original)
            candidate.update(
                dex=dex, name=names.get(dex, f"#{dex:04d}"),
                form="regular", ready=True, valid=True,
                idleAnimation=idle, animations=clips,
                idleBreaks=[n for n in candidate.get("idleBreaks", []) if n in clips and n != idle],
                source="Switch game assets", textureIssues=False,
            )
            if internal is not None and game != "unknown":
                candidate["sourceGame"] = game
                candidate["sourceModelId"] = internal
                candidate["modelId"] = internal
            else:
                # Do not misrepresent old, guessed folder IDs as verified.
                for key in ("modelId", "sourceModelId", "sourceGame"):
                    candidate.pop(key, None)
            key = (dex, "regular")
            # Prefer already correctly filed assets, then installed assets,
            # then repo exports and older caches.
            score = (0 if identity is not None else 1, 0 if slot == dex else 1, rank)
            if key not in found or score < found[key][0]:
                found[key] = (score, path, candidate)
    if not found:
        print("No usable animated Switch exports remain.")
        return 0

    # Stage all candidates before writing any destination (source and target
    # folders may form cycles). Preserve originals in a non-scanned backup.
    stage = target / ".dex-restoration-stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    items = []
    for (dex, form), (_, source, entry) in sorted(found.items()):
        staged = stage / f"{dex:04d}.glb"
        shutil.copy2(source, staged)
        items.append((dex, form, entry, staged))
    try:
        entries = []
        for dex, form, entry, staged in items:
            relative = Path("switch") / f"{dex:04d}" / "regular.glb"
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(destination)
            backup = roots[-1] / f"{dex:04d}" / "regular.glb"
            backup.parent.mkdir(parents=True, exist_ok=True)
            if backup.resolve() != destination.resolve():
                shutil.copy2(destination, backup)
            entry["path"] = relative.as_posix()
            entries.append(entry)
        atomic_text(target / "model_catalog.tsv", "dex\tname\tform\tpath\n" +
                    "".join(f"{e['dex']}\t{e['name']}\tregular\t{e['path']}\n" for e in entries))
        atomic_text(target / "switch-model-metadata.json", json.dumps(entries, indent=2) + "\n")
        atomic_text(target / "model_source_policy.json",
                    json.dumps({"switchOnly": True, "regularOnly": True,
                                "allowBrokenTextures": False}) + "\n")
        sync_pack(target, repo)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    print(f"Restored {len(entries)} Switch models; corrected {mismatches} misfiled "
          f"sources, {uncertain} entries without conclusive embedded IDs.")
    return len(entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=default_pack())
    args = parser.parse_args()
    raise SystemExit(0 if restore(args.target) else 2)
