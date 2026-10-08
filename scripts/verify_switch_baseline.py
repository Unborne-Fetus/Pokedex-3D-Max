#!/usr/bin/env python3
"""Verify a completed, regular-only original Switch model baseline.

Run after setup-all.bat switch/full:
    python scripts/verify_switch_baseline.py

Checks the pipeline completion marker, native offline catalog, browser manifest,
all GLB meshes/materials/textures/idle animations, and byte-identical models
between the browser index and native desktop app. Read-only: never repairs,
deletes, or replaces source assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

from import_switch_game_assets import (
    ROOT,
    CONVERSION_PIPELINE_VERSION,
    PIPELINE_READY,
    MANIFEST_JSON,
    MANIFEST_JS,
    material_texture_coverage,
)

WEB_ROOT = ROOT / "web" / "models" / "switch"
MAX_DETAILS = 25


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def glb_json(path: Path) -> dict:
    """Read the GLB JSON chunk without buffering the entire geometry payload."""
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise ValueError("Truncated GLB header")
        magic, version, size = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2 or size != path.stat().st_size:
            raise ValueError("Invalid GLB header, version, or size")
        while stream.tell() + 8 <= size:
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError("Truncated GLB chunk header")
            length, kind = struct.unpack("<II", header)
            if length > size - stream.tell():
                raise ValueError("GLB chunk exceeds file length")
            if kind == 0x4E4F534A:
                return json.loads(stream.read(length).rstrip(b" \t\r\n\x00").decode("utf-8"))
            stream.seek(length, 1)
    raise ValueError("Missing GLB JSON chunk")


def javascript_manifest(path: Path) -> list:
    source = path.read_text(encoding="utf-8")
    token = "window.POKEDEX3D_SWITCH_MODELS ="
    offset = source.find(token)
    if offset == -1:
        raise ValueError("Browser script does not assign POKEDEX3D_SWITCH_MODELS")
    models, _ = json.JSONDecoder().raw_decode(source[offset + len(token):].lstrip())
    if not isinstance(models, list):
        raise ValueError("Browser model manifest must be an array")
    return models


def inspect_glb(path: Path, expected_idle: str) -> list[str]:
    doc = glb_json(path)
    problems = []
    if not doc.get("scenes") or not doc.get("meshes") or not doc.get("nodes"):
        problems.append("no scene, meshes, or nodes")
    if not doc.get("skins"):
        problems.append("no skeletal skin")
    if not doc.get("materials"):
        problems.append("no materials")
    textured, total = material_texture_coverage(doc)
    if total == 0 or textured != total:
        problems.append(f"albedo coverage {textured}/{total}")
    images = doc.get("images") or []
    textures = doc.get("textures") or []
    views = doc.get("bufferViews") or []
    for mat in doc.get("materials") or []:
        slot = (mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
        if not isinstance(slot, dict):
            continue
        texture_index = slot.get("index")
        if not isinstance(texture_index, int) or not 0 <= texture_index < len(textures):
            problems.append("invalid albedo texture index")
            continue
        image_index = textures[texture_index].get("source")
        if not isinstance(image_index, int) or not 0 <= image_index < len(images):
            problems.append("unresolved base-color image")
            continue
        image = images[image_index]
        view_index = image.get("bufferView")
        uri = image.get("uri", "")
        if isinstance(view_index, int) and 0 <= view_index < len(views):
            if views[view_index].get("byteLength", 0) <= 0:
                problems.append("empty embedded image")
        elif not isinstance(uri, str) or not uri.startswith("data:image/"):
            problems.append("external/missing image instead of embedded texture")
    names = []
    for anim in doc.get("animations") or []:
        if not isinstance(anim, dict) or not anim.get("channels") or not anim.get("samplers"):
            continue
        names.append(anim.get("name") or "")
    if not names:
        problems.append("no playable animation tracks")
    elif expected_idle not in names:
        problems.append(f"idle clip {expected_idle!r} absent from {names[:5]}")
    for anim in doc.get("animations") or []:
        if not isinstance(anim, dict):
            continue
        for channel in anim.get("channels") or []:
            target = (channel.get("target") or {}).get("node")
            sampler = channel.get("sampler")
            if not isinstance(target, int) or not 0 <= target < len(doc.get("nodes") or []):
                problems.append("animation targets invalid node")
                break
            if not isinstance(sampler, int) or not 0 <= sampler < len(anim.get("samplers") or []):
                problems.append("animation references invalid sampler")
                break
    return sorted(set(problems))


def verify(local_root: Path, deep: bool = True) -> int:
    problems: list[str] = []

    def issue(message: str) -> None:
        problems.append(message)

    if not PIPELINE_READY.is_file():
        print(f"NOT COMPLETE: no {PIPELINE_READY.name} marker. The local import may still be running.")
        return 2
    try:
        marker = load_json(PIPELINE_READY)
        manifest = load_json(MANIFEST_JSON)
        browser = javascript_manifest(MANIFEST_JS)
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as error:
        print(f"NOT COMPLETE: cannot read pipeline metadata: {error}")
        return 2

    if marker.get("pipelineVersion") != CONVERSION_PIPELINE_VERSION:
        issue(f"wrong pipeline version: {marker.get('pipelineVersion')}")
    if marker.get("failedConversionModels") != 0 or marker.get("stagedModels") != 0:
        issue("pipeline marker has conversion failures or staged models")
    if not isinstance(manifest, list) or not manifest:
        issue("browser model manifest is empty")
        manifest = []
    if browser != manifest:
        issue("index JavaScript and JSON model manifests differ")
    if marker.get("activeModels") != len(manifest):
        issue(f"pipeline lists {marker.get('activeModels')} active models but manifest has {len(manifest)}")
    if marker.get("selectedModels") != len(manifest):
        issue("pipeline selection count differs from published manifest")

    catalog = local_root / "model_catalog.tsv"
    metadata_file = local_root / "switch-model-metadata.json"
    try:
        catalog_rows = catalog.read_text(encoding="utf-8").splitlines()
        metadata = load_json(metadata_file)
    except (OSError, ValueError) as error:
        issue(f"native app offline catalog/metadata unavailable: {error}")
        catalog_rows, metadata = [], []

    catalog_by_key: dict[tuple[int, str], str] = {}
    for line in catalog_rows[1:]:
        fields = line.split("\t")
        if len(fields) < 4 or not fields[0].isdigit():
            issue(f"bad catalog row: {line[:100]}")
            continue
        key = (int(fields[0]), fields[2])
        catalog_by_key[key] = fields[3].replace("\\", "/")

    if not isinstance(metadata, list):
        issue("native animation metadata is not an array")
        metadata = []
    metadata_keys = {(int(e["dex"]), str(e["form"])) for e in metadata}
    browser_keys = set()
    inspected = 0

    for entry in manifest:
        try:
            dex, form = int(entry["dex"]), str(entry["form"])
            key = (dex, form)
            if key in browser_keys:
                issue(f"duplicate manifest key {key}")
            browser_keys.add(key)
            if not 1 <= dex <= 1025 or form != "regular":
                issue(f"not a regular Switch Pokémon model: {key}")
                continue
            if entry.get("ready") is False or entry.get("valid") is False:
                issue(f"{key}: model is staged/invalid")
            idle = entry.get("idleAnimation")
            if not isinstance(idle, str) or not idle:
                issue(f"{key}: no designated idle animation")
                continue
            relative = f"switch/{dex:04d}/regular.glb"
            expected_url = "web/models/" + relative
            if entry.get("url") != expected_url:
                issue(f"{key}: unexpected model URL {entry.get('url')}")
            web_model = WEB_ROOT / f"{dex:04d}" / "regular.glb"
            native_model = local_root / relative
            if not web_model.is_file() or not native_model.is_file():
                issue(f"{key}: missing web/native GLB")
                continue
            if catalog_by_key.get(key) != relative:
                issue(f"{key}: missing/incorrect native catalog entry")
            if key not in metadata_keys:
                issue(f"{key}: missing native animation metadata")
            if web_model.stat().st_size != native_model.stat().st_size:
                issue(f"{key}: web and native models have different sizes")
            elif deep and sha256_file(web_model) != sha256_file(native_model):
                issue(f"{key}: web and native models have different content")
            for detail in inspect_glb(web_model, idle):
                issue(f"{key}: {detail}")
            inspected += 1
        except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
            issue(f"manifest entry cannot be verified: {error}")

    if set(catalog_by_key) != browser_keys:
        issue(f"native catalog differs: {len(set(catalog_by_key) - browser_keys)} extra, "
              f"{len(browser_keys - set(catalog_by_key))} missing")
    if metadata_keys != browser_keys:
        issue(f"native metadata differs: {len(metadata_keys ^ browser_keys)} mismatched models")

    print(f"Switch baseline: checked {inspected}/{len(manifest)} regular model(s).")
    print(f"Browser index: {len(manifest)} models. Native catalog: {len(catalog_by_key)} models.")
    print(f"Source pipeline: v{CONVERSION_PIPELINE_VERSION}, marker {PIPELINE_READY.name}.")
    if problems:
        print(f"FAILED: {len(problems)} issue(s).")
        for problem in problems[:MAX_DETAILS]:
            print(" - " + problem)
        if len(problems) > MAX_DETAILS:
            print(f" - ... {len(problems) - MAX_DETAILS} additional issue(s)")
        return 1
    print("PASS: model files, embedded albedo, idle animations, and web/native copies verified.")
    return 0


def self_test() -> None:
    assert CONVERSION_PIPELINE_VERSION > 0
    assert isinstance(javascript_manifest, type(self_test))
    assert material_texture_coverage({"materials": [], "textures": []}) == (0, 0)
    print("Switch baseline verifier self-test passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quick", action="store_true", help="skip full SHA-256 parity checks")
    parser.add_argument(
        "--offline-root",
        type=Path,
        default=Path(os.environ.get("LOCALAPPDATA", "")) / "Pokedex3DMax" / "offline-models",
        help="native runtime offline-models directory",
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()
        raise SystemExit(0)
    raise SystemExit(verify(args.offline_root, deep=not args.quick))
