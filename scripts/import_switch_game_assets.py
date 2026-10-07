#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "switch-game-assets"
TOOLS = ROOT / ".tools"
WEB_ROOT = ROOT / "web" / "models" / "switch"
MANIFEST_JSON = ROOT / "web" / "models" / "switch-manifest.json"
MANIFEST_JS = ROOT / "web" / "models" / "switch-manifest.js"
ADDON_DIR = TOOLS / "pokemon_switch_model_importer"
ADDON_REPO = "https://github.com/ChicoEevee/Pokemon-Switch-Model-Importer-Blender.git"
BLENDER_DEPS = CACHE / "blender-python-deps"

MODEL_EXTS = {".trmdl", ".gfbmdl"}
ANIM_EXTS = {".tranm", ".gfbanm"}
DEX_RE = re.compile(r"pm(\d{4})", re.I)
FORM_RE = re.compile(r"pm\d{4}(?:_(\d{2}))?(?:_(\d{2}))?", re.I)
SAFE_RE = re.compile(r"[^a-z0-9_-]+")

SOURCE_PRIORITY = {
    "za": 600,
    "sv": 500,
    "la": 400,
    "swsh": 300,
    "lgpe": 200,
    "bdsp": 100,
    "unknown": 0,
}


def slug(value: str) -> str:
    value = SAFE_RE.sub("-", value.strip().lower()).strip("-")
    return value or "regular"


def detect_game(path: Path) -> str:
    text = str(path).lower().replace("_", "-")
    name = path.name.lower()
    if any(x in text for x in ("legends-z-a", "legends-za", "z-a-poke", "za-poke")) or name.startswith("za-"):
        return "za"
    if any(x in text for x in ("scarlet", "violet", "-sv-", "sv-poke")):
        return "sv"
    if any(x in text for x in ("legends-arceus", "la-poke", "pla-")) or name.startswith("la-"):
        return "la"
    if any(x in text for x in ("sword", "shield", "swsh")):
        return "swsh"
    if any(x in text for x in ("lets-go", "let's-go", "lgpe")):
        return "lgpe"
    if any(x in text for x in ("brilliant-diamond", "shining-pearl", "bdsp")):
        return "bdsp"
    return "unknown"


def extract_input(source: Path) -> tuple[Path, str]:
    source = source.expanduser().resolve()
    game = detect_game(source)
    if source.is_dir():
        return source, game
    if not source.is_file():
        raise FileNotFoundError(source)

    dest = CACHE / slug(source.stem)
    marker = dest / ".complete"
    if marker.is_file():
        return dest, game

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    suffix = source.suffix.lower()
    if suffix == ".zip":
        print(f"Extracting {source.name} ...", flush=True)
        with zipfile.ZipFile(source) as zf:
            zf.extractall(dest)
    elif suffix == ".7z":
        seven = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
        if not seven:
            raise RuntimeError(
                f"{source.name} is a 7z archive. Install 7-Zip or extract it manually and pass the folder."
            )
        print(f"Extracting {source.name} ...", flush=True)
        subprocess.run([seven, "x", "-y", f"-o{dest}", str(source)], check=True)
    else:
        raise RuntimeError(f"Unsupported input archive: {source.name}")

    marker.write_text("ok\n", encoding="utf-8")
    return dest, game


def infer_form(path: Path) -> str:
    candidates = [path.stem] + [p.name for p in path.parents][:5]
    for value in candidates:
        match = FORM_RE.search(value)
        if not match:
            continue
        parts = [part for part in match.groups() if part is not None]
        if not parts or all(part == "00" for part in parts):
            return "regular"
        return "form-" + "-".join(parts)
    return "regular"


def scan_models(root: Path, game: str) -> list[dict]:
    jobs: list[dict] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MODEL_EXTS:
            continue
        if "_rare" in path.name.lower():
            continue
        match = DEX_RE.search(str(path))
        if not match:
            continue
        dex = int(match.group(1))
        if dex <= 0 or dex > 2000:
            continue
        jobs.append(
            {
                "dex": dex,
                "form": infer_form(path),
                "game": game,
                "source": str(path),
                "extension": path.suffix.lower(),
            }
        )
    return jobs



