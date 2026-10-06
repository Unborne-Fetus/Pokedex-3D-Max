#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / ".cache" / "pokedex3dpro-import"
OUTPUT_ROOT = ROOT / "web" / "models" / "pokedex3dpro"
MANIFEST_JSON = ROOT / "web" / "models" / "pokedex3dpro-manifest.json"
MANIFEST_JS = ROOT / "web" / "models" / "pokedex3dpro-manifest.js"
JOBS_JSON = ROOT / ".cache" / "pokedex3dpro-jobs.json"

DEX_RE = re.compile(r"(?:^|[^0-9])#?0*(?P<dex>[1-9][0-9]{0,3})(?:[^0-9]|$)")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode:
        raise RuntimeError(
            f"Command failed with code {result.returncode}: {' '.join(cmd)}"
        )


def find_blender(explicit: str | None) -> str:
    if explicit:
        return explicit

    found = shutil.which("blender")
    if found:
        return found

    candidates = [
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Blender Foundation",
        Path(os.environ.get("PROGRAMFILES(X86", "C:/Program Files (x86)")) / "Blender Foundation",
    ]
    for root in candidates:
        if not root.exists():
            continue
        for exe in sorted(root.glob("Blender */blender.exe"), reverse=True):
            return str(exe)

    raise RuntimeError(
        "Blender was not found. Install Blender or pass --blender PATH_TO_blender.exe"
    )


def dex_from_path(path: Path) -> int | None:
    # Prefer the package folder name, then walk upward. Expected names include
    # '#0002 Ivysaur', '0002-Ivysaur', or simply '2'.
    for candidate in (path, *path.parents):
        match = DEX_RE.search(candidate.name)
        if not match:
            continue
        value = int(match.group("dex"))
        if 1 <= value <= 649:
            return value
    return None


def discover_packages(root: Path, forced_dex: int | None = None) -> list[dict]:
    jobs: list[dict] = []

    for model_dae in sorted(root.rglob("model.dae")):
        package = model_dae.parent
        anim_dae = package / "anim.dae"
        if not anim_dae.is_file():
            continue

        dex = forced_dex or dex_from_path(package)
        if not dex:
            print(f"Skipping package with unknown dex number: {package}")
            continue

        textures = sorted(
            str(path)
            for path in package.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tga"}
        )

        output = OUTPUT_ROOT / f"{dex:04d}" / "regular.glb"
        jobs.append(
            {
                "dex": dex,
                "form": "regular",
                "sourceDir": str(package.resolve()),
                "modelDae": str(model_dae.resolve()),
                "animDae": str(anim_dae.resolve()),
                "textures": textures,
                "output": str(output.resolve()),
            }
        )

    # Keep the first complete regular package for each dex.
    deduped: dict[int, dict] = {}
    for job in jobs:
        deduped.setdefault(job["dex"], job)

    return [deduped[dex] for dex in sorted(deduped)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert extracted Pokédex 3D Pro model.dae + anim.dae packages "
            "to animated web GLBs. The source packages are not downloaded by "
            "this script; place extracted packages in the input directory."
        )
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="folder containing extracted Pokédex 3D Pro packages",
    )
    parser.add_argument("--dex", type=int, default=None)
    parser.add_argument("--blender", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source_root = Path(args.input).resolve()
    if not source_root.is_dir():
        raise RuntimeError(
            f"Input folder does not exist: {source_root}\n"
            "Extract model packs so each package contains model.dae and anim.dae."
        )

    jobs = discover_packages(source_root, args.dex)
    if not jobs:
        raise RuntimeError(
            "No complete Pokédex 3D Pro packages found. "
            "Each package must contain both model.dae and anim.dae."
        )

    pending = jobs if args.force else [
        job for job in jobs if not Path(job["output"]).is_file()
    ]

    print(f"Discovered {len(jobs)} official animated package(s).")
    print(f"Need to convert {len(pending)} package(s).")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    JOBS_JSON.parent.mkdir(parents=True, exist_ok=True)
    JOBS_JSON.write_text(
        json.dumps(
            {
                "jobs": pending,
                "manifestJobs": jobs,
                "manifestJson": str(MANIFEST_JSON),
                "manifestJs": str(MANIFEST_JS),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if pending:
        blender = find_blender(args.blender)
        helper = ROOT / "scripts" / "blender_import_pokedex3dpro.py"
        run(
            [
                blender,
                "--background",
                "--python",
                str(helper),
                "--",
                str(JOBS_JSON),
            ]
        )

    if not MANIFEST_JSON.is_file():
        raise RuntimeError("Conversion finished without generating a manifest.")

    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    valid = [item for item in manifest if item.get("valid")]
    print(f"Valid official animated models: {len(valid)}/{len(manifest)}")

    if not valid:
        raise RuntimeError("No valid official animated models were produced.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
