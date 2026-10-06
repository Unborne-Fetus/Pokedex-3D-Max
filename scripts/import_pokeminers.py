#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "pokeminers-pogo-assets"
POKEMON_SUBDIR = Path("3D Assets") / "Pokemon"
OUTPUT_ROOT = ROOT / "web" / "models" / "pokeminers"
MANIFEST_JSON = ROOT / "web" / "models" / "pokeminers-manifest.json"
MANIFEST_JS = ROOT / "web" / "models" / "pokeminers-manifest.js"
JOBS_JSON = ROOT / ".cache" / "pokeminers-jobs.json"

RIG_RE = re.compile(r"^pm(?P<dex>\d{4})_(?P<form>\d{2})_Rig$")


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd or ROOT)
    if result.returncode:
        raise RuntimeError(f"Command failed with code {result.returncode}: {' '.join(cmd)}")


def sparse_patterns(start_dex: int, end_dex: int) -> list[str]:
    if start_dex and end_dex and end_dex >= start_dex:
        return [
            f"/3D Assets/Pokemon/pm{dex:04d}_*_Rig/"
            for dex in range(start_dex, end_dex + 1)
        ]
    return ["/3D Assets/Pokemon/"]


def configure_sparse_checkout(start_dex: int, end_dex: int) -> None:
    patterns = sparse_patterns(start_dex, end_dex)
    run(["git", "sparse-checkout", "init", "--no-cone"], CACHE)
    run(["git", "sparse-checkout", "set", "--no-cone", *patterns], CACHE)


def ensure_source(update: bool, start_dex: int, end_dex: int) -> Path:
    pokemon_dir = CACHE / POKEMON_SUBDIR

    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        run([
            "git", "clone",
            "--filter=blob:none",
            "--no-checkout",
            "https://github.com/PokeMiners/pogo_assets.git",
            str(CACHE),
        ])
        configure_sparse_checkout(start_dex, end_dex)
        run(["git", "checkout", "master"], CACHE)
    else:
        if update:
            run(["git", "fetch", "origin", "master"], CACHE)
            run(["git", "reset", "--hard", "origin/master"], CACHE)
        configure_sparse_checkout(start_dex, end_dex)
        run(["git", "checkout", "master"], CACHE)

    if not pokemon_dir.is_dir():
        raise RuntimeError(f"PokeMiners Pokemon folder not found: {pokemon_dir}")

    return pokemon_dir


def form_name(code: str) -> str:
    if code == "00":
        return "regular"
    return f"go-form-{code}"


def find_blender(explicit: str | None) -> str:
    if explicit:
        return explicit

    found = shutil.which("blender")
    if found:
        return found

    candidates = [
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Blender Foundation",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Blender Foundation",
    ]
    for root in candidates:
        if not root.exists():
            continue
        for exe in sorted(root.glob("Blender */blender.exe"), reverse=True):
            return str(exe)

    raise RuntimeError(
        "Blender was not found. Install Blender or pass --blender PATH_TO_blender.exe"
    )


def make_jobs(pokemon_dir: Path, limit: int, start_dex: int, end_dex: int) -> list[dict]:
    jobs: list[dict] = []

    for rig_dir in sorted(pokemon_dir.iterdir()):
        if not rig_dir.is_dir():
            continue

        match = RIG_RE.match(rig_dir.name)
        if not match:
            continue

        dex = int(match.group("dex"))
        code = match.group("form")

        if start_dex and dex < start_dex:
            continue
        if end_dex and dex > end_dex:
            continue

        fbx = rig_dir / f"{rig_dir.name}.fbx"
        if not fbx.is_file():
            continue

        form = form_name(code)
        output = OUTPUT_ROOT / f"{dex:04d}" / f"{form}.glb"

        textures = sorted(
            str(path)
            for path in rig_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tga"}
        )

        jobs.append({
            "dex": dex,
            "formCode": code,
            "form": form,
            "sourceDir": str(rig_dir),
            "fbx": str(fbx),
            "textures": textures,
            "output": str(output),
        })

        if limit and len(jobs) >= limit:
            break

    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bulk-import Pokemon GO FBX rigs from PokeMiners into web-ready GLBs"
    )
    parser.add_argument("--blender", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-dex", type=int, default=0)
    parser.add_argument("--end-dex", type=int, default=0)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    pokemon_dir = ensure_source(args.update, args.start_dex, args.end_dex)
    blender = find_blender(args.blender)
    jobs = make_jobs(
        pokemon_dir,
        args.limit,
        args.start_dex,
        args.end_dex,
    )

    if not jobs:
        print("No PokeMiners Pokemon rigs matched the requested range.")
        return 0

    if not args.force:
        pending = [job for job in jobs if not Path(job["output"]).is_file()]
    else:
        pending = jobs

    print(f"Found {len(jobs)} rig/form folders.")
    print(f"Need to convert {len(pending)} models.")
    print(f"Output: {OUTPUT_ROOT}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    JOBS_JSON.parent.mkdir(parents=True, exist_ok=True)
    JOBS_JSON.write_text(
        json.dumps({
            "jobs": pending,
            "manifestJobs": jobs,
            "manifestJson": str(MANIFEST_JSON),
            "manifestJs": str(MANIFEST_JS),
        }, indent=2),
        encoding="utf-8",
    )

    if pending:
        helper = ROOT / "scripts" / "blender_batch_convert_pokeminers.py"
        run([
            blender,
            "--background",
            "--python",
            str(helper),
            "--",
            str(JOBS_JSON),
        ])

    if not MANIFEST_JSON.is_file():
        raise RuntimeError("Bulk conversion finished without generating a manifest.")

    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    converted = sum(1 for item in manifest if item.get("valid"))
    failed = len(manifest) - converted

    print()
    print("PokeMiners bulk import complete")
    print(f"  Manifest entries: {len(manifest)}")
    print(f"  Valid converted models: {converted}")
    print(f"  Missing/failed: {failed}")
    print(f"  Manifest: {MANIFEST_JSON}")
    print()
    print("Open index.html (or your local web server) and the web viewer will")
    print("automatically prefer these models over the old remote fallback assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