def scan_animations(root: Path, game: str) -> list[dict]:
    animations: list[dict] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in ANIM_EXTS:
            continue
        match = DEX_RE.search(str(path))
        if not match:
            continue
        dex = int(match.group(1))
        if dex <= 0 or dex > 2000:
            continue
        animations.append(
            {
                "dex": dex,
                "form": infer_form(path),
                "game": game,
                "source": str(path),
                "name": path.stem,
                "extension": path.suffix.lower(),
            }
        )
    return animations


def animation_score(item: dict) -> tuple[int, int, str]:
    """Prefer calm/idle clips and then shorter, simpler filenames."""
    name = item["name"].lower()
    score = 0
    preferred = (
        ("idle", 1000),
        ("wait", 950),
        ("stand", 900),
        ("battlewait", 875),
        ("battle_wait", 875),
        ("breath", 850),
        ("rest", 800),
        ("loop", 500),
    )
    bad = ("attack", "damage", "faint", "death", "down", "hit", "move", "run", "walk", "jump")
    for token, value in preferred:
        if token in name:
            score = max(score, value)
    if any(token in name for token in bad):
        score -= 300
    return (score, -len(name), name)


def attach_animations(jobs: list[dict], animations: list[dict], max_clips: int = 6) -> None:
    by_exact: dict[tuple[int, str], list[dict]] = {}
    by_dex: dict[int, list[dict]] = {}
    for anim in animations:
        by_exact.setdefault((anim["dex"], anim["form"]), []).append(anim)
        by_dex.setdefault(anim["dex"], []).append(anim)

    for job in jobs:
        exact = by_exact.get((job["dex"], job["form"]), [])
        candidates = exact or by_dex.get(job["dex"], [])
        candidates = sorted(candidates, key=animation_score, reverse=True)

        # Keep a small useful set: one best idle-like clip plus a few distinct
        # alternatives. This avoids exploding GLB size while getting models out
        # of bind pose immediately.
        selected: list[dict] = []
        seen_names: set[str] = set()
        for anim in candidates:
            name = anim["name"].lower()
            if name in seen_names:
                continue
            selected.append(anim)
            seen_names.add(name)
            if len(selected) >= max_clips:
                break

        job["animations"] = selected


def dedupe_jobs(jobs: list[dict]) -> list[dict]:
    chosen: dict[tuple[int, str], dict] = {}
    for job in jobs:
        key = (job["dex"], job["form"])
        current = chosen.get(key)
        if current is None:
            chosen[key] = job
            continue
        incoming = SOURCE_PRIORITY.get(job["game"], 0)
        existing = SOURCE_PRIORITY.get(current["game"], 0)
        if incoming > existing:
            chosen[key] = job
        elif incoming == existing and len(job["source"]) < len(current["source"]):
            chosen[key] = job
    return sorted(chosen.values(), key=lambda item: (item["dex"], item["form"]))


def ensure_addon() -> Path:
    init_py = ADDON_DIR / "__init__.py"
    if init_py.is_file():
        return ADDON_DIR
    TOOLS.mkdir(parents=True, exist_ok=True)
    if ADDON_DIR.exists():
        shutil.rmtree(ADDON_DIR)
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is required to fetch the Pokémon Switch Blender importer.")
    print("Downloading Pokémon Switch model importer ...", flush=True)
    subprocess.run([git, "clone", "--depth", "1", ADDON_REPO, str(ADDON_DIR)], check=True)
    if not init_py.is_file():
        raise RuntimeError("Model importer checkout was incomplete")
    return ADDON_DIR



