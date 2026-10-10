"""Expose already-installed Switch GLBs to the browser index without downloading."""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def default_pack() -> Path:
    if os.environ.get("POKEDEX_3D_MAX_MODELS"):
        return Path(os.environ["POKEDEX_3D_MAX_MODELS"])
    if os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Pokedex3DMax" / "offline-models"
    return ROOT / "offline-models"


def animation_names(path: Path) -> list[str]:
    with path.open("rb") as handle:
        magic, version, total = struct.unpack("<III", handle.read(12))
        if magic != 0x46546C67 or version != 2 or total != path.stat().st_size:
            raise ValueError(f"Invalid GLB: {path}")
        length, kind = struct.unpack("<II", handle.read(8))
        if kind != 0x4E4F534A or length > total - 20:
            raise ValueError(f"Invalid GLB JSON: {path}")
        doc = json.loads(handle.read(length).rstrip(b" \x00\t\r\n"))
    return [entry.get("name") or f"animation_{i}" for i, entry in enumerate(doc.get("animations", []))]


def sync_pack(target: Path, repo: Path = ROOT, selected_dexes: set[int] | None = None) -> int:
    target = target.resolve()
    catalog = target / "model_catalog.tsv"
    if not catalog.is_file():
        print(f"No installed model catalog at {catalog}; keeping existing browser assets.")
        return 0
    metadata_path = target / "switch-model-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else []
    metadata_by_key = {(int(e["dex"]), e["form"]): e for e in metadata}
    old_manifest = repo / "web/models/switch-manifest.json"
    if old_manifest.is_file():
        for entry in json.loads(old_manifest.read_text(encoding="utf-8")):
            metadata_by_key.setdefault((int(entry["dex"]), entry["form"]), entry)
    entries = []
    for line in catalog.read_text(encoding="utf-8").splitlines()[1:]:
        cells = line.split("\t")
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        relative = Path(cells[3].replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts or relative.parts[:1] != ("switch",):
            continue
        source = (target / relative).resolve()
        if not source.is_relative_to(target) or not source.is_file():
            continue
        dex, name, form = int(cells[0]), cells[1], cells[2]
        if selected_dexes is not None and dex not in selected_dexes:
            continue
        if form.lower() != "regular":
            continue
        try:
            names = animation_names(source)
        except (OSError, ValueError, struct.error) as error:
            print(f"Skipping invalid Switch model {source}: {error}")
            continue
        entry = dict(metadata_by_key.get((dex, form), {}))
        idle = entry.get("idleAnimation")
        if idle not in names:
            idle = next((n for n in names if re.search(r"idle|wait|stand|breath|fight[_ -]?a", n, re.I)
                         and not re.search(r"attack|damage|faint|death|bind|t[-_ ]?pose", n, re.I)), None)
        if not idle or entry.get("ready") is False:
            continue
        destination = repo / "web/models" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        current = destination.is_file() and (
            os.path.samefile(source, destination) or
            (source.stat().st_size == destination.stat().st_size and
             source.stat().st_mtime_ns == destination.stat().st_mtime_ns)
        )
        if not current:
            temp = destination.with_suffix(".glb.tmp")
            temp.unlink(missing_ok=True)
            try:
                os.link(source, temp)
            except OSError:
                shutil.copy2(source, temp)
            temp.replace(destination)
        entry.update(dex=dex, name=name, form=form, url="web/models/" + relative.as_posix(),
                     local=True, ready=True, valid=True, animations=names, idleAnimation=idle,
                     idleBreaks=[n for n in entry.get("idleBreaks", []) if n in names and n != idle],
                     source="Switch game assets")
        entries.append(entry)
    if selected_dexes is not None and old_manifest.is_file():
        # Targeted recovery must never replace or recopy unrelated reviewed models.
        for previous in json.loads(old_manifest.read_text(encoding="utf-8")):
            dex = int(previous.get("dex", 0))
            form = str(previous.get("form", ""))
            if dex in selected_dexes or form != "regular" or previous.get("ready") is False:
                continue
            if (repo / "web/models/switch" / f"{dex:04d}" / "regular.glb").is_file():
                entries.append(previous)
    policy_path = target / "model_source_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.is_file() else {}
    policy.update({"switchOnly": True, "regularOnly": True, "allowBrokenTextures": False})
    entries.sort(key=lambda e: (e["dex"], e["form"]))
    old_manifest.parent.mkdir(parents=True, exist_ok=True)
    for path, text in [(old_manifest, json.dumps(entries, indent=2) + "\n"),
                       (old_manifest.with_suffix(".js"), "window.POKEDEX3D_MODEL_POLICY = " + json.dumps(policy) + ";\nwindow.POKEDEX3D_SWITCH_MODELS = " + json.dumps(entries) + ";\n")]:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
    print(f"Browser index synced: {len(entries)} regular animated Switch model(s).")
    return len(entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=default_pack())
    args = parser.parse_args()
    sync_pack(args.target)
