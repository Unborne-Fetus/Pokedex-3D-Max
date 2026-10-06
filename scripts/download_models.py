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
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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


def download_one(entry: dict, target: Path, retries: int = 3) -> tuple[dict, int]:
    relative = Path(entry["relative"])
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and destination.stat().st_size > 0:
        return entry, destination.stat().st_size

    tmp = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            data = fetch_bytes(entry["url"], timeout=120)
            if len(data) < 20:
                raise IOError(f"download too small ({len(data)} bytes)")
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
    with manifest.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("dex\tname\tform\tpath\tbytes\n")
        for entry, size in successes:
            handle.write(
                f"{entry['dex']}\t{entry['name']}\t{entry['form']}\t"
                f"{entry['relative']}\t{size}\n"
            )

    metadata = {
        "source": ASSET_REPO,
        "catalog": API_URL,
        "modelCount": len(successes),
        "failedCount": len(failures),
        "totalBytes": sum(size for _, size in successes),
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
