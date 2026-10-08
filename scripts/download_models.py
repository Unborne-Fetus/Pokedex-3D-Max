#!/usr/bin/env python3
"""
Download the complete Pokedex 3D Max offline model pack.

Source:
  https://github.com/Pokemon-3D-api/assets
Catalog:
  https://pokemon-3d-api.onrender.com/v1/pokemon

The generated pack is intentionally kept out of Git history. It can be used by the
Android and Windows builds and can be archived as a release artifact.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
import shutil
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

API_URL = "https://pokemon-3d-api.onrender.com/v1/pokemon"
ASSET_REPO = "https://github.com/Pokemon-3D-api/assets"
ASSET_LICENSE_URL = "https://raw.githubusercontent.com/Pokemon-3D-api/assets/main/LICENSE"
USER_AGENT = "Pokedex-3D-Max/0.1 offline-model-pack-builder"


def normalize_url(url: str) -> str:
    return (
        url.replace("/refs/heads/main/heads/main/", "/refs/heads/main/")
        .replace("/main/heads/main/", "/main/")
    )


def fetch_bytes(url: str, timeout: int = 90) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def load_catalog() -> list[dict]:
    raw = fetch_bytes(API_URL, timeout=60)
    decoded = json.loads(raw.decode("utf-8"))

    if isinstance(decoded, list):
        return decoded

    if isinstance(decoded, dict):
        pokemon = decoded.get("pokemon")
        if isinstance(pokemon, list):
            return pokemon

        data = decoded.get("data")
        if isinstance(data, list):
            return data

    raise ValueError(
        "Unsupported catalog JSON shape: expected a top-level list "
        "or an object containing a 'pokemon'/'data' list"
    )


def local_relative_path(model_url: str, dex: int, form_name: str, index: int) -> Path:
    parsed = urllib.parse.urlparse(model_url)
    marker = "/models/opt/"
    if marker in parsed.path:
        suffix = parsed.path.split(marker, 1)[1]
        return Path("models") / "opt" / Path(suffix)

    safe_form = "".join(c if c.isalnum() or c in "-_" else "_" for c in form_name)
    return Path("models") / "opt" / safe_form / f"{dex}-{index}.glb"


def clean_field(value: str) -> str:
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _align4(data: bytearray) -> None:
    while len(data) % 4:
        data.append(0)


def prepare_glb_for_desktop(data: bytes) -> tuple[bytes, bool]:
    """Replace required EXT_texture_webp images with embedded PNG images."""
    if len(data) < 20 or data[:4] != b"glTF":
        return data, False

    _, version, total_length = struct.unpack_from("<III", data, 0)
    if version != 2 or total_length > len(data):
        return data, False

    offset = 12
    chunks: list[tuple[int, bytes]] = []
    while offset + 8 <= total_length:
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk_data = data[offset : offset + chunk_length]
        offset += chunk_length
        chunks.append((chunk_type, chunk_data))

    json_index = next((i for i, item in enumerate(chunks) if item[0] == 0x4E4F534A), None)
    bin_index = next((i for i, item in enumerate(chunks) if item[0] == 0x004E4942), None)
    if json_index is None or bin_index is None:
        return data, False

    doc = json.loads(chunks[json_index][1].rstrip(b" \t\r\n\x00").decode("utf-8"))
    required = doc.get("extensionsRequired") or []
    used = doc.get("extensionsUsed") or []
    if "EXT_texture_webp" not in required and "EXT_texture_webp" not in used:
        return data, False

    if Image is None:
        raise RuntimeError(
            "This model requires EXT_texture_webp. Install Pillow so the setup can "
            "convert embedded WebP textures to PNG for the Windows renderer."
        )

    images = doc.get("images") or []
    buffer_views = doc.get("bufferViews") or []
    textures = doc.get("textures") or []
    binary = bytearray(chunks[bin_index][1])

    converted_sources: dict[int, int] = {}

    for image_index, image in enumerate(images):
        if image.get("mimeType") != "image/webp":
            continue
        view_index = image.get("bufferView")
        if not isinstance(view_index, int) or not (0 <= view_index < len(buffer_views)):
            continue

        view = buffer_views[view_index]
        start = int(view.get("byteOffset", 0))
        length = int(view.get("byteLength", 0))
        webp = bytes(binary[start : start + length])

        with Image.open(BytesIO(webp)) as source:
            output = BytesIO()
            source.convert("RGBA").save(output, format="PNG", optimize=True)
            png = output.getvalue()

        _align4(binary)
        png_offset = len(binary)
        binary.extend(png)
        _align4(binary)

        new_view_index = len(buffer_views)
        buffer_views.append(
            {
                "buffer": int(view.get("buffer", 0)),
                "byteOffset": png_offset,
                "byteLength": len(png),
            }
        )
        image["bufferView"] = new_view_index
        image["mimeType"] = "image/png"
        converted_sources[image_index] = image_index

    for texture in textures:
        extensions = texture.get("extensions")
        if not isinstance(extensions, dict):
            continue
        webp_ext = extensions.get("EXT_texture_webp")
        if isinstance(webp_ext, dict):
            source_index = webp_ext.get("source")
            if isinstance(source_index, int) and source_index in converted_sources:
                texture["source"] = converted_sources[source_index]
                extensions.pop("EXT_texture_webp", None)
                if not extensions:
                    texture.pop("extensions", None)

    doc["extensionsRequired"] = [x for x in required if x != "EXT_texture_webp"]
    doc["extensionsUsed"] = [x for x in used if x != "EXT_texture_webp"]
    if not doc["extensionsRequired"]:
        doc.pop("extensionsRequired", None)
    if not doc["extensionsUsed"]:
        doc.pop("extensionsUsed", None)

    if doc.get("buffers"):
        doc["buffers"][0]["byteLength"] = len(binary)

    json_bytes = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    json_padding = (-len(json_bytes)) % 4
    json_bytes += b" " * json_padding
    _align4(binary)

    rebuilt = bytearray()
    rebuilt.extend(struct.pack("<III", 0x46546C67, 2, 0))
    rebuilt.extend(struct.pack("<II", len(json_bytes), 0x4E4F534A))
    rebuilt.extend(json_bytes)
    rebuilt.extend(struct.pack("<II", len(binary), 0x004E4942))
    rebuilt.extend(binary)
    struct.pack_into("<I", rebuilt, 8, len(rebuilt))
    return bytes(rebuilt), True


def download_one(entry: dict, target: Path, retries: int = 3) -> tuple[dict, int]:
    relative = Path(entry["relative"])
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and destination.stat().st_size > 0:
        existing = destination.read_bytes()
        prepared, changed = prepare_glb_for_desktop(existing)
        if changed:
            tmp = destination.with_suffix(destination.suffix + ".part")
            tmp.write_bytes(prepared)
            tmp.replace(destination)
        return entry, destination.stat().st_size

    tmp = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            data = fetch_bytes(entry["url"], timeout=120)
            if len(data) < 20:
                raise IOError(f"download too small ({len(data)} bytes)")
            data, _ = prepare_glb_for_desktop(data)
            tmp.write_bytes(data)
            tmp.replace(destination)
            return entry, len(data)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if tmp.exists():
                tmp.unlink()
            if attempt != retries:
                time.sleep(attempt * 1.5)

    raise RuntimeError(f"failed {entry['url']}: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        default="offline-models",
        help="output directory (default: offline-models)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(12, max(4, (os.cpu_count() or 4))),
        help="parallel downloads",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="optional number of models to download for testing; 0 downloads all",
    )
    args = parser.parse_args()

    target = Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)

    print(f"Loading catalog from {API_URL}", flush=True)
    pokemon = load_catalog()

    entries: list[dict] = []
    seen: set[tuple[int, str, str]] = set()

    for pokemon_entry in pokemon:
        dex = int(pokemon_entry["id"])
        forms = pokemon_entry.get("forms", [])
        for index, form in enumerate(forms):
            url = normalize_url(str(form.get("model", "")).strip())
            if not url:
                continue

            name = clean_field(str(form.get("name") or f"#{dex:04d}"))
            form_name = clean_field(str(form.get("formName") or "regular"))
            relative = local_relative_path(url, dex, form_name, index).as_posix()
            key = (dex, form_name, relative)
            if key in seen:
                continue
            seen.add(key)

            entries.append(
                {
                    "dex": dex,
                    "name": name,
                    "form": form_name,
                    "url": url,
                    "relative": relative,
                }
            )

    entries.sort(key=lambda e: (e["dex"], 0 if e["form"].lower() == "regular" else 1, e["form"]))
    if args.limit > 0:
        entries = entries[: args.limit]

    print(f"Downloading {len(entries)} model files with {args.workers} workers", flush=True)
    started_at = time.time()
    downloaded_bytes = 0
    successes: list[tuple[dict, int]] = []
    failures: list[str] = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {pool.submit(download_one, entry, target): entry for entry in entries}
        completed = 0
        for future in as_completed(future_map):
            entry = future_map[future]
            completed += 1
            try:
                result = future.result()
                successes.append(result)
                downloaded_bytes += result[1]
            except Exception as exc:  # noqa: BLE001
                failures.append(str(exc))

            if completed % 5 == 0 or completed == len(entries):
                elapsed = max(time.time() - started_at, 0.001)
                mib = downloaded_bytes / (1024 * 1024)
                rate = mib / elapsed
                percent = (completed / len(entries) * 100) if entries else 100.0
                print(
                    f"  {completed}/{len(entries)} ({percent:5.1f}%) | "
                    f"{mib:,.1f} MiB processed | {rate:,.1f} MiB/s | "
                    f"failures={len(failures)}",
                    flush=True,
                )

    successes.sort(
        key=lambda item: (
            item[0]["dex"],
            0 if item[0]["form"].lower() == "regular" else 1,
            item[0]["form"],
        )
    )

    manifest = target / "model_catalog.tsv"

    # Switch imports are installed before this generic pack refresh in setup-all.
    # Preserve those validated rows instead of silently erasing them. A Switch
    # row replaces the generic row for the same dex/form; staged Switch models
    # are absent from the catalog, so the generic fallback remains available.
    preserved_switch: dict[tuple[int, str], list[str]] = {}
    if manifest.is_file():
        for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) < 4 or not cols[0].isdigit():
                continue
            rel = cols[3].replace("\\", "/")
            if not rel.startswith("switch/"):
                continue
            path = target / Path(rel)
            if not path.is_file():
                continue
            size = str(path.stat().st_size)
            preserved_switch[(int(cols[0]), cols[2])] = [
                cols[0],
                cols[1],
                cols[2],
                rel,
                size,
            ]

    switch_keys = set(preserved_switch)
    generic_rows = [
        (
            int(entry["dex"]),
            str(entry["form"]),
            [
                str(entry["dex"]),
                str(entry["name"]),
                str(entry["form"]),
                str(entry["relative"]),
                str(size),
            ],
        )
        for entry, size in successes
        if (int(entry["dex"]), str(entry["form"])) not in switch_keys
    ]

    combined_rows = generic_rows + [
        (dex, form, cols)
        for (dex, form), cols in preserved_switch.items()
    ]
    combined_rows.sort(
        key=lambda item: (
            item[0],
            0 if item[1].lower() == "regular" else 1,
            item[1],
            item[2][3],
        )
    )

    temp_manifest = manifest.with_suffix(".tmp")
    with temp_manifest.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("dex\tname\tform\tpath\tbytes\n")
        for _, _, cols in combined_rows:
            handle.write("\t".join(cols) + "\n")
    temp_manifest.replace(manifest)

    metadata = {
        "source": ASSET_REPO,
        "catalog": API_URL,
        "modelCount": len(successes),
        "switchModelCount": len(preserved_switch),
        "catalogModelCount": len(combined_rows),
        "failedCount": len(failures),
        "totalBytes": sum(size for _, size in successes)
        + sum(int(cols[4]) for cols in preserved_switch.values()),
    }
    (target / "pack_info.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    attribution = (
        "Pokedex 3D Max offline model pack\n"
        f"Asset source: {ASSET_REPO}\n"
        f"Catalog source: {API_URL}\n"
        "The upstream asset repository is distributed under the MIT License.\n"
        "Pokémon names, characters, and designs belong to their respective rights holders.\n"
    )
    (target / "ASSET_SOURCE.txt").write_text(attribution, encoding="utf-8")

    try:
        (target / "UPSTREAM_LICENSE.txt").write_bytes(fetch_bytes(ASSET_LICENSE_URL))
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: could not fetch upstream license: {exc}", file=sys.stderr)

    if failures:
        (target / "failed_downloads.txt").write_text(
            "\n".join(failures) + "\n",
            encoding="utf-8",
        )

    total_gib = metadata["totalBytes"] / (1024 ** 3)
    print(
        f"Finished: {metadata['modelCount']} models, "
        f"{total_gib:.2f} GiB, {metadata['failedCount']} failures",
        flush=True,
    )

    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