def ensure_blender_python_deps() -> Path:
    """Install pure-Python importer dependencies outside Blender.

    Blender 4.5 blocks add-ons from fetching Python packages when Online Access
    is disabled. Install flatbuffers with the normal setup Python instead, then
    put that directory on Blender's sys.path before registering the importer.
    """
    marker = BLENDER_DEPS / ".flatbuffers-ready"
    if marker.is_file():
        return BLENDER_DEPS

    BLENDER_DEPS.mkdir(parents=True, exist_ok=True)

    # Verify an existing cached install before touching the network.
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(BLENDER_DEPS)!r}); "
                "import flatbuffers; print(flatbuffers.__version__)"
            ),
        ],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        marker.write_text("ok\n", encoding="utf-8")
        print(f"Blender dependency cache already has flatbuffers ({probe.stdout.strip()}).", flush=True)
        return BLENDER_DEPS

    print("Installing flatbuffers for Blender importer (outside Blender) ...", flush=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--upgrade",
        "--target",
        str(BLENDER_DEPS),
        "flatbuffers",
    ]
    result = subprocess.run(cmd)
    if result.returncode:
        raise RuntimeError("Could not install the flatbuffers dependency required by the Blender importer.")

    verify = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(BLENDER_DEPS)!r}); "
                "import flatbuffers; print(flatbuffers.__version__)"
            ),
        ],
        capture_output=True,
        text=True,
    )
    if verify.returncode:
        raise RuntimeError("flatbuffers installed, but the dependency cache could not import it.")

    marker.write_text("ok\n", encoding="utf-8")
    print(f"flatbuffers ready for Blender ({verify.stdout.strip()}).", flush=True)
    return BLENDER_DEPS


def find_blender(explicit: str | None) -> str:
    candidates = [explicit, os.environ.get("BLENDER"), shutil.which("blender")]
    if os.name == "nt":
        program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        blender_root = program_files / "Blender Foundation"
        if blender_root.exists():
            for exe in sorted(blender_root.glob("Blender */blender.exe"), reverse=True):
                candidates.append(str(exe))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
        if candidate and shutil.which(candidate):
            return str(shutil.which(candidate))
    raise RuntimeError("Blender was not found. Install Blender 3.6+ or pass --blender PATH.")


def run_blender(jobs: list[dict], blender: str, addon: Path, blender_deps: Path) -> None:
    WEB_ROOT.mkdir(parents=True, exist_ok=True)
    payload = []
    for job in jobs:
        out = WEB_ROOT / f"{job['dex']:04d}" / f"{job['form']}.glb"
        if out.is_file() and out.stat().st_size > 1024:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        payload.append({**job, "output": str(out)})

    if not payload:
        print("All selected models are already converted.")
        return

    jobs_file = CACHE / "switch-model-jobs.json"
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    helper = ROOT / "scripts" / "blender_import_switch_game_model.py"
    cmd = [
        blender,
        "--background",
        "--python",
        str(helper),
        "--",
        str(jobs_file),
        str(addon.parent),
        addon.name,
        str(blender_deps),
    ]
    print(f"Converting {len(payload)} Switch models in one Blender session ...", flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode:
        raise RuntimeError(f"Blender conversion failed with code {result.returncode}")


def parse_glb_doc(path: Path) -> dict:
    import struct

    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("not a GLB")
    _, version, total = struct.unpack_from("<III", data, 0)
    if version != 2 or total > len(data):
        raise ValueError("invalid GLB")
    offset = 12
    while offset + 8 <= total:
        length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + length]
        offset += length
        if chunk_type == 0x4E4F534A:
            return json.loads(chunk.rstrip(b" \t\r\n\x00").decode("utf-8"))
    raise ValueError("GLB JSON chunk missing")


def choose_idle(names: list[str]) -> str | None:
    patterns = [r"(^|[|_])idle($|[|_])", r"wait|stand|breath", r"fight[_-]?a|battle[_-]?a"]
    for pattern in patterns:
        rx = re.compile(pattern, re.I)
        for name in names:
            if rx.search(name):
                return name
    return None


def build_manifest(jobs: list[dict], allow_static: bool) -> list[dict]:
    entries: list[dict] = []
    for job in jobs:
        glb = WEB_ROOT / f"{job['dex']:04d}" / f"{job['form']}.glb"
        if not glb.is_file() or glb.stat().st_size <= 1024:
            continue
        try:
            doc = parse_glb_doc(glb)
        except Exception as exc:
            print(f"Skipping damaged GLB {glb}: {exc}")
            continue
        animations = [
            {"name": animation.get("name") or f"animation_{index}"}
            for index, animation in enumerate(doc.get("animations") or [])
        ]
        names = [a["name"] for a in animations]
        idle = choose_idle(names)
        ready = bool(idle or animations) or allow_static
        entries.append(
            {
                "dex": job["dex"],
                "form": job["form"],
                "url": f"web/models/switch/{job['dex']:04d}/{job['form']}.glb",
                "source": f"official-game-assets:{job['game']}",
                "sourceGame": job["game"],
                "sourceFormat": job["extension"],
                "animations": animations,
                "idleAnimation": idle,
                "idleBreaks": [],
                "ready": ready,
                "valid": True,
                "warnings": [] if ready else [
                    "Model imported successfully but no animation clip is attached yet; kept staged to avoid showing a bind/T-pose."
                ],
            }
        )
    return entries


