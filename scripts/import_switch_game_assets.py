#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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
ADDON_REV = "b0c98d9fcaab85a04ad35e2d111bae4cad6c1e04"
BLENDER_DEPS = CACHE / "blender-python-deps"
CONVERSION_CACHE = CACHE / "switch-conversion-cache.json"
CONVERSION_PIPELINE_VERSION = 3
PIPELINE_READY = CACHE / f"pipeline-v{CONVERSION_PIPELINE_VERSION}.ready.json"

MODEL_EXTS = {".trmdl", ".gfbmdl"}
ANIM_EXTS = {".tranm", ".gfbanm"}
ANIMATION_EXT_FOR_MODEL = {".trmdl": ".tranm", ".gfbmdl": ".gfbanm"}
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


def discover_default_inputs() -> list[Path]:
    """Find archives downloaded by setup-all when none are supplied explicitly."""
    roots = [
        ROOT,
        ROOT / "switch-assets",
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        ROOT / ".cache" / "mega-switch-assets",
    ]
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".zip", ".7z"}:
                continue
            if not re.search(r"(poke|pokemon)", path.stem, re.I):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(resolved)
    return sorted(found, key=lambda p: p.name.lower())


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


def archive_signature(source: Path) -> dict:
    stat = source.stat()
    return {
        "path": str(source),
        "size": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
    }


def archive_cache_dir(source: Path) -> Path:
    # Do not key extraction only by filename: two different archives can have
    # the same leaf name in Downloads and the MEGA cache.
    identity = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
    return CACHE / "extracted" / f"{slug(source.stem)}-{identity}"


