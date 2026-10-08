#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWITCH_ROOT = ROOT / "web" / "models" / "switch"
SWITCH_MANIFEST = ROOT / "web" / "models" / "switch-manifest.json"
DEFAULT_RELEASE_TAG = "model-pack-v7"
DEFAULT_MANIFEST_URL = (
    "https://github.com/Unborne-Fetus/Pokedex-3D-Max/releases/download/"
    + DEFAULT_RELEASE_TAG
    + "/model-pack-manifest.json"
)
CACHE_ROOT = ROOT / ".cache" / "remote-switch-model-pack"
STATE_FILE = CACHE_ROOT / "installed-state.json"
SPECIES_NAMES = ROOT / "data" / "species_names.tsv"
USER_AGENT = "Pokedex3DMax-RemoteModelPack/1"


def is_shiny_entry(entry: dict) -> bool:
    return "shiny" in str(entry.get("form", "")).casefold() or str(entry.get("name", "")).casefold().startswith("shiny ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response, temp.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)
    temp.replace(destination)


def download_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Remote model-pack manifest is not a JSON object")
    return value


def safe_extract_zip(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsafe archive member: {member.filename}")
        archive.extractall(destination)


def load_switch_entries() -> list[dict]:
    if not SWITCH_MANIFEST.is_file():
        raise RuntimeError(
            "switch-manifest.json does not exist. Run the local Switch importer first."
        )
    data = json.loads(SWITCH_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("switch-manifest.json is malformed")
    return [entry for entry in data if isinstance(entry, dict) and entry.get("ready") is not False]


def shard_name(dex: int, shard_size: int) -> str:
    start = ((dex - 1) // shard_size) * shard_size + 1
    end = start + shard_size - 1
    return f"switch-models-{start:04d}-{end:04d}.zip"


def build_pack(output: Path, base_url: str, shard_size: int) -> int:
    entries = [entry for entry in load_switch_entries() if not is_shiny_entry(entry)]
    if not entries:
        raise RuntimeError("No ready Switch model entries exist to publish")

    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("switch-models-*.zip"):
        old.unlink()

    by_shard: dict[str, list[dict]] = {}
    normalized_entries: list[dict] = []

    for entry in entries:
        dex = int(entry["dex"])
        form = str(entry["form"])
        source = SWITCH_ROOT / f"{dex:04d}" / f"{form}.glb"
        if not source.is_file() or source.stat().st_size <= 1024:
            raise RuntimeError(f"Ready Switch model is missing: {source}")

        name = shard_name(dex, shard_size)
        by_shard.setdefault(name, []).append(entry)
        normalized_entries.append(
            {
                "dex": dex,
                "form": form,
                "path": f"switch/{dex:04d}/{form}.glb",
                "source": entry.get("source", "official-game-assets"),
                "sourceGame": entry.get("sourceGame"),
                "idleAnimation": entry.get("idleAnimation"),
                "animations": entry.get("animations") or [],
                "shard": name,
                "bytes": source.stat().st_size,
                "sha256": sha256_file(source),
            }
        )

    shards: list[dict] = []
    for name in sorted(by_shard):
        archive_path = output / name
        shard_entries = by_shard[name]
        with zipfile.ZipFile(
            archive_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for entry in shard_entries:
                dex = int(entry["dex"])
                form = str(entry["form"])
                source = SWITCH_ROOT / f"{dex:04d}" / f"{form}.glb"
                archive.write(source, arcname=f"switch/{dex:04d}/{form}.glb")

        shards.append(
            {
                "name": name,
                "url": base_url.rstrip("/") + "/" + name,
                "bytes": archive_path.stat().st_size,
                "sha256": sha256_file(archive_path),
                "models": len(shard_entries),
            }
        )

    manifest = {
        "format": 1,
        "pack": "Pokedex 3D Max Switch Models",
        "pipelineVersion": 7,
        "releaseTag": DEFAULT_RELEASE_TAG,
        "models": len(normalized_entries),
        "shardSize": shard_size,
        "shards": shards,
        "entries": sorted(
            normalized_entries,
            key=lambda item: (item["dex"], item["form"]),
        ),
    }
    atomic_json(output / "model-pack-manifest.json", manifest)
    print(
        f"Built remote Switch model pack: {len(normalized_entries)} model(s), "
        f"{len(shards)} shard(s)"
    )
    print(f"Output: {output}")
    return 0


def read_species_names(path: Path = SPECIES_NAMES) -> dict[int, str]:
    names: dict[int, str] = {}
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        cols = line.split("\t", 1)
        if len(cols) != 2 or not cols[0].isdigit():
            continue
        name = cols[1].strip()
        if name:
            names[int(cols[0])] = name
    return names


def read_catalog(path: Path) -> dict[tuple[int, str], list[str]]:
    rows: dict[tuple[int, str], list[str]] = {}
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 4 and cols[0].isdigit():
            rows[(int(cols[0]), cols[2])] = cols[:4]
    return rows


def write_catalog(path: Path, rows: dict[tuple[int, str], list[str]]) -> None:
    text = ["dex\tname\tform\tpath"]
    text.extend("\t".join(cols) for _, cols in sorted(rows.items()))
    temp = path.with_suffix(".tmp")
    temp.write_text("\n".join(text) + "\n", encoding="utf-8")
    temp.replace(path)


def install_pack(manifest_url: str, target: Path, force: bool = False) -> int:
    print(f"Checking remote Switch model pack: {manifest_url}")
    try:
        manifest = download_json(manifest_url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"Remote Switch model pack unavailable: {exc}")
        return 3

    if manifest.get("format") != 1:
        print("Remote Switch model pack uses an unsupported manifest format.")
        return 3

    entries = manifest.get("entries")
    shards = manifest.get("shards")
    if isinstance(entries, list):
        entries = [entry for entry in entries if isinstance(entry, dict) and not is_shiny_entry(entry)]
    if not isinstance(entries, list) or not isinstance(shards, list) or not entries:
        print("Remote Switch model pack manifest is incomplete.")
        return 3

    target.mkdir(parents=True, exist_ok=True)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    downloads = CACHE_ROOT / "downloads"
    extracted = CACHE_ROOT / "extracted"
    downloads.mkdir(parents=True, exist_ok=True)
    extracted.mkdir(parents=True, exist_ok=True)

    old_state = read_json(STATE_FILE, {})
    old_shards = old_state.get("shards", {}) if isinstance(old_state, dict) else {}
    installed_shards: dict[str, str] = {}

    for index, shard in enumerate(shards, start=1):
        if not isinstance(shard, dict):
            raise RuntimeError("Malformed shard entry")
        name = str(shard["name"])
        url = str(shard["url"])
        expected = str(shard["sha256"]).lower()
        archive = downloads / name

        cached_ok = (
            not force
            and archive.is_file()
            and old_shards.get(name) == expected
            and sha256_file(archive).lower() == expected
        )

        if cached_ok:
            print(f"[{index}/{len(shards)}] cached {name}")
        else:
            print(f"[{index}/{len(shards)}] downloading {name}")
            try:
                download(url, archive)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
                print(f"Remote shard download failed: {name}: {exc}")
                return 3
            actual = sha256_file(archive).lower()
            if actual != expected:
                archive.unlink(missing_ok=True)
                print(f"Remote shard checksum failed: {name}")
                return 3

        shard_extract = extracted / name.removesuffix(".zip")
        marker = shard_extract / ".sha256"
        if force or not marker.is_file() or marker.read_text(encoding="utf-8").strip() != expected:
            if shard_extract.exists():
                shutil.rmtree(shard_extract)
            safe_extract_zip(archive, shard_extract)
            marker.write_text(expected + "\n", encoding="utf-8")

        installed_shards[name] = expected

    switch_root = target / "switch"
    switch_root.mkdir(parents=True, exist_ok=True)
    expected_switch_paths: set[Path] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel = Path(str(entry["path"]))
        if rel.parts[:1] != ("switch",):
            raise RuntimeError(f"Unexpected remote model path: {rel}")
        shard = str(entry["shard"])
        src = extracted / shard.removesuffix(".zip") / rel
        dst = target / rel
        if not src.is_file():
            raise RuntimeError(f"Remote pack is missing model: {rel}")
        expected_model_hash = str(entry.get("sha256", "")).lower()
        if expected_model_hash and sha256_file(src).lower() != expected_model_hash:
            raise RuntimeError(f"Remote model checksum failed: {rel}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if force or not dst.is_file() or sha256_file(dst) != sha256_file(src):
            shutil.copy2(src, dst)
        expected_switch_paths.add(dst.resolve())

    # Remove obsolete remote/local Switch overrides that are not part of the
    # current validated online pack. Original downloaded game archives remain
    # untouched in .cache/mega-switch-assets and continue to serve as backup.
    for path in switch_root.rglob("*.glb"):
        if path.resolve() not in expected_switch_paths:
            path.unlink()

    catalog_path = target / "model_catalog.tsv"
    generic_catalog_path = target / "generic_model_catalog.tsv"
    runtime_species_names = target / "species_names.tsv"
    if SPECIES_NAMES.is_file():
        shutil.copy2(SPECIES_NAMES, runtime_species_names)

    catalog = read_catalog(catalog_path)
    generic = read_catalog(generic_catalog_path)

    # Preserve meaningful names before generic rows or remote overlays mutate
    # the catalog. Older Switch installs may already know the species name even
    # when a generic fallback row is missing for a particular form.
    preserved_names: dict[tuple[int, str], str] = {
        key: row[1]
        for key, row in catalog.items()
        if len(row) >= 2 and row[1] and not row[1].startswith("#")
    }
    names_by_dex: dict[int, str] = read_species_names()
    for source_rows in (catalog, generic):
        for (dex, _form), row in source_rows.items():
            if len(row) >= 2 and row[1] and not row[1].startswith("#"):
                names_by_dex.setdefault(dex, row[1])

    # Restore generic rows first, then overlay every remote Switch model.
    if generic:
        for key, row in generic.items():
            catalog[key] = row
    else:
        catalog = {
            key: row
            for key, row in catalog.items()
            if len(row) >= 4 and not row[3].replace("\\", "/").startswith("switch/")
        }

    remote_keys: set[tuple[int, str]] = set()
    for entry in entries:
        dex = int(entry["dex"])
        form = str(entry["form"])
        key = (dex, form)
        remote_keys.add(key)
        fallback = generic.get(key)
        name = names_by_dex.get(dex)
        if not name and fallback and len(fallback) >= 2 and fallback[1]:
            name = fallback[1]
        if not name:
            name = preserved_names.get(key) or f"#{dex:04d}"
        catalog[key] = [str(dex), name, form, str(entry["path"]).replace("\\", "/")]

    # If an old Switch row survived for a no-longer-published form, restore its
    # generic fallback or remove it from runtime selection.
    for key, row in list(catalog.items()):
        if len(row) < 4:
            continue
        if not row[3].replace("\\", "/").startswith("switch/"):
            continue
        if key in remote_keys:
            continue
        if key in generic:
            catalog[key] = generic[key]
        else:
            catalog.pop(key, None)

    write_catalog(catalog_path, catalog)

    state = {
        "format": 1,
        "manifestUrl": manifest_url,
        "pipelineVersion": manifest.get("pipelineVersion"),
        "models": len(entries),
        "shards": installed_shards,
    }
    atomic_json(STATE_FILE, state)
    print(
        f"Remote Switch model pack installed: {len(entries)} model(s), "
        f"{len(shards)} shard(s)"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or install the Pokedex 3D Max remote Switch model pack"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="package validated local Switch GLBs into release shards")
    build.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / DEFAULT_RELEASE_TAG,
    )
    build.add_argument(
        "--base-url",
        default=(
            "https://github.com/Unborne-Fetus/Pokedex-3D-Max/releases/download/"
            + DEFAULT_RELEASE_TAG
        ),
    )
    build.add_argument("--shard-size", type=int, default=100)

    install = sub.add_parser("install", help="download and install the validated remote model pack")
    install.add_argument(
        "--manifest-url",
        default=os.environ.get("POKEDEX3D_MODEL_PACK_MANIFEST", DEFAULT_MANIFEST_URL),
    )
    install.add_argument(
        "--target",
        type=Path,
        default=(
            Path(os.environ["LOCALAPPDATA"]) / "Pokedex3DMax" / "offline-models"
            if os.environ.get("LOCALAPPDATA")
            else ROOT / "offline-models"
        ),
    )
    install.add_argument("--force", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "build":
        if args.shard_size <= 0:
            raise SystemExit("--shard-size must be positive")
        return build_pack(args.output.resolve(), args.base_url, args.shard_size)
    if args.command == "install":
        return install_pack(args.manifest_url, args.target.resolve(), args.force)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