def write_manifest(entries: list[dict]) -> None:
    MANIFEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_JSON.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    MANIFEST_JS.write_text(
        "window.POKEDEX3D_SWITCH_MODELS = " + json.dumps(entries, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


def install_desktop(entries: list[dict]) -> None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return
    root = Path(local) / "Pokedex3DMax" / "offline-models"
    root.mkdir(parents=True, exist_ok=True)
    catalog = root / "model_catalog.tsv"

    existing: dict[tuple[int, str], list[str]] = {}
    if catalog.is_file():
        for line in catalog.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) >= 4 and cols[0].isdigit():
                existing[(int(cols[0]), cols[2])] = cols[:4]

    for entry in entries:
        if entry.get("ready") is False:
            continue
        src = ROOT / entry["url"]
        rel = Path("switch") / f"{entry['dex']:04d}" / f"{entry['form']}.glb"
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        existing[(entry["dex"], entry["form"])] = [
            str(entry["dex"]),
            f"#{entry['dex']:04d}",
            entry["form"],
            rel.as_posix(),
        ]

    rows = ["dex\tname\tform\tpath"]
    rows.extend("\t".join(cols) for _, cols in sorted(existing.items()))
    catalog.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Pokémon Switch game model assets into Pokedex 3D Max"
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="ZIP/7z archives or extracted folders")
    parser.add_argument("--blender", help="path to blender executable")
    parser.add_argument("--limit", type=int, default=0, help="convert only the first N deduplicated models")
    parser.add_argument("--dex", type=int, action="append", default=[], help="only convert selected National Dex number; repeatable")
    parser.add_argument("--inventory-only", action="store_true", help="scan sources without running Blender")
    parser.add_argument(
        "--allow-static",
        action="store_true",
        help="activate models with no animation clips (normally staged but disabled to prevent T-poses)",
    )
    parser.add_argument("--no-desktop-install", action="store_true")
    args = parser.parse_args()

    all_jobs: list[dict] = []
    all_animations: list[dict] = []
    for source in args.inputs:
        root, game = extract_input(source)
        found = scan_models(root, game)
        anims = scan_animations(root, game)
        print(f"{source.name}: {len(found)} model files, {len(anims)} animation files ({game})")
        all_jobs.extend(found)
        all_animations.extend(anims)

    jobs = dedupe_jobs(all_jobs)
    attach_animations(jobs, all_animations)
    if args.dex:
        wanted = set(args.dex)
        jobs = [job for job in jobs if job["dex"] in wanted]
    if args.limit > 0:
        jobs = jobs[: args.limit]

    models_with_anim = sum(1 for job in jobs if job.get("animations"))
    print(f"Selected {len(jobs)} unique Pokémon/form model jobs; {models_with_anim} have matching animation candidates")
    if args.inventory_only:
        inventory = CACHE / "switch-model-inventory.json"
        inventory.parent.mkdir(parents=True, exist_ok=True)
        inventory.write_text(json.dumps(jobs, indent=2) + "\n", encoding="utf-8")
        print(f"Inventory: {inventory}")
        return 0

    if not jobs:
        return 0

    blender = find_blender(args.blender)
    addon = ensure_addon()
    blender_deps = ensure_blender_python_deps()
    run_blender(jobs, blender, addon, blender_deps)
    entries = build_manifest(jobs, args.allow_static)
    write_manifest(entries)
    if not args.no_desktop_install:
        install_desktop(entries)

    ready = sum(1 for entry in entries if entry.get("ready") is not False)
    staged = len(entries) - ready
    print(f"Imported {len(entries)} models: {ready} active, {staged} staged awaiting animations")
    print(f"Manifest: {MANIFEST_JSON}")
    if staged and not args.allow_static:
        print("Staged models are intentionally not selected by the app until animations are attached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