def extract_input(source: Path) -> tuple[Path, str]:
    source = source.expanduser().resolve()
    game = detect_game(source)
    if source.is_dir():
        return source, game
    if not source.is_file():
        raise FileNotFoundError(source)

    dest = archive_cache_dir(source)
    marker = dest / ".complete.json"
    expected_signature = archive_signature(source)

    if marker.is_file():
        try:
            cached_signature = json.loads(marker.read_text(encoding="utf-8"))
        except Exception:
            cached_signature = None
        if cached_signature == expected_signature:
            return dest, game
        print(f"Archive changed; refreshing extracted cache for {source.name}.", flush=True)

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    suffix = source.suffix.lower()
    if suffix == ".zip":
        print(f"Extracting {source.name} ...", flush=True)
        with zipfile.ZipFile(source) as zf:
            root = dest.resolve()
            for member in zf.infolist():
                target = (dest / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise RuntimeError(
                        f"Unsafe archive path in {source.name}: {member.filename}"
                    )
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

    marker.write_text(
        json.dumps(expected_signature, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return dest, game


def infer_form_parts(path: Path) -> list[str]:
    candidates = [path.stem] + [p.name for p in path.parents][:5]
    for value in candidates:
        match = FORM_RE.search(value)
        if match:
            return [part for part in match.groups() if part is not None]
    return []


def infer_form(path: Path) -> str:
    parts = infer_form_parts(path)
    if not parts or all(part == "00" for part in parts):
        return "regular"
    return "form-" + "-".join(parts)


def infer_form_key(path: Path) -> str:
    """Canonical identity used for compatibility matching only.

    Some packs write a trailing _00 on animation names but omit it on the
    matching model. Trim only trailing zero components; never substitute a
    different non-zero form.
    """
    parts = infer_form_parts(path)
    while parts and parts[-1] == "00":
        parts.pop()
    return "-".join(parts) if parts else "regular"


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
                "formKey": infer_form_key(path),
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
                "formKey": infer_form_key(path),
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
    """Attach only animations that are compatible with the model's rig family."""
    by_key: dict[tuple[int, str, str, str], list[dict]] = {}
    for anim in animations:
        key = (
            anim["dex"],
            anim.get("formKey", anim["form"]),
            anim["game"],
            anim["extension"],
        )
        by_key.setdefault(key, []).append(anim)

    for job in jobs:
        expected_ext = ANIMATION_EXT_FOR_MODEL.get(job["extension"])
        key = (
            job["dex"],
            job.get("formKey", job["form"]),
            job["game"],
            expected_ext,
        )
        candidates = by_key.get(key, []) if expected_ext else []
        candidates = sorted(candidates, key=animation_score, reverse=True)

        selected: list[dict] = []
        seen_sources: set[str] = set()
        for anim in candidates:
            source = str(Path(anim["source"]).resolve())
            if source in seen_sources:
                continue
            selected.append(anim)
            seen_sources.add(source)
            if len(selected) >= max_clips:
                break

        job["animations"] = selected
        job["animationMatch"] = "same-game-same-form-same-format" if selected else "none"


def job_choice_score(job: dict) -> tuple[int, int, int, int]:
    animations = job.get("animations") or []
    best_animation = animation_score(animations[0])[0] if animations else -100000
    return (
        1 if animations else 0,
        SOURCE_PRIORITY.get(job["game"], 0),
        best_animation,
        -len(job["source"]),
    )


def dedupe_jobs(jobs: list[dict]) -> list[dict]:
    """Prefer one best source per canonical Pokémon/form identity."""
    chosen: dict[tuple[int, str], dict] = {}
    for job in jobs:
        key = (job["dex"], job.get("formKey", job["form"]))
        current = chosen.get(key)
        if current is None or job_choice_score(job) > job_choice_score(current):
            chosen[key] = job
    return sorted(
        chosen.values(),
        key=lambda item: (item["dex"], item.get("formKey", item["form"]), item["form"]),
    )


def patch_addon_for_batch_imports() -> None:
    """Apply small compatibility fixes to the cached third-party importer.

    Keep these local and idempotent so setup-all/manual imports behave the same
    even when the upstream checkout is freshly cloned.
    """
    switch_source = ADDON_DIR / "PokemonSwitch.py"
    if switch_source.is_file():
        text = switch_source.read_text(encoding="utf-8")

        noisy = "    print(weight_array)\n"
        if noisy in text:
            text = text.replace(noisy, "    # Suppressed huge vertex-weight debug dump for batch imports.\n")

        unsafe = '                    if mat["mat_uvindexlayermask"] != -1:\n                        material.node_tree.links.new(uv_node.outputs["UV"], lym_image_texture.inputs["Vector"])\n'
        safe = '                    if mat["mat_uvindexlayermask"] != -1 and lym_image_texture is not None:\n                        material.node_tree.links.new(uv_node.outputs["UV"], lym_image_texture.inputs["Vector"])\n'
        if unsafe in text:
            text = text.replace(unsafe, safe)

        switch_source.write_text(text, encoding="utf-8")

    # The older GFBMDL importer has its own enormous per-vertex debug print.
    gfbmdl_source = ADDON_DIR / "gfbmdl_import.py"
    if gfbmdl_source.is_file():
        text = gfbmdl_source.read_text(encoding="utf-8")
        if "    print(weight_array)\n" in text:
            text = text.replace(
                "    print(weight_array)\n",
                "    # Suppressed huge vertex-weight debug dump for batch imports.\n",
            )
        gfbmdl_source.write_text(text, encoding="utf-8")



def addon_checkout_is_usable(git: str) -> bool:
    init_py = ADDON_DIR / "__init__.py"
    anim_py = ADDON_DIR / "gfbanm_importer.py"
    if not init_py.is_file() or not anim_py.is_file():
        return False

    try:
        rev = subprocess.run(
            [git, "-C", str(ADDON_DIR), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return False
    if rev != ADDON_REV:
        return False

    # These markers are required by the batch wrapper. In particular, the
    # active-action fallback was added upstream after older cached checkouts.
    text = anim_py.read_text(encoding="utf-8", errors="replace")
    return (
        "if nla_import and action is not None:" in text
        and "Action {anim_name} created and set as active action." in text
    )


def install_pinned_addon(git: str) -> None:
    TOOLS.mkdir(parents=True, exist_ok=True)
    if ADDON_DIR.exists():
        shutil.rmtree(ADDON_DIR)

    print(f"Installing pinned Pokémon Switch importer {ADDON_REV[:12]} ...", flush=True)
    subprocess.run([git, "clone", "--no-checkout", ADDON_REPO, str(ADDON_DIR)], check=True)
    subprocess.run(
        [git, "-C", str(ADDON_DIR), "fetch", "--depth", "1", "origin", ADDON_REV],
        check=True,
    )
    subprocess.run(
        [git, "-C", str(ADDON_DIR), "checkout", "--detach", ADDON_REV],
        check=True,
    )


def ensure_addon() -> Path:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is required to fetch the Pokémon Switch Blender importer.")

    if not addon_checkout_is_usable(git):
        print(
            "Cached Pokémon Switch importer is stale or incompatible; replacing it.",
            flush=True,
        )
        install_pinned_addon(git)

    if not addon_checkout_is_usable(git):
        raise RuntimeError(
            "Pinned Pokémon Switch importer was installed but failed validation."
        )

    patch_addon_for_batch_imports()
    print(f"Using Pokémon Switch importer revision {ADDON_REV[:12]}.", flush=True)
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

    # setup-all installs a portable Blender under .tools. Reuse that exact copy
    # when the manual importer is launched directly.
    portable_root = TOOLS
    if portable_root.exists():
        portable_name = "blender.exe" if os.name == "nt" else "blender"
        for exe in sorted(
            portable_root.rglob(portable_name),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        ):
            candidates.append(str(exe))

    if os.name == "nt":
        program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        blender_root = program_files / "Blender Foundation"
        if blender_root.exists():
            for exe in sorted(blender_root.glob("Blender */blender.exe"), reverse=True):
                candidates.append(str(exe))

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            resolved = str(Path(candidate).resolve())
            print(f"Using Blender: {resolved}", flush=True)
            return resolved
        if candidate and shutil.which(candidate):
            resolved = str(Path(shutil.which(candidate)).resolve())
            print(f"Using Blender: {resolved}", flush=True)
            return resolved

    raise RuntimeError(
        "Blender was not found. Run setup-all.bat full once, install Blender 3.6+, "
        "or pass --blender PATH."
    )


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


def existing_glb_is_complete(path: Path, wants_animations: bool) -> bool:
    if not path.is_file() or path.stat().st_size <= 1024:
        return False
    try:
        doc = parse_glb_doc(path)
    except Exception:
        return False
    if wants_animations and not doc.get("animations"):
        return False
    return True


def source_signature(path_value: str) -> dict:
    path = Path(path_value).resolve()
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
    }


def job_fingerprint(job: dict) -> str:
    payload = {
        "pipeline": CONVERSION_PIPELINE_VERSION,
        "addonRevision": ADDON_REV,
        "dex": job["dex"],
        "form": job["form"],
        "formKey": job.get("formKey"),
        "game": job["game"],
        "extension": job["extension"],
        "model": source_signature(job["source"]),
        "animations": [
            {
                "name": anim.get("name"),
                "game": anim.get("game"),
                "extension": anim.get("extension"),
                "source": source_signature(anim["source"]),
            }
            for anim in (job.get("animations") or [])
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_conversion_cache() -> dict[str, str]:
    if not CONVERSION_CACHE.is_file():
        return {}
    try:
        data = json.loads(CONVERSION_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_conversion_cache(cache: dict[str, str]) -> None:
    CONVERSION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    temp = CONVERSION_CACHE.with_suffix(".tmp")
    temp.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(CONVERSION_CACHE)


def output_cache_key(job: dict) -> str:
    return f"{job['dex']:04d}/{job['form']}.glb"


def run_blender(jobs: list[dict], blender: str, addon: Path, blender_deps: Path) -> None:
    WEB_ROOT.mkdir(parents=True, exist_ok=True)
    cache = load_conversion_cache()
    payload: list[dict] = []
    reused = 0

    for job in jobs:
        out = WEB_ROOT / f"{job['dex']:04d}" / f"{job['form']}.glb"
        wants_animations = bool(job.get("animations"))
        fingerprint = job_fingerprint(job)
        cache_key = output_cache_key(job)

        if cache.get(cache_key) == fingerprint and existing_glb_is_complete(out, wants_animations):
            reused += 1
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        payload.append({
            **job,
            "output": str(out),
            "fingerprint": fingerprint,
            "cacheKey": cache_key,
        })

    if reused:
        print(f"Reusing {reused} fingerprint-matched Switch model(s).", flush=True)

    if not payload:
        print("All selected models are already converted with the current pipeline.")
        return

    jobs_file = CACHE / "switch-model-jobs.json"
    failure_path = jobs_file.with_name("switch-model-failures.json")
    if failure_path.exists():
        failure_path.unlink()

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
    print(f"Converting {len(payload)} stale/missing Switch models in one Blender session ...", flush=True)
    result = subprocess.run(cmd, cwd=ROOT)

    failed_sources: set[str] = set()
    failure_report_available = False
    if failure_path.is_file():
        try:
            failures = json.loads(failure_path.read_text(encoding="utf-8"))
            failed_sources = {
                str(Path(item["source"]).resolve())
                for item in failures
                if isinstance(item, dict) and item.get("source")
            }
            failure_report_available = True
        except Exception:
            pass

    # Persist verified successes even if another conversion in the batch failed,
    # so the next run retries only the failed jobs.
    if result.returncode == 0 or failure_report_available:
        for item in payload:
            source = str(Path(item["source"]).resolve())
            if source in failed_sources:
                continue
            out = Path(item["output"])
            if existing_glb_is_complete(out, bool(item.get("animations"))):
                cache[item["cacheKey"]] = item["fingerprint"]
        save_conversion_cache(cache)

    if result.returncode:
        count = len(failed_sources) if failure_report_available else "unknown number of"
        raise RuntimeError(
            f"Blender conversion failed with code {result.returncode}; {count} job(s) failed"
        )


def choose_idle(names: list[str]) -> str | None:
    preferred = (
        r"default(?:idle|wait)",
        r"battle(?:idle|wait)",
        r"(^|[_-])idle([0-9]*|[_-].*)?$",
        r"wait|stand|breath|rest",
        r"loop",
    )
    rejected = re.compile(
        r"attack|damage|faint|death|down|hit|move|run|walk|jump",
        re.I,
    )
    for pattern in preferred:
        rx = re.compile(pattern, re.I)
        for name in names:
            if rx.search(name) and not rejected.search(name):
                return name
    return names[0] if names and not rejected.search(names[0]) else None


def build_manifest(jobs: list[dict], allow_static: bool) -> list[dict]:
    entries: list[dict] = []
    for job in jobs:
        glb = WEB_ROOT / f"{job['dex']:04d}" / f"{job['form']}.glb"
        if not glb.is_file() or glb.stat().st_size <= 1024:
            raise RuntimeError(f"Missing or undersized converted GLB: {glb}")

        try:
            doc = parse_glb_doc(glb)
        except Exception as exc:
            raise RuntimeError(f"Damaged GLB {glb}: {exc}") from exc

        animations = [
            {"name": animation.get("name") or f"animation_{index}"}
            for index, animation in enumerate(doc.get("animations") or [])
            if isinstance(animation, dict)
            and bool(animation.get("channels"))
            and bool(animation.get("samplers"))
        ]
        expected_animated = bool(job.get("animations"))
        actual_animated = bool(animations)

        if expected_animated != actual_animated:
            raise RuntimeError(
                "Converted GLB animation invariant failed for "
                f"#{job['dex']:04d} {job['form']}: "
                f"expected_animated={expected_animated}, actual_animated={actual_animated}"
            )

        names = [a["name"] for a in animations]
        idle = choose_idle(names)
        ready = actual_animated or allow_static
        entries.append(
            {
                "dex": job["dex"],
                "form": job["form"],
                "formKey": job.get("formKey"),
                "url": f"web/models/switch/{job['dex']:04d}/{job['form']}.glb",
                "source": f"official-game-assets:{job['game']}",
                "sourceGame": job["game"],
                "sourceFormat": job["extension"],
                "animationMatch": job.get("animationMatch", "none"),
                "animations": animations,
                "idleAnimation": idle,
                "idleBreaks": [],
                "ready": ready,
                "valid": True,
                "warnings": [] if ready else [
                    "Model imported successfully but no compatible animation exists for this exact game/form/rig; kept staged to avoid a bind/T-pose."
                ],
            }
        )
    return entries


def write_manifest(entries: list[dict]) -> None:
    MANIFEST_JSON.parent.mkdir(parents=True, exist_ok=True)

    json_temp = MANIFEST_JSON.with_suffix(".json.tmp")
    js_temp = MANIFEST_JS.with_suffix(".js.tmp")

    json_temp.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    js_temp.write_text(
        "window.POKEDEX3D_SWITCH_MODELS = "
        + json.dumps(entries, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )

    json_temp.replace(MANIFEST_JSON)
    js_temp.replace(MANIFEST_JS)


def load_existing_manifest() -> list[dict]:
    if not MANIFEST_JSON.is_file():
        return []
    try:
        data = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def merge_partial_manifest(
    converted_entries: list[dict],
    selected_dexes: set[int] | None,
    selected_keys: set[tuple[int, str]] | None,
) -> list[dict]:
    """Merge a targeted import into the existing global Switch manifest."""
    existing = load_existing_manifest()

    if selected_dexes:
        kept = [
            entry
            for entry in existing
            if int(entry.get("dex", -1)) not in selected_dexes
        ]
    else:
        replace_keys = selected_keys or {
            (int(entry["dex"]), str(entry["form"]))
            for entry in converted_entries
        }
        kept = [
            entry
            for entry in existing
            if (int(entry.get("dex", -1)), str(entry.get("form", ""))) not in replace_keys
        ]

    merged: dict[tuple[int, str], dict] = {}
    for entry in kept + converted_entries:
        key = (int(entry["dex"]), str(entry["form"]))
        merged[key] = entry

    return [
        merged[key]
        for key in sorted(merged, key=lambda item: (item[0], item[1]))
    ]


def read_catalog_rows(path: Path) -> dict[tuple[int, str], list[str]]:
    rows: dict[tuple[int, str], list[str]] = {}
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 4 and cols[0].isdigit():
            rows[(int(cols[0]), cols[2])] = cols[:4]
    return rows


def install_desktop(
    entries: list[dict],
    prune_missing: bool = False,
    replace_dexes: set[int] | None = None,
) -> None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return

    root = Path(local) / "Pokedex3DMax" / "offline-models"
    root.mkdir(parents=True, exist_ok=True)
    catalog = root / "model_catalog.tsv"
    generic_catalog = root / "generic_model_catalog.tsv"

    existing = read_catalog_rows(catalog)
    generic = read_catalog_rows(generic_catalog)
    manifest_keys = {(int(entry["dex"]), str(entry["form"])) for entry in entries}

    def row_is_switch(cols: list[str] | None) -> bool:
        if not cols or len(cols) < 4:
            return False
        return cols[3].replace("\\", "/").startswith("switch/")

    def restore_generic(key: tuple[int, str]) -> None:
        fallback = generic.get(key)
        if fallback and len(fallback) >= 4 and (root / Path(fallback[3])).is_file():
            existing[key] = fallback
        else:
            existing.pop(key, None)

    def remove_switch_row(key: tuple[int, str], cols: list[str]) -> None:
        rel = cols[3].replace("\\", "/")
        stale = root / Path(rel)
        if stale.is_file():
            stale.unlink()
        restore_generic(key)

    # A full import is authoritative for every Switch row. A targeted --dex run
    # is authoritative only for those dex numbers. This prevents old spellings
    # such as form-16-00 from surviving after canonical form matching changes.
    for key, cols in list(existing.items()):
        if not row_is_switch(cols):
            continue
        should_prune = (
            (prune_missing and key not in manifest_keys)
            or (
                replace_dexes is not None
                and key[0] in replace_dexes
                and key not in manifest_keys
            )
        )
        if should_prune:
            remove_switch_row(key, cols)

    for entry in entries:
        key = (int(entry["dex"]), str(entry["form"]))
        rel = Path("switch") / f"{entry['dex']:04d}" / f"{entry['form']}.glb"
        dst = root / rel

        if entry.get("ready") is False:
            if dst.is_file():
                dst.unlink()
            # Never delete a working generic fallback. Only replace an old
            # Switch override with the generic row when one exists.
            if row_is_switch(existing.get(key)):
                restore_generic(key)
            continue

        src = ROOT / entry["url"]
        if not src.is_file():
            raise RuntimeError(f"Ready manifest entry is missing its GLB: {src}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        generic_row = generic.get(key)
        previous = existing.get(key)
        previous_name = ""
        if generic_row and len(generic_row) >= 2:
            previous_name = generic_row[1].strip()
        elif previous and len(previous) >= 2:
            previous_name = previous[1].strip()

        display_name = (
            previous_name
            if previous_name and not previous_name.startswith("#")
            else f"#{entry['dex']:04d}"
        )
        existing[key] = [
            str(entry["dex"]),
            display_name,
            entry["form"],
            rel.as_posix(),
        ]

    rows = ["dex\tname\tform\tpath"]
    rows.extend("\t".join(cols) for _, cols in sorted(existing.items()))
    catalog_temp = catalog.with_suffix(".tmp")
    catalog_temp.write_text("\n".join(rows) + "\n", encoding="utf-8")
    catalog_temp.replace(catalog)


def run_self_tests() -> None:
    assert infer_form_key(Path("pm0479_16.gfbmdl")) == "16"
    assert infer_form_key(Path("pm0479_16_00_20012_battleidle02.tranm")) == "16"
    assert infer_form_key(Path("pm0479_00_00.trmdl")) == "regular"

    legacy_model = {
        "dex": 479,
        "form": "form-16",
        "formKey": "16",
        "game": "swsh",
        "source": "pm0479_16.gfbmdl",
        "extension": ".gfbmdl",
    }
    modern_wrong = {
        "dex": 479,
        "form": "form-16-00",
        "formKey": "16",
        "game": "za",
        "source": "pm0479_16_00_idle.tranm",
        "name": "pm0479_16_00_idle",
        "extension": ".tranm",
    }
    legacy_right = {
        "dex": 479,
        "form": "form-16-00",
        "formKey": "16",
        "game": "swsh",
        "source": "pm0479_16_00_idle.gfbanm",
        "name": "pm0479_16_00_idle",
        "extension": ".gfbanm",
    }

    jobs = [dict(legacy_model)]
    attach_animations(jobs, [modern_wrong, legacy_right])
    assert len(jobs[0]["animations"]) == 1
    assert jobs[0]["animations"][0]["extension"] == ".gfbanm"

    wrong_form_job = {
        **legacy_model,
        "form": "form-11",
        "formKey": "11",
    }
    jobs = [wrong_form_job]
    attach_animations(jobs, [legacy_right])
    assert jobs[0]["animations"] == []

    static_newer = {
        "dex": 25,
        "form": "regular",
        "formKey": "regular",
        "game": "za",
        "source": "new.trmdl",
        "extension": ".trmdl",
        "animations": [],
    }
    animated_older = {
        "dex": 25,
        "form": "regular",
        "formKey": "regular",
        "game": "swsh",
        "source": "old.gfbmdl",
        "extension": ".gfbmdl",
        "animations": [legacy_right],
    }
    chosen = dedupe_jobs([static_newer, animated_older])
    assert len(chosen) == 1
    assert chosen[0]["source"] == "old.gfbmdl"

    form_a = {
        **legacy_model,
        "form": "form-16",
        "formKey": "16",
        "animations": [legacy_right],
    }
    form_b = {
        **legacy_model,
        "form": "form-16-00",
        "formKey": "16",
        "source": "duplicate.gfbmdl",
        "animations": [],
    }
    chosen = dedupe_jobs([form_a, form_b])
    assert len(chosen) == 1
    assert chosen[0]["source"] == "pm0479_16.gfbmdl"

    # Partial-import replacement must be scoped: one selected Dex may not
    # imply any other Dex should be removed.
    old_entries = [
        {"dex": 25, "form": "regular"},
        {"dex": 479, "form": "form-11"},
        {"dex": 483, "form": "regular"},
    ]
    selected_dexes = {479}
    kept = [
        entry for entry in old_entries
        if int(entry["dex"]) not in selected_dexes
    ]
    assert {(entry["dex"], entry["form"]) for entry in kept} == {
        (25, "regular"),
        (483, "regular"),
    }

    print("Switch importer self-tests passed.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Pokémon Switch game model assets into Pokedex 3D Max"
    )
    parser.add_argument("inputs", nargs="*", type=Path, help="ZIP/7z archives or extracted folders")
    parser.add_argument("--blender", help="path to blender executable")
    parser.add_argument("--limit", type=int, default=0, help="convert only the first N deduplicated models")
    parser.add_argument("--dex", type=int, action="append", default=[], help="only convert selected National Dex number; repeatable")
    parser.add_argument("--inventory-only", action="store_true", help="scan sources without running Blender")
    parser.add_argument("--self-test", action="store_true", help="run importer matching/cache self-tests and exit")
    parser.add_argument(
        "--allow-static",
        action="store_true",
        help="activate models with no animation clips (normally staged but disabled to prevent T-poses)",
    )
    parser.add_argument("--no-desktop-install", action="store_true")
    args = parser.parse_args()

    run_self_tests()
    if args.self_test:
        return 0

    full_runtime_refresh = (
        not args.dex
        and args.limit <= 0
        and not args.no_desktop_install
        and not args.inventory_only
        and not args.allow_static
    )
    if full_runtime_refresh and PIPELINE_READY.is_file():
        PIPELINE_READY.unlink()

    if not args.inputs:
        args.inputs = discover_default_inputs()
        if not args.inputs:
            print("No Switch Pokemon model archives were found.", file=sys.stderr)
            print("Run setup-all.bat full first, or drag archive files onto import-switch-models.bat.", file=sys.stderr)
            return 2
        print(f"Auto-discovered {len(args.inputs)} Switch archive(s).", flush=True)
        for source in args.inputs:
            print(f"  {source.name}", flush=True)

    all_jobs: list[dict] = []
    all_animations: list[dict] = []
    for source in args.inputs:
        root, game = extract_input(source)
        found = scan_models(root, game)
        anims = scan_animations(root, game)
        print(f"{source.name}: {len(found)} model files, {len(anims)} animation files ({game})")
        all_jobs.extend(found)
        all_animations.extend(anims)

    # Evaluate compatibility before deduplication so a model with a genuine
    # matching animation can beat a newer duplicate that would be static.
    attach_animations(all_jobs, all_animations)
    jobs = dedupe_jobs(all_jobs)
    if args.dex:
        wanted = set(args.dex)
        jobs = [job for job in jobs if job["dex"] in wanted]
    if args.limit > 0:
        jobs = jobs[: args.limit]

    models_with_anim = sum(1 for job in jobs if job.get("animations"))
    incompatible_pairs = sum(
        1
        for job in jobs
        for anim in (job.get("animations") or [])
        if ANIMATION_EXT_FOR_MODEL.get(job["extension"]) != anim.get("extension")
        or job["game"] != anim.get("game")
        or job.get("formKey") != anim.get("formKey")
    )
    if incompatible_pairs:
        raise RuntimeError(f"Internal compatibility error: {incompatible_pairs} invalid model/animation pair(s)")
    print(
        f"Selected {len(jobs)} unique Pokémon/form model jobs; "
        f"{models_with_anim} have compatible same-game/form animations"
    )
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
    converted_entries = build_manifest(jobs, args.allow_static)

    partial_run = bool(args.dex) or args.limit > 0
    selected_dexes = set(args.dex) if args.dex else None
    selected_keys = {(int(job["dex"]), str(job["form"])) for job in jobs}

    if partial_run:
        entries = merge_partial_manifest(
            converted_entries,
            selected_dexes=selected_dexes,
            selected_keys=selected_keys,
        )
    else:
        entries = converted_entries

    write_manifest(entries)
    if not args.no_desktop_install:
        # On targeted runs, touch only converted entries. On a full run, the
        # generated manifest is authoritative and stale Switch cache entries
        # can be safely pruned.
        install_desktop(
            converted_entries if partial_run else entries,
            prune_missing=not partial_run,
            replace_dexes=selected_dexes if partial_run else None,
        )

    ready = sum(1 for entry in converted_entries if entry.get("ready") is not False)
    staged = len(converted_entries) - ready
    verb = "Updated" if partial_run else "Imported"
    print(
        f"{verb} {len(converted_entries)} selected models: "
        f"{ready} active, {staged} staged awaiting animations"
    )
    print(f"Manifest: {MANIFEST_JSON}")
    if staged and not args.allow_static:
        print("Staged models are intentionally not selected by the app until animations are attached.")

    if full_runtime_refresh:
        ready_payload = {
            "pipelineVersion": CONVERSION_PIPELINE_VERSION,
            "addonRevision": ADDON_REV,
            "manifest": str(MANIFEST_JSON),
            "selectedModels": len(converted_entries),
            "activeModels": ready,
            "stagedModels": staged,
        }
        ready_temp = PIPELINE_READY.with_suffix(".tmp")
        ready_temp.write_text(
            json.dumps(ready_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ready_temp.replace(PIPELINE_READY)
        print(f"Validated pipeline marker: {PIPELINE_READY}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
