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
SPECIES_NAMES = ROOT / "data" / "species_names.tsv"
SWSH_MODEL_DEX = ROOT / "data" / "swsh_model_dex.tsv"
ADDON_DIR = TOOLS / "pokemon_switch_model_importer"
ADDON_REPO = "https://github.com/ChicoEevee/Pokemon-Switch-Model-Importer-Blender.git"
ADDON_REV = "b0c98d9fcaab85a04ad35e2d111bae4cad6c1e04"
BLENDER_DEPS = CACHE / "blender-python-deps"
CONVERSION_CACHE = CACHE / "switch-conversion-cache.json"
CONVERSION_PIPELINE_VERSION = 11
PIPELINE_READY = CACHE / f"pipeline-v{CONVERSION_PIPELINE_VERSION}.ready.json"
COVERAGE_REPORT = CACHE / "switch-animation-coverage.json"

MODEL_EXTS = {".trmdl", ".gfbmdl"}
ANIM_EXTS = {".tranm", ".gfbanm"}
ANIMATION_EXT_FOR_MODEL = {".trmdl": ".tranm", ".gfbmdl": ".gfbanm"}
ANIMATION_EXT_FOR_GAME = {
    "lgpe": ".gfbanm",
    "swsh": ".gfbanm",
    "la": ".tranm",
    "sv": ".tranm",
    "za": ".tranm",
}
DEX_RE = re.compile(r"pm(\d{4})", re.I)
FORM_RE = re.compile(r"pm\d{4}(?:_(\d{2}))?(?:_(\d{2}))?", re.I)
SAFE_RE = re.compile(r"[^a-z0-9_-]+")
IMAGE_EXTS = {".png", ".tga", ".jpg", ".jpeg", ".bmp", ".dds", ".webp"}

SOURCE_PRIORITY = {
    "za": 600,
    "sv": 500,
    "la": 400,
    "swsh": 300,
    "lgpe": 200,
    "bdsp": 100,
    "unknown": 0,
}


def read_swsh_model_dex(path: Path = SWSH_MODEL_DEX) -> dict[int, int]:
    mapping: dict[int, int] = {}
    if not path.is_file():
        return mapping
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        try:
            model_id = int(cols[0])
            dex = int(cols[1])
        except ValueError:
            continue
        if model_id > 0 and dex > 0:
            mapping[model_id] = dex
    return mapping


SWSH_MODEL_DEX_MAP = read_swsh_model_dex()


def national_dex_for_model_id(model_id: int, game: str) -> int:
    if game == "swsh":
        return SWSH_MODEL_DEX_MAP.get(model_id, model_id)
    return model_id


def is_switch_pokemon_asset_archive(path: Path) -> bool:
    """Return True only for Pokémon model/animation packs used by this importer."""
    if path.suffix.lower() not in {".zip", ".7z"}:
        return False
    if detect_game(path) == "unknown":
        return False

    stem = path.stem.lower().replace("_", "-")
    if "poke" not in stem:
        return False

    excluded = (
        "trainer",
        "battlemap",
        "battle-map",
        "map",
        "sharedtex",
        "shared-tex",
        "poketex",
        "texture",
        "demo",
    )
    return not any(token in stem for token in excluded)


def is_switch_texture_archive(path: Path) -> bool:
    if path.suffix.lower() not in {".zip", ".7z"}:
        return False
    stem = path.stem.lower().replace("_", "-")
    return (
        detect_game(path) != "unknown"
        and (
            "poketex" in stem
            or "poke-texture" in stem
            or "texture" in stem
            or "textures" in stem
            or "texpack" in stem
            or stem.startswith("tex-")
            or "-tex-" in stem
            or stem.endswith("-tex")
        )
    )


def discover_default_inputs() -> list[Path]:
    """Find Switch archives without recursively walking the toolchain cache."""
    plans = [
        (ROOT, False),
        (ROOT / "switch-assets", True),
        (Path.home() / "Downloads", True),
        (Path.home() / "Desktop", True),
        (ROOT / ".cache" / "mega-switch-assets", True),
    ]
    found: list[Path] = []
    seen: set[Path] = set()

    for root, recursive in plans:
        if not root.exists():
            continue
        iterator = root.rglob("*") if recursive else root.iterdir()
        for path in iterator:
            if not path.is_file():
                continue
            if not (
                is_switch_pokemon_asset_archive(path)
                or is_switch_texture_archive(path)
            ):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(resolved)

    return sorted(found, key=lambda p: (detect_game(p), p.name.lower(), str(p).lower()))


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


def decode_bntx_textures(root: Path) -> int:
    """Decode local BNTX files with the verified ultimate_tex_cli converter."""
    textures = list(root.rglob("*.bntx"))
    if not textures:
        return 0
    decoder = os.environ.get("POKEDEX3D_BNTX_DECODER") or shutil.which("ultimate_tex_cli")
    if not decoder and TOOLS.exists():
        decoder = next((str(p) for p in TOOLS.rglob("ultimate_tex_cli.exe")), None)
    if not decoder:
        raise RuntimeError(
            f"Found {len(textures)} BNTX textures under {root}, but "
            "ultimate_tex_cli is missing. Download its Windows CLI release from "
            "https://github.com/ScanMountGoat/ultimate_tex/releases and place "
            "ultimate_tex_cli.exe in .tools, or set POKEDEX3D_BNTX_DECODER "
            "to its full path. No models were converted with missing textures."
        )
    done = 0
    for source in textures:
        target = source.with_suffix(".png")
        if target.is_file() and target.stat().st_size > 0:
            continue
        result = subprocess.run(
            [str(decoder), str(source), str(target)],
            capture_output=True, text=True,
        )
        if result.returncode or not target.is_file() or target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            raise RuntimeError(
                f"BNTX decode failed for {source.name}: {(result.stderr or result.stdout)[-400:]}"
            )
        done += 1
    if done:
        print(f"Decoded {done} BNTX textures to PNG under {root}.", flush=True)
    return done

def first_image_asset(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    try:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                return path
    except OSError:
        return None
    return None


def add_texture_root(
    roots: list[Path],
    roots_by_game: dict[str, list[Path]],
    root: Path,
    game: str,
) -> bool:
    resolved = root.resolve()
    game_roots = roots_by_game.setdefault(game, [])
    changed = False
    if resolved not in roots:
        roots.append(resolved)
        changed = True
    if resolved not in game_roots:
        game_roots.append(resolved)
        changed = True
    return changed


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
        model_id = int(match.group(1))
        dex = national_dex_for_model_id(model_id, game)
        if dex <= 0 or dex > 2000:
            continue
        form = infer_form(path)
        if form != "regular":
            continue
        jobs.append(
            {
                "dex": dex,
                "modelId": model_id,
                "form": form,
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
        model_id = int(match.group(1))
        dex = national_dex_for_model_id(model_id, game)
        if dex <= 0 or dex > 2000:
            continue
        form = infer_form(path)
        if form != "regular":
            continue
        animations.append(
            {
                "dex": dex,
                "modelId": model_id,
                "form": form,
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
        expected_ext = ANIMATION_EXT_FOR_GAME.get(
            job["game"],
            ANIMATION_EXT_FOR_MODEL.get(job["extension"]),
        )
        key = (
            job["dex"],
            job.get("formKey", job["form"]),
            job["game"],
            expected_ext,
        )
        candidates = by_key.get(key, []) if expected_ext else []
        # Only consider clips whose names explicitly indicate a calm idle-like
        # animation. Generic "loop" clips are not safe enough to activate.
        candidates = [
            anim
            for anim in candidates
            if animation_score(anim)[0] >= 800
        ]
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


def write_animation_coverage_report(jobs: list[dict], animations: list[dict]) -> None:
    """Write a compact explanation of why models are animated or staged."""
    animation_counts: dict[tuple[str, str], int] = {}
    for anim in animations:
        key = (str(anim.get("game", "unknown")), str(anim.get("extension", "")))
        animation_counts[key] = animation_counts.get(key, 0) + 1

    games = sorted({str(job.get("game", "unknown")) for job in jobs})
    game_reports: dict[str, dict] = {}
    for game in games:
        game_jobs = [job for job in jobs if str(job.get("game")) == game]
        animated_jobs = [job for job in game_jobs if job.get("animations")]
        missing_jobs = [job for job in game_jobs if not job.get("animations")]
        model_extensions: dict[str, int] = {}
        for job in game_jobs:
            ext = str(job.get("extension", ""))
            model_extensions[ext] = model_extensions.get(ext, 0) + 1

        available_animation_extensions = {
            ext: count
            for (anim_game, ext), count in sorted(animation_counts.items())
            if anim_game == game
        }
        expected_ext = ANIMATION_EXT_FOR_GAME.get(game)

        game_reports[game] = {
            "selectedModels": len(game_jobs),
            "modelsWithCompatibleAnimation": len(animated_jobs),
            "modelsMissingCompatibleAnimation": len(missing_jobs),
            "expectedAnimationExtension": expected_ext,
            "modelExtensions": model_extensions,
            "availableAnimationExtensions": available_animation_extensions,
            "missingExamples": [
                {
                    "dex": int(job["dex"]),
                    "modelId": int(job.get("modelId", job["dex"])),
                    "form": job["form"],
                    "formKey": job.get("formKey"),
                    "source": Path(job["source"]).name,
                }
                for job in missing_jobs[:25]
            ],
        }

    remapped_jobs = [
        job
        for job in jobs
        if int(job.get("modelId", job["dex"])) != int(job["dex"])
    ]
    report = {
        "pipelineVersion": CONVERSION_PIPELINE_VERSION,
        "addonRevision": ADDON_REV,
        "selectedModels": len(jobs),
        "remappedInternalModelIds": len(remapped_jobs),
        "remapExamples": [
            {
                "modelId": int(job.get("modelId", job["dex"])),
                "dex": int(job["dex"]),
                "form": job["form"],
                "source": Path(job["source"]).name,
            }
            for job in remapped_jobs[:50]
        ],
        "modelsWithCompatibleAnimation": sum(1 for job in jobs if job.get("animations")),
        "modelsMissingCompatibleAnimation": sum(1 for job in jobs if not job.get("animations")),
        "games": game_reports,
    }
    COVERAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    temp = COVERAGE_REPORT.with_suffix(".tmp")
    temp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(COVERAGE_REPORT)

    print("Animation coverage by source game:", flush=True)
    for game, data in game_reports.items():
        expected = data["expectedAnimationExtension"] or "unknown"
        available = ", ".join(
            f"{ext}={count}"
            for ext, count in data["availableAnimationExtensions"].items()
        ) or "none"
        print(
            f"  {game}: {data['modelsWithCompatibleAnimation']}/"
            f"{data['selectedModels']} model(s) have compatible animations; "
            f"expected {expected}; animation files available: {available}",
            flush=True,
        )
    print(f"Coverage report: {COVERAGE_REPORT}", flush=True)


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

        # Nintendo material references are not always spelled/cased exactly
        # like the extracted image files. Resolve texture files conservatively
        # by exact path first, then normalized basename across nearby folders.
        texture_marker = "# POKEDEX3D_TEXTURE_RESOLVER_V2"
        if texture_marker not in text:
            helper = r'''
# POKEDEX3D_TEXTURE_RESOLVER_V2
_POKEDEX3D_TEXTURE_INDEX = {}

def _pokedex3d_texture_keys(value):
    name = os.path.basename(str(value or "").replace("\\\\", "/"))
    stem = os.path.splitext(name)[0].casefold()
    exact = re.sub(r"[^a-z0-9]+", "", stem)

    # Some packs add/drop one or more "_00" form segments while keeping
    # the actual texture basename unchanged.
    relaxed_stem = re.sub(
        r"^(pm[0-9]{4})(?:[_-]00)+(?=[_-])",
        r"\1",
        stem,
    )
    relaxed = re.sub(r"[^a-z0-9]+", "", relaxed_stem)

    keys = [exact]
    if relaxed and relaxed != exact:
        keys.append(relaxed)
    return keys

def _pokedex3d_texture_path(filep, reference, textureextension):
    reference = str(reference or "")
    if not reference:
        return os.path.join(filep, reference)

    raw = reference.replace("\\\\", "/")
    no_ext = raw[:-5] if len(raw) > 5 and raw.lower().endswith(".bntx") else os.path.splitext(raw)[0]
    candidates = [
        os.path.normpath(os.path.join(filep, no_ext + textureextension)),
        os.path.join(filep, os.path.basename(no_ext) + textureextension),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    keys = _pokedex3d_texture_keys(reference)
    if not keys or not keys[0]:
        return candidates[0]

    search_root = os.path.abspath(filep)
    cache_key = search_root.casefold()
    index = _POKEDEX3D_TEXTURE_INDEX.get(cache_key)
    if index is None:
        index = {}
        roots = [search_root]
        parent = os.path.dirname(search_root)
        if parent and parent != search_root:
            roots.append(parent)
        extra_roots = os.environ.get("POKEDEX3D_TEXTURE_ROOTS", "")
        for extra in extra_roots.split(os.pathsep):
            extra = extra.strip()
            if extra:
                roots.append(os.path.abspath(extra))
        image_exts = {".png", ".tga", ".jpg", ".jpeg", ".bmp", ".dds", ".webp"}
        visited = set()
        for root in roots:
            root = os.path.abspath(root)
            if root in visited or not os.path.isdir(root):
                continue
            visited.add(root)
            for current, dirs, files in os.walk(root):
                # Avoid crawling giant unrelated extraction siblings.
                rel_depth = os.path.relpath(current, root).count(os.sep)
                if rel_depth >= 8:
                    dirs[:] = []
                for filename in files:
                    if os.path.splitext(filename)[1].lower() not in image_exts:
                        continue
                    path = os.path.join(current, filename)
                    for texture_key in _pokedex3d_texture_keys(filename):
                        index.setdefault(texture_key, []).append(path)
        _POKEDEX3D_TEXTURE_INDEX[cache_key] = index

    matches = []
    for key in keys:
        matches = index.get(key) or []
        if matches:
            break
    if matches:
        # Prefer the closest path to the model directory, then shortest name.
        matches = sorted(
            matches,
            key=lambda path: (
                len(os.path.relpath(path, search_root).split(os.sep)),
                len(path),
                path.casefold(),
            ),
        )
        resolved = matches[0]
        print("Pokedex3D texture resolve:", reference, "->", resolved)
        return resolved

    print("Pokedex3D texture missing:", reference)
    return candidates[0]
'''
            if "import re\n" not in text:
                text = text.replace("import os\n", "import os\nimport re\n", 1)
            insertion_point = text.find("\n\n", text.find("import "))
            if insertion_point < 0:
                insertion_point = 0
            text = text[:insertion_point + 2] + helper + text[insertion_point + 2:]

        # V2 treated an empty optional texture name as the model directory.
        # os.path.exists(directory) is true, so the upstream importer then tried
        # to load that directory as an image and aborted every TRMDL conversion.
        # Migrate already-patched cached add-ons in place instead of requiring
        # users to delete .tools or redownload the pinned importer.
        old_empty_reference = '''def _pokedex3d_texture_path(filep, reference, textureextension):
    reference = str(reference or "")
    if not reference:
        return os.path.join(filep, reference)
'''
        new_empty_reference = '''def _pokedex3d_texture_path(filep, reference, textureextension):
    reference = str(reference or "")
    if not reference:
        # Return a guaranteed non-file. Callers guard with os.path.exists(),
        # so absent optional maps are skipped instead of loading a directory.
        return os.path.join(filep, "__pokedex3d_missing_texture__" + textureextension)
'''
        if old_empty_reference in text:
            text = text.replace(old_empty_reference, new_empty_reference, 1)

        # Route the add-on's normal texture lookups through the resolver.
        text = re.sub(
            r'os\.path\.join\(filep,\s*mat\["([^"]+)"\]\[:-5\]\s*\+\s*textureextension\)',
            r'_pokedex3d_texture_path(filep, mat["\1"], textureextension)',
            text,
        )

        noisy = "    print(weight_array)\n"
        if noisy in text:
            text = text.replace(noisy, "    # Suppressed huge vertex-weight debug dump for batch imports.\n")

        unsafe = '                    if mat["mat_uvindexlayermask"] != -1:\n                        material.node_tree.links.new(uv_node.outputs["UV"], lym_image_texture.inputs["Vector"])\n'
        safe = '                    if mat["mat_uvindexlayermask"] != -1 and lym_image_texture is not None:\n                        material.node_tree.links.new(uv_node.outputs["UV"], lym_image_texture.inputs["Vector"])\n'
        if unsafe in text:
            text = text.replace(unsafe, safe)

        try:
            compile(text, str(switch_source), "exec")
        except SyntaxError as exc:
            raise RuntimeError(
                f"Patched TRMDL importer is not valid Python: {exc}"
            ) from exc

        switch_source.write_text(text, encoding="utf-8")

    # The legacy GFBMDL importer (Let's Go / Sword & Shield) historically
    # creates a blank image node and never assigns the model's texture table.
    # Patch it to resolve the exact TextureMap -> Model.TextureNames reference
    # and tag the selected albedo for the GLB material flattener.
    gfbmdl_source = ADDON_DIR / "gfbmdl_import.py"
    if gfbmdl_source.is_file():
        text = gfbmdl_source.read_text(encoding="utf-8")

        if "import re\n" not in text:
            text = text.replace("import sys\n", "import sys\nimport re\n", 1)

        # Add the material-name heuristic to cached V1 add-ons without
        # forcing a full third-party checkout refresh.
        if (
            "# POKEDEX3D_GFBMDL_TEXTURE_RESOLVER_V1" in text
            and "def _pokedex3d_gfb_resolve_material_fallback(" not in text
        ):
            supplemental = r'''
def _pokedex3d_gfb_resolve_material_fallback(material_name, model_dir):
    """Best-effort albedo lookup for legacy dumps with inconsistent map names."""
    material_key = re.sub(r"[^a-z0-9]+", "", _pokedex3d_gfb_decode(material_name).casefold())
    pokemon_dir = os.path.dirname(os.path.abspath(model_dir or "."))
    pokemon_key = re.sub(
        r"[^a-z0-9]+",
        "",
        os.path.basename(pokemon_dir).casefold(),
    )

    positive = ("alb", "albedo", "basecolor", "basecolour", "diff", "diffuse", "col", "color", "colour")
    negative = ("nrm", "normal", "mask", "msk", "rough", "rgh", "metal", "mtl", "spec", "ao", "occlusion", "emit", "emi", "lym", "height")

    ranked = []
    seen = set()
    for root in _pokedex3d_gfb_image_roots(model_dir):
        index = _pokedex3d_gfb_index_root(root)
        for paths in index.values():
            for path in paths:
                path_key = os.path.abspath(path).casefold()
                if path_key in seen:
                    continue
                seen.add(path_key)

                basename = os.path.splitext(os.path.basename(path))[0].casefold()
                normalized = re.sub(r"[^a-z0-9]+", "", basename)
                if any(token in normalized for token in negative):
                    continue

                score = 0
                if pokemon_key and pokemon_key in normalized:
                    score += 120
                if material_key and material_key in normalized:
                    score += 100
                if any(token in normalized for token in positive):
                    score += 60

                # Partial material-name overlap still helps with names such as
                # BodyA00 vs BodyA_col, but require a meaningful prefix.
                if material_key:
                    common = os.path.commonprefix([material_key, normalized])
                    score += min(len(common), 12) * 3

                if score > 0:
                    ranked.append((score, len(path), path.casefold(), path))

    if not ranked:
        return None

    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    best = ranked[0]
    # Avoid weak accidental matches when many generations share pm#### names.
    if best[0] < 60:
        return None

    print(
        "GFBMDL heuristic texture resolve:",
        material_name,
        "score=" + str(best[0]),
        "->",
        best[3],
        flush=True,
    )
    return best[3]
'''
            target = "def _pokedex3d_gfb_material_color(material):\n"
            if target in text:
                text = text.replace(target, supplemental + "\n\n" + target, 1)

        # Migrate an already-patched cached add-on from the first resolver
        # draft. The original draft accidentally emitted a literal "\\1"
        # instead of the captured Pokémon prefix in the relaxed key.
        text = text.replace(
            '        r"\\\\1",\n        stem,',
            '        r"\\1",\n        stem,',
        )

        old_map_index_block = '''        texture_name = ""
        if 0 <= index < model.TextureNamesLength():
            texture_name = _pokedex3d_gfb_decode(model.TextureNames(index)).strip()

        combined = (sampler + " " + texture_name).casefold()
'''
        new_map_index_block = '''        texture_candidates = []
        for candidate_index in (index, index - 1, index + 1):
            if 0 <= candidate_index < model.TextureNamesLength():
                candidate_name = _pokedex3d_gfb_decode(
                    model.TextureNames(candidate_index)
                ).strip()
                if candidate_name and candidate_name not in texture_candidates:
                    texture_candidates.append(candidate_name)
        texture_name = texture_candidates[0] if texture_candidates else ""

        combined = (sampler + " " + " ".join(texture_candidates)).casefold()
'''
        if old_map_index_block in text:
            text = text.replace(old_map_index_block, new_map_index_block, 1)

        old_descriptor_field = '''                "texture": texture_name,
                "score": score,
'''
        new_descriptor_field = '''                "texture": texture_name,
                "textureCandidates": texture_candidates,
                "score": score,
'''
        if old_descriptor_field in text:
            text = text.replace(old_descriptor_field, new_descriptor_field, 1)

        old_reference_loop = '''    for descriptor in descriptors:
        reference = descriptor["texture"] or descriptor["sampler"]
        candidate = _pokedex3d_gfb_resolve_texture(reference, model_dir or ".")
        if candidate:
            resolved = candidate
            selected = descriptor
            break
'''
        new_reference_loop = '''    for descriptor in descriptors:
        references = list(descriptor.get("textureCandidates") or [])
        if descriptor.get("sampler"):
            references.append(descriptor["sampler"])
        for reference in references:
            candidate = _pokedex3d_gfb_resolve_texture(reference, model_dir or ".")
            if candidate:
                resolved = candidate
                selected = descriptor
                selected["resolvedReference"] = reference
                break
        if resolved:
            break
'''
        if old_reference_loop in text:
            text = text.replace(old_reference_loop, new_reference_loop, 1)

        old_resolution_tail = '''            selected = descriptor
            break

    if resolved:
'''
        new_resolution_tail = '''            selected = descriptor
            break

    if not resolved:
        resolved = _pokedex3d_gfb_resolve_material_fallback(mat_name, model_dir or ".")

    if resolved:
'''
        if old_resolution_tail in text:
            text = text.replace(old_resolution_tail, new_resolution_tail, 1)


        marker = "# POKEDEX3D_GFBMDL_TEXTURE_RESOLVER_V1"
        if marker not in text:
            helper = r'''
# POKEDEX3D_GFBMDL_TEXTURE_RESOLVER_V1
_POKEDEX3D_GFB_TEXTURE_INDEX = {}

def _pokedex3d_gfb_decode(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)

def _pokedex3d_gfb_texture_keys(value):
    raw = _pokedex3d_gfb_decode(value).replace("\\\\", "/")
    name = os.path.basename(raw)
    stem = os.path.splitext(name)[0].casefold()
    exact = re.sub(r"[^a-z0-9]+", "", stem)

    relaxed_stem = re.sub(
        r"^(pm[0-9]{4})(?:[_-]00)+(?=[_-])",
        r"\1",
        stem,
    )
    relaxed = re.sub(r"[^a-z0-9]+", "", relaxed_stem)

    keys = [exact]
    if relaxed and relaxed != exact:
        keys.append(relaxed)
    return [key for key in keys if key]

def _pokedex3d_gfb_image_roots(model_dir):
    roots = []
    model_dir = os.path.abspath(model_dir or ".")
    pokemon_dir = os.path.dirname(model_dir)

    for candidate in (
        model_dir,
        pokemon_dir,
        os.path.join(pokemon_dir, "tex"),
        os.path.join(pokemon_dir, "texture"),
        os.path.join(pokemon_dir, "textures"),
    ):
        candidate = os.path.abspath(candidate)
        if os.path.isdir(candidate) and candidate not in roots:
            roots.append(candidate)

    extra = os.environ.get("POKEDEX3D_TEXTURE_ROOTS", "")
    for candidate in extra.split(os.pathsep):
        candidate = candidate.strip()
        if not candidate:
            continue
        candidate = os.path.abspath(candidate)
        if os.path.isdir(candidate) and candidate not in roots:
            roots.append(candidate)

    return roots

def _pokedex3d_gfb_index_root(root):
    cache_key = os.path.abspath(root).casefold()
    cached = _POKEDEX3D_GFB_TEXTURE_INDEX.get(cache_key)
    if cached is not None:
        return cached

    index = {}
    image_exts = {".png", ".tga", ".jpg", ".jpeg", ".bmp", ".dds", ".webp"}
    count = 0
    for current, dirs, files in os.walk(root):
        rel_depth = os.path.relpath(current, root).count(os.sep)
        if rel_depth >= 10:
            dirs[:] = []
        for filename in files:
            if os.path.splitext(filename)[1].lower() not in image_exts:
                continue
            path = os.path.join(current, filename)
            for key in _pokedex3d_gfb_texture_keys(filename):
                index.setdefault(key, []).append(path)
            count += 1

    _POKEDEX3D_GFB_TEXTURE_INDEX[cache_key] = index
    print(
        "GFBMDL texture index:",
        root,
        f"({count} image file(s), {len(index)} key(s))",
        flush=True,
    )
    return index

def _pokedex3d_gfb_resolve_texture(reference, model_dir):
    reference = _pokedex3d_gfb_decode(reference).strip()
    if not reference:
        return None

    normalized = reference.replace("\\\\", "/")
    basename = os.path.basename(normalized)
    stem, ext = os.path.splitext(basename)
    image_exts = (".png", ".tga", ".jpg", ".jpeg", ".bmp", ".dds", ".webp")
    candidate_names = [basename]
    if ext.lower() not in image_exts:
        candidate_names = [stem + image_ext for image_ext in image_exts]

    for root in _pokedex3d_gfb_image_roots(model_dir):
        direct_dirs = (
            root,
            os.path.join(root, "tex"),
            os.path.join(root, "texture"),
            os.path.join(root, "textures"),
        )
        for directory in direct_dirs:
            for name in candidate_names:
                candidate = os.path.normpath(os.path.join(directory, name))
                if os.path.isfile(candidate):
                    return candidate

    keys = _pokedex3d_gfb_texture_keys(reference)
    for root in _pokedex3d_gfb_image_roots(model_dir):
        index = _pokedex3d_gfb_index_root(root)
        for key in keys:
            matches = index.get(key) or []
            if not matches:
                continue
            matches = sorted(
                matches,
                key=lambda path: (
                    len(os.path.relpath(path, root).split(os.sep)),
                    len(path),
                    path.casefold(),
                ),
            )
            return matches[0]

    return None

def _pokedex3d_gfb_material_maps(material, model):
    descriptors = []
    for i in range(material.TextureMapsLength()):
        mapping = material.TextureMaps(i)
        if mapping is None:
            continue

        sampler = _pokedex3d_gfb_decode(mapping.Sampler()).strip()
        index = int(mapping.Index())
        texture_candidates = []
        for candidate_index in (index, index - 1, index + 1):
            if 0 <= candidate_index < model.TextureNamesLength():
                candidate_name = _pokedex3d_gfb_decode(
                    model.TextureNames(candidate_index)
                ).strip()
                if candidate_name and candidate_name not in texture_candidates:
                    texture_candidates.append(candidate_name)
        texture_name = texture_candidates[0] if texture_candidates else ""

        combined = (sampler + " " + " ".join(texture_candidates)).casefold()
        score = 0
        preferred = (
            "basecolor", "base_color", "albedo", "diffuse", "diff",
            "color", "colour", "col0", "_col", "body",
        )
        rejected = (
            "normal", "nrm", "bump", "rough", "rgh", "metal", "mtl",
            "spec", "mask", "msk", "opacity", "alpha", "ambient",
            "occlusion", "ao", "emission", "emissive", "emi", "lym",
            "height", "shadow", "detail", "cube", "environment",
        )
        if any(token in combined for token in preferred):
            score += 100
        if any(token in combined for token in rejected):
            score -= 200
        # Base-color maps are normally among the earliest material texture maps.
        score += max(0, 20 - i)

        descriptors.append(
            {
                "order": i,
                "sampler": sampler,
                "index": index,
                "texture": texture_name,
                "textureCandidates": texture_candidates,
                "score": score,
            }
        )

    return sorted(
        descriptors,
        key=lambda item: (-item["score"], item["order"]),
    )

def _pokedex3d_gfb_resolve_material_fallback(material_name, model_dir):
    """Best-effort albedo lookup for legacy dumps with inconsistent map names."""
    material_key = re.sub(r"[^a-z0-9]+", "", _pokedex3d_gfb_decode(material_name).casefold())
    pokemon_dir = os.path.dirname(os.path.abspath(model_dir or "."))
    pokemon_key = re.sub(
        r"[^a-z0-9]+",
        "",
        os.path.basename(pokemon_dir).casefold(),
    )

    positive = ("alb", "albedo", "basecolor", "basecolour", "diff", "diffuse", "col", "color", "colour")
    negative = ("nrm", "normal", "mask", "msk", "rough", "rgh", "metal", "mtl", "spec", "ao", "occlusion", "emit", "emi", "lym", "height")

    ranked = []
    seen = set()
    for root in _pokedex3d_gfb_image_roots(model_dir):
        index = _pokedex3d_gfb_index_root(root)
        for paths in index.values():
            for path in paths:
                path_key = os.path.abspath(path).casefold()
                if path_key in seen:
                    continue
                seen.add(path_key)

                basename = os.path.splitext(os.path.basename(path))[0].casefold()
                normalized = re.sub(r"[^a-z0-9]+", "", basename)
                if any(token in normalized for token in negative):
                    continue

                score = 0
                if pokemon_key and pokemon_key in normalized:
                    score += 120
                if material_key and material_key in normalized:
                    score += 100
                if any(token in normalized for token in positive):
                    score += 60

                # Partial material-name overlap still helps with names such as
                # BodyA00 vs BodyA_col, but require a meaningful prefix.
                if material_key:
                    common = os.path.commonprefix([material_key, normalized])
                    score += min(len(common), 12) * 3

                if score > 0:
                    ranked.append((score, len(path), path.casefold(), path))

    if not ranked:
        return None

    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    best = ranked[0]
    # Avoid weak accidental matches when many generations share pm#### names.
    if best[0] < 60:
        return None

    print(
        "GFBMDL heuristic texture resolve:",
        material_name,
        "score=" + str(best[0]),
        "->",
        best[3],
        flush=True,
    )
    return best[3]


def _pokedex3d_gfb_material_color(material):
    preferred = ("basecolor", "base_color", "diffuse", "color")
    first = None
    for i in range(material.ColorsLength()):
        entry = material.Colors(i)
        if entry is None or entry.Color() is None:
            continue
        color = entry.Color()
        rgba = (
            max(0.0, min(1.0, float(color.R()))),
            max(0.0, min(1.0, float(color.G()))),
            max(0.0, min(1.0, float(color.B()))),
            1.0,
        )
        name = _pokedex3d_gfb_decode(entry.Name()).casefold()
        if first is None:
            first = rgba
        if any(token in name for token in preferred):
            return rgba
    return first

'''
            target = "def CreateMaterial(material):\n"
            if target not in text:
                raise RuntimeError(
                    "Pinned GFBMDL importer layout changed; texture patch cannot be applied"
                )
            text = text.replace(target, helper + target, 1)

        old_material = '''def CreateMaterial(material):
    mat = bpy.data.materials.new(name=material.Name().decode("utf-8"))
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shdr = nodes.get('Principled BSDF')
    out = nodes.get('Material Output')
    img = nodes.new('ShaderNodeTexImage')
    att = nodes.new('ShaderNodeAttribute')
    mix = nodes.new('ShaderNodeMixRGB')
    img.location = (-450, 350)
    att.location = (-450, 165)
    mix.location = (-160, 160)
    att.attribute_name = "Colors"
    links.new(att.outputs[0], mix.inputs[1]) # vert cols -> mix
    links.new(img.outputs[0], mix.inputs[2]) # img cols -> mix
    links.new(mix.outputs[0], shdr.inputs[0]) # mix -> shader
    return mat
'''
        new_material = '''def CreateMaterial(material, model=None, model_dir=None):
    mat_name = _pokedex3d_gfb_decode(material.Name()) or "Material"
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shdr = nodes.get('Principled BSDF')
    if shdr is None:
        shdr = nodes.new('ShaderNodeBsdfPrincipled')
    out = nodes.get('Material Output')
    if out is None:
        out = nodes.new('ShaderNodeOutputMaterial')
        links.new(shdr.outputs['BSDF'], out.inputs['Surface'])

    img = nodes.new('ShaderNodeTexImage')
    img.name = "POKEDEX3D_ALBEDO"
    img.label = "Pokedex3D Albedo"
    img.location = (-450, 350)

    att = nodes.new('ShaderNodeAttribute')
    mix = nodes.new('ShaderNodeMixRGB')
    img.location = (-450, 350)
    att.location = (-450, 165)
    mix.location = (-160, 160)
    att.attribute_name = "Colors"
    mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = 1.0

    resolved = None
    selected = None
    descriptors = _pokedex3d_gfb_material_maps(material, model) if model is not None else []
    for descriptor in descriptors:
        references = list(descriptor.get("textureCandidates") or [])
        if descriptor.get("sampler"):
            references.append(descriptor["sampler"])
        for reference in references:
            candidate = _pokedex3d_gfb_resolve_texture(reference, model_dir or ".")
            if candidate:
                resolved = candidate
                selected = descriptor
                selected["resolvedReference"] = reference
                break
        if resolved:
            break

    if not resolved:
        resolved = _pokedex3d_gfb_resolve_material_fallback(mat_name, model_dir or ".")

    if resolved:
        image = bpy.data.images.load(resolved, check_existing=True)
        img.image = image
        image.alpha_mode = 'CHANNEL_PACKED'
        mat["pokedex3d_basecolor_image"] = image.name
        mat["pokedex3d_basecolor_path"] = resolved
        mat["pokedex3d_gfb_sampler"] = selected["sampler"] if selected else ""
        mat["pokedex3d_gfb_texture_index"] = selected["index"] if selected else -1
        print(
            "GFBMDL texture resolve:",
            mat_name,
            "sampler=" + (selected["sampler"] if selected else ""),
            "texture=" + (selected["texture"] if selected else ""),
            "resolved=" + (selected.get("resolvedReference", "") if selected else ""),
            "->",
            resolved,
            flush=True,
        )
    else:
        fallback = _pokedex3d_gfb_material_color(material)
        if fallback is not None:
            shdr.inputs['Base Color'].default_value = fallback
            mat["pokedex3d_basecolor_factor"] = list(fallback)
        printable = [
            f'{item["order"]}:{item["sampler"]}->{item["texture"]}'
            for item in descriptors
        ]
        print(
            "GFBMDL texture missing:",
            mat_name,
            "maps=[" + ", ".join(printable) + "]",
            "fallback=" + (str(fallback) if fallback is not None else "none"),
            flush=True,
        )

    links.new(att.outputs[0], mix.inputs[1])
    links.new(img.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], shdr.inputs['Base Color'])
    return mat
'''
        if old_material in text:
            text = text.replace(old_material, new_material, 1)
        elif "def CreateMaterial(material, model=None, model_dir=None):" not in text:
            raise RuntimeError(
                "Pinned GFBMDL importer material function changed; texture patch cannot be applied"
            )

        if "def LoadModel(buf, filename):" in text:
            text = text.replace(
                "def LoadModel(buf, filename):",
                "def LoadModel(buf, filename, model_dir=None):",
                1,
            )
        if "mats.append(CreateMaterial(mon.Materials(i)))" in text:
            text = text.replace(
                "mats.append(CreateMaterial(mon.Materials(i)))",
                "mats.append(CreateMaterial(mon.Materials(i), mon, model_dir))",
                1,
            )
        if "LoadModel(buf, f[1].name)" in text:
            text = text.replace(
                "LoadModel(buf, f[1].name)",
                "LoadModel(buf, f[1].name, os.path.dirname(fpath))",
                1,
            )

        if "    print(weight_array)\n" in text:
            text = text.replace(
                "    print(weight_array)\n",
                "    # Suppressed huge vertex-weight debug dump for batch imports.\n",
            )

        required_gfbmdl_markers = (
            "# POKEDEX3D_GFBMDL_TEXTURE_RESOLVER_V1",
            "def _pokedex3d_gfb_resolve_material_fallback(",
            '"textureCandidates": texture_candidates',
            "def CreateMaterial(material, model=None, model_dir=None):",
            '_pokedex3d_gfb_resolve_material_fallback(mat_name, model_dir or ".")',
            "def LoadModel(buf, filename, model_dir=None):",
            "CreateMaterial(mon.Materials(i), mon, model_dir)",
            "LoadModel(buf, f[1].name, os.path.dirname(fpath))",
        )
        missing_gfbmdl_markers = [
            marker
            for marker in required_gfbmdl_markers
            if marker not in text
        ]
        if missing_gfbmdl_markers:
            raise RuntimeError(
                "GFBMDL texture patch validation failed; missing: "
                + ", ".join(missing_gfbmdl_markers)
            )
        try:
            compile(text, str(gfbmdl_source), "exec")
        except SyntaxError as exc:
            raise RuntimeError(
                f"Patched GFBMDL importer is not valid Python: {exc}"
            ) from exc

        gfbmdl_source.write_text(text, encoding="utf-8")

    # GFBMDL-era rigs use compact CamelCase bone names (LArm, RHand,
    # Spine1...), while their animation tracks may use normalized snake_case
    # names (left_arm, right_hand, spine_01...). Upstream requires an exact
    # string match and therefore creates no Action even though the animation
    # parsed successfully. Add a conservative normalized-name resolver: it
    # only matches names that become identical after expanding a leading L/R,
    # removing separators and normalizing zero-padded numeric components.
    gfbanm_source = ADDON_DIR / "gfbanm_importer.py"
    if gfbanm_source.is_file():
        text = gfbanm_source.read_text(encoding="utf-8")

        if "import re\n" not in text:
            text = text.replace("import math\n", "import math\nimport re\n", 1)

        helper_marker = "# POKEDEX3D_NORMALIZED_BONE_MATCH_V1"
        if helper_marker not in text:
            insertion = r'''
# POKEDEX3D_NORMALIZED_BONE_MATCH_V1
def _pokedex3d_normalize_bone_name(name: str) -> str:
    """Normalize equivalent old/new Pokémon rig bone naming conventions."""
    value = str(name or "").strip()
    value = re.sub(r"^L(?=[A-Z])", "Left", value)
    value = re.sub(r"^R(?=[A-Z])", "Right", value)
    parts = re.findall(r"[A-Za-z]+|[0-9]+", value)
    normalized = []
    for part in parts:
        if part.isdigit():
            normalized.append(str(int(part)))
        else:
            normalized.append(part.casefold())
    return "".join(normalized)


def _pokedex3d_pose_bone_lookup(armature_obj):
    lookup = {}
    ambiguous = set()
    for pose_bone in armature_obj.pose.bones:
        key = _pokedex3d_normalize_bone_name(pose_bone.name)
        if not key:
            continue
        if key in lookup and lookup[key] != pose_bone:
            ambiguous.add(key)
        else:
            lookup[key] = pose_bone
    for key in ambiguous:
        lookup.pop(key, None)
    return lookup


'''
            target = "def apply_animation_to_tracks(\n"
            if target not in text:
                raise RuntimeError("Pinned gfbanm importer layout changed; normalized bone patch cannot be applied")
            text = text.replace(target, insertion + target, 1)

        old = '''    action = None
    context.window_manager.progress_begin(0, len(tracks))
    for i, track in enumerate(tracks):
        if track is None or track.name is None or track.name == "":
            context.window_manager.progress_update(i + 1)
            continue
        print(f"Creating keyframes for {track.name} track.")
        if track.name not in context.object.pose.bones.keys():
            context.window_manager.progress_update(i + 1)
            continue
        pose_bone = context.object.pose.bones[track.name]
'''
        new = '''    action = None
    named_track_count = 0
    matched_track_count = 0
    unmatched_track_names = []
    normalized_bones = _pokedex3d_pose_bone_lookup(context.object)
    context.window_manager.progress_begin(0, len(tracks))
    for i, track in enumerate(tracks):
        if track is None or track.name is None or track.name == "":
            context.window_manager.progress_update(i + 1)
            continue
        named_track_count += 1
        print(f"Creating keyframes for {track.name} track.")
        pose_bone = context.object.pose.bones.get(track.name)
        if pose_bone is None:
            pose_bone = normalized_bones.get(_pokedex3d_normalize_bone_name(track.name))
        if pose_bone is None:
            unmatched_track_names.append(track.name)
            context.window_manager.progress_update(i + 1)
            continue
        matched_track_count += 1
'''
        if old in text:
            text = text.replace(old, new, 1)
        elif "normalized_bones = _pokedex3d_pose_bone_lookup(context.object)" not in text:
            raise RuntimeError("Pinned gfbanm importer track loop changed; normalized bone patch cannot be applied")

        stats_anchor = '''    context.window_manager.progress_end()
    context.view_layer.update()

    # If requested, push the newly-created action into NLA as a new track/strip.
'''
        stats_replacement = '''    context.window_manager.progress_end()
    context.view_layer.update()

    match_ratio = (matched_track_count / named_track_count) if named_track_count else 0.0
    print(
        f"Animation bone match: {matched_track_count}/{named_track_count} "
        f"({match_ratio:.1%})"
    )
    if unmatched_track_names:
        preview = ", ".join(unmatched_track_names[:12])
        suffix = " ..." if len(unmatched_track_names) > 12 else ""
        print(f"Unmatched animation tracks: {preview}{suffix}")
    if action is not None:
        action["pokedex3d_matched_tracks"] = matched_track_count
        action["pokedex3d_named_tracks"] = named_track_count
        action["pokedex3d_match_ratio"] = match_ratio

    # If requested, push the newly-created action into NLA as a new track/strip.
'''
        if stats_anchor in text:
            text = text.replace(stats_anchor, stats_replacement, 1)
        elif 'action["pokedex3d_matched_tracks"]' not in text:
            raise RuntimeError("Pinned gfbanm importer stats anchor changed; normalized bone patch cannot be applied")

        gfbanm_source.write_text(text, encoding="utf-8")



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



def material_texture_coverage(doc: dict) -> tuple[int, int]:
    """Return (materials with valid base-color textures, total materials)."""
    textures = doc.get("textures") or []
    materials = doc.get("materials") or []
    textured = 0
    total = 0

    for material in materials:
        if not isinstance(material, dict):
            continue
        total += 1
        pbr = material.get("pbrMetallicRoughness") or {}
        slot = pbr.get("baseColorTexture")
        if not isinstance(slot, dict):
            continue
        index = slot.get("index")
        if isinstance(index, int) and 0 <= index < len(textures):
            textured += 1

    return textured, total


def glb_texture_count(path: Path) -> int:
    """Count mesh materials with a valid base-color texture binding."""
    try:
        doc = parse_glb_doc(path)
    except Exception:
        return 0
    return material_texture_coverage(doc)[0]


def glb_textures_complete(path: Path) -> bool:
    """Require every exported material to have a real base-color texture."""
    try:
        doc = parse_glb_doc(path)
    except Exception:
        return False
    textured, total = material_texture_coverage(doc)
    return total > 0 and textured == total


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
        "modelId": job.get("modelId", job["dex"]),
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


def load_conversion_cache() -> dict[str, object]:
    if not CONVERSION_CACHE.is_file():
        return {}
    try:
        data = json.loads(CONVERSION_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_conversion_cache(cache: dict[str, object]) -> None:
    CONVERSION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    temp = CONVERSION_CACHE.with_suffix(".tmp")
    temp.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(CONVERSION_CACHE)


def output_cache_key(job: dict) -> str:
    return f"{job['dex']:04d}/{job['form']}.glb"


def run_blender(
    jobs: list[dict],
    blender: str,
    addon: Path,
    blender_deps: Path,
    texture_roots: list[Path] | None = None,
    refresh_changed: bool = False,
    force: bool = False,
) -> None:
    WEB_ROOT.mkdir(parents=True, exist_ok=True)
    cache = load_conversion_cache()
    payload: list[dict] = []
    reused = 0

    for job in jobs:
        out = WEB_ROOT / f"{job['dex']:04d}" / f"{job['form']}.glb"
        wants_animations = bool(job.get("animations"))
        fingerprint = job_fingerprint(job)
        cache_key = output_cache_key(job)

        cached = cache.get(cache_key)
        cached_fingerprint = None
        cached_rejected = False
        cached_rejection_reason = None
        if isinstance(cached, str):
            cached_fingerprint = cached
        elif isinstance(cached, dict):
            cached_fingerprint = cached.get("fingerprint")
            cached_rejected = bool(cached.get("animationRejected"))
            cached_rejection_reason = cached.get("animationRejectionReason")

        structurally_complete = (
            existing_glb_is_complete(
                out,
                wants_animations and not cached_rejected,
            )
            and glb_textures_complete(out)
        )
        fingerprint_matches = cached_fingerprint == fingerprint

        reuse_existing = False
        reuse_reason = None
        if not force:
            if refresh_changed:
                reuse_existing = structurally_complete and fingerprint_matches
                reuse_reason = "unchanged"
            else:
                # Incremental is the default: a valid output is already imported,
                # even if source/archive mtimes or pipeline metadata changed.
                # The only exception is when the current job now requires an
                # animation but the existing GLB does not contain one.
                reuse_existing = structurally_complete
                reuse_reason = "already imported"

        if reuse_existing:
            if cached_rejected:
                job["animationCandidates"] = list(job.get("animations") or [])
                job["animations"] = []
                job["animationRejected"] = True
                job["animationRejectionReason"] = cached_rejection_reason
            # Seed/refresh the fingerprint cache for outputs that predate the
            # cache so future --refresh-changed runs can compare them.
            cache[cache_key] = {
                "fingerprint": fingerprint,
                "animationRejected": cached_rejected,
                "animationRejectionReason": cached_rejection_reason,
            }
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
        mode = "unchanged" if refresh_changed else "already-imported"
        print(f"Reusing {reused} {mode} Switch model(s).", flush=True)
        save_conversion_cache(cache)

    if not payload:
        print("All selected models are already imported; nothing to convert.")
        return

    jobs_file = CACHE / "switch-model-jobs.json"
    failure_path = jobs_file.with_name("switch-model-failures.json")
    results_path = jobs_file.with_name("switch-model-results.json")
    for stale_report in (failure_path, results_path):
        if stale_report.exists():
            stale_report.unlink()

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
    if force:
        reason = "forced"
    elif refresh_changed:
        reason = "missing/invalid/changed"
    else:
        reason = "missing/invalid or newly animatable"
    print(
        f"Converting {len(payload)} {reason} Switch model(s) in one Blender session ...",
        flush=True,
    )
    blender_env = os.environ.copy()
    if texture_roots:
        blender_env["POKEDEX3D_TEXTURE_ROOTS"] = os.pathsep.join(
            str(path.resolve()) for path in texture_roots if path.exists()
        )
    result = subprocess.run(cmd, cwd=ROOT, env=blender_env)

    outcomes: dict[str, dict] = {}
    if results_path.is_file():
        try:
            raw_results = json.loads(results_path.read_text(encoding="utf-8"))
            outcomes = {
                str(Path(item["source"]).resolve()): item
                for item in raw_results
                if isinstance(item, dict) and item.get("source")
            }
        except Exception as exc:
            raise RuntimeError(f"Could not read Blender conversion results: {exc}") from exc

    jobs_by_source = {
        str(Path(job["source"]).resolve()): job
        for job in jobs
    }
    payload_by_source = {
        str(Path(item["source"]).resolve()): item
        for item in payload
    }
    rejected_count = 0
    for source, outcome in outcomes.items():
        if not outcome.get("animationRejected"):
            continue
        rejected_count += 1
        reason = outcome.get("animationRejectionReason")
        for target in (jobs_by_source.get(source), payload_by_source.get(source)):
            if target is None:
                continue
            target["animationCandidates"] = list(target.get("animations") or [])
            target["animations"] = []
            target["animationRejected"] = True
            target["animationRejectionReason"] = reason

    if rejected_count:
        print(
            f"Quarantined {rejected_count} model(s) whose animation candidates "
            "did not safely match their rigs.",
            flush=True,
        )

    failed_sources: set[str] = set()
    failure_details: dict[str, dict] = {}
    failure_report_available = False
    if failure_path.is_file():
        try:
            failures = json.loads(failure_path.read_text(encoding="utf-8"))
            failure_details = {
                str(Path(item["source"]).resolve()): item
                for item in failures
                if isinstance(item, dict) and item.get("source")
            }
            failed_sources = set(failure_details)
            failure_report_available = True
        except Exception:
            pass

    submitted_sources = {
        str(Path(item["source"]).resolve())
        for item in payload
    }
    accounted_sources = set(outcomes) | failed_sources
    unaccounted_sources = submitted_sources - accounted_sources
    unknown_sources = accounted_sources - submitted_sources
    if unaccounted_sources or unknown_sources:
        details = []
        if unaccounted_sources:
            details.append(
                "unaccounted=" + ", ".join(sorted(unaccounted_sources)[:10])
            )
        if unknown_sources:
            details.append(
                "unknown=" + ", ".join(sorted(unknown_sources)[:10])
            )
        raise RuntimeError(
            "Blender conversion result protocol invariant failed: "
            + "; ".join(details)
        )

    for job in jobs:
        source = str(Path(job["source"]).resolve())
        if source not in failed_sources:
            job.pop("conversionFailed", None)
            job.pop("conversionFailureReason", None)
            continue
        detail = failure_details.get(source) or {}
        job["conversionFailed"] = True
        job["conversionFailureReason"] = (
            detail.get("error")
            or detail.get("message")
            or detail.get("reason")
            or "Blender conversion failed"
        )
        out = WEB_ROOT / f"{job['dex']:04d}" / f"{job['form']}.glb"
        if out.is_file() and (
            not existing_glb_is_complete(out, False)
            or not glb_textures_complete(out)
        ):
            out.unlink()

    # Persist verified successes even if another conversion in the batch failed,
    # so the next run retries only true conversion failures. Rig-incompatible
    # animation outcomes are cached as quarantined static models until either
    # the assets or pipeline version changes.
    if result.returncode == 0 or failure_report_available:
        for item in payload:
            source = str(Path(item["source"]).resolve())
            if source in failed_sources:
                continue
            outcome = outcomes.get(source)
            if outcome is None:
                continue
            out = Path(item["output"])
            rejected = bool(outcome.get("animationRejected"))
            if existing_glb_is_complete(out, bool(item.get("animations")) and not rejected):
                cache[item["cacheKey"]] = {
                    "fingerprint": item["fingerprint"],
                    "animationRejected": rejected,
                    "animationRejectionReason": outcome.get("animationRejectionReason"),
                }
        save_conversion_cache(cache)

    if result.returncode:
        if not failure_report_available:
            raise RuntimeError(
                f"Blender conversion failed with code {result.returncode}; "
                "no structured failure report was produced"
            )
        print(
            f"WARNING - {len(failed_sources)} Switch model conversion(s) failed. "
            "Those models remain unavailable; no alternate model source is substituted.",
            flush=True,
        )
        print(f"Failure report: {failure_path}", flush=True)


def choose_idle(names: list[str]) -> str | None:
    preferred = (
        r"default(?:idle|wait)",
        r"battle(?:idle|wait)",
        r"fight[_ -]?a",
        r"(^|[_-])idle([0-9]*|[_-].*)?$",
        r"wait|stand|breath|rest",
    )
    rejected = re.compile(
        r"attack|damage|faint|death|down|hit|move|run|walk|jump|bind|t[-_ ]?pose",
        re.I,
    )
    for pattern in preferred:
        rx = re.compile(pattern, re.I)
        for name in names:
            if rx.search(name) and not rejected.search(name):
                return name
    return None


def build_manifest(jobs: list[dict]) -> list[dict]:
    entries: list[dict] = []
    for job in jobs:
        if job.get("conversionFailed"):
            continue
        glb = WEB_ROOT / f"{job['dex']:04d}" / f"{job['form']}.glb"
        if not glb.is_file() or glb.stat().st_size <= 1024:
            raise RuntimeError(f"Missing or undersized converted GLB: {glb}")

        try:
            doc = parse_glb_doc(glb)
        except Exception as exc:
            raise RuntimeError(f"Damaged GLB {glb}: {exc}") from exc

        if not glb_textures_complete(glb):
            raise RuntimeError(
                f"Incomplete base-color texture coverage in converted GLB: {glb}"
            )

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
        ready = bool(idle)
        if ready:
            warnings = []
        elif job.get("animationRejected"):
            reason = str(job.get("animationRejectionReason") or "rig compatibility check failed")
            warnings = [
                "Animation candidates were rejected by the rig compatibility gate; "
                "the verified static model is quarantined/staged. " + reason
            ]
        elif actual_animated:
            warnings = [
                "Model has animation data but no verified idle-like clip; kept staged to avoid starting in a non-idle pose."
            ]
        else:
            warnings = [
                "Model imported successfully but no compatible animation exists for this exact game/form/rig; kept staged to avoid a bind/T-pose."
            ]
        entries.append(
            {
                "dex": job["dex"],
                "modelId": job.get("modelId", job["dex"]),
                "form": job["form"],
                "formKey": job.get("formKey"),
                "url": f"web/models/switch/{job['dex']:04d}/{job['form']}.glb",
                "source": f"official-game-assets:{job['game']}",
                "sourceGame": job["game"],
                "sourceFormat": job["extension"],
                "animationMatch": job.get("animationMatch", "none"),
                "animationRejected": bool(job.get("animationRejected")),
                "animationRejectionReason": job.get("animationRejectionReason"),
                "animations": animations,
                "idleAnimation": idle,
                "idleBreaks": [],
                "ready": ready,
                "valid": True,
                "warnings": warnings,
            }
        )
    return entries


def prune_generated_switch_outputs(entries: list[dict]) -> None:
    expected = {
        (
            WEB_ROOT
            / f"{int(entry['dex']):04d}"
            / f"{entry['form']}.glb"
        ).resolve()
        for entry in entries
    }
    if not WEB_ROOT.is_dir():
        return

    removed = 0
    for path in WEB_ROOT.rglob("*.glb"):
        if path.resolve() in expected:
            continue
        path.unlink()
        removed += 1

    for directory in sorted(
        (path for path in WEB_ROOT.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass

    if removed:
        print(f"Removed {removed} stale generated Switch GLB(s).", flush=True)


def prune_conversion_cache(jobs: list[dict]) -> None:
    cache = load_conversion_cache()
    expected = {output_cache_key(job) for job in jobs}
    pruned = {
        key: value
        for key, value in cache.items()
        if key in expected
    }
    if len(pruned) != len(cache):
        save_conversion_cache(pruned)
        print(
            f"Removed {len(cache) - len(pruned)} stale Switch conversion cache entrie(s).",
            flush=True,
        )


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
    runtime_species_names = root / "species_names.tsv"

    if SPECIES_NAMES.is_file():
        shutil.copy2(SPECIES_NAMES, runtime_species_names)

    existing = read_catalog_rows(catalog)
    known_names_by_dex: dict[int, str] = read_species_names()
    for source_rows in (existing,):
        for (dex, _form), cols in source_rows.items():
            if len(cols) >= 2:
                candidate = cols[1].strip()
                if candidate and not candidate.startswith("#"):
                    known_names_by_dex.setdefault(dex, candidate)
    manifest_keys = {(int(entry["dex"]), str(entry["form"])) for entry in entries}

    def row_is_switch(cols: list[str] | None) -> bool:
        if not cols or len(cols) < 4:
            return False
        return cols[3].replace("\\", "/").startswith("switch/")

    def remove_catalog_row(key: tuple[int, str]) -> None:
        existing.pop(key, None)

    def remove_switch_row(key: tuple[int, str], cols: list[str]) -> None:
        rel = cols[3].replace("\\", "/")
        stale = root / Path(rel)
        if stale.is_file():
            stale.unlink()
        remove_catalog_row(key)

    # The baseline catalog is Switch-only. Old generic/CDN rows are metadata
    # debris from previous builds and are never retained as runtime choices.
    existing = {
        key: cols
        for key, cols in existing.items()
        if row_is_switch(cols)
    }

    # A full import is authoritative for every Switch row. A targeted --dex run
    # is authoritative only for those dex numbers. This prevents old spellings
    # such as form-16-00 from surviving after canonical form matching changes.
    if prune_missing:
        expected_runtime_switch = {
            (
                root
                / "switch"
                / f"{int(entry['dex']):04d}"
                / f"{entry['form']}.glb"
            ).resolve()
            for entry in entries
            if entry.get("ready") is not False
        }
        runtime_switch_root = root / "switch"
        if runtime_switch_root.is_dir():
            for stale in runtime_switch_root.rglob("*.glb"):
                if stale.resolve() not in expected_runtime_switch:
                    stale.unlink()
            for directory in sorted(
                (path for path in runtime_switch_root.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass

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
            remove_catalog_row(key)
            continue

        src = ROOT / entry["url"]
        if not src.is_file():
            raise RuntimeError(f"Ready manifest entry is missing its GLB: {src}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        previous = existing.get(key)
        previous_name = ""
        if previous and len(previous) >= 2:
            previous_name = previous[1].strip()

        display_name = known_names_by_dex.get(int(entry["dex"]))
        if not display_name:
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

    # Preserve the same animation metadata for the native viewer and index.
    metadata_path = root / "switch-model-metadata.json"
    previous_metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else []
    active_keys = {key for key, cols in existing.items() if row_is_switch(cols)}
    merged_metadata = {
        (int(item["dex"]), str(item["form"])): item
        for item in previous_metadata
        if (int(item["dex"]), str(item["form"])) in active_keys
    }
    for entry in entries:
        key = (int(entry["dex"]), str(entry["form"]))
        if key in active_keys and entry.get("ready") is not False:
            merged_metadata[key] = entry
    metadata_temp = metadata_path.with_suffix(".tmp")
    metadata_temp.write_text(json.dumps(list(merged_metadata.values()), indent=2) + "\n", encoding="utf-8")
    metadata_temp.replace(metadata_path)

    installed = read_catalog_rows(catalog)
    missing_paths: list[str] = []
    for cols in installed.values():
        if len(cols) < 4:
            continue
        path = root / Path(cols[3])
        if not path.is_file():
            missing_paths.append(str(path))
    if missing_paths:
        preview = "\n  ".join(missing_paths[:10])
        raise RuntimeError(
            "Desktop model catalog contains missing files:\n  " + preview
        )

    for entry in entries:
        key = (int(entry["dex"]), str(entry["form"]))
        row = installed.get(key)
        switch_expected = entry.get("ready") is not False
        switch_actual = bool(
            row
            and len(row) >= 4
            and row[3].replace("\\", "/").startswith("switch/")
        )
        if switch_expected != switch_actual:
            raise RuntimeError(
                "Desktop catalog invariant failed for "
                f"#{entry['dex']:04d} {entry['form']}: "
                f"expected_switch={switch_expected}, actual_switch={switch_actual}"
            )


def run_self_tests() -> None:
    accepted_archives = [
        "LA-Poke.zip",
        "LA-PokeAnim.zip",
        "LGPE-PokeAnim.zip",
        "SV-Poke.zip",
        "SV-PokeDLC2.zip",
        "SwSh-PokeGen4-5.zip",
        "SwSh-PokeGen8.zip",
        "ZA-Poke.zip",
        "ZA-PokeAnim.zip",
        "ZA-PokeAnimDLC.zip",
        "ZA-PokeDLC.zip",
    ]
    rejected_archives = [
        "LGPE-BattleMaps.7z",
        "LGPE-Trainers.7z",
        "SwSh-TrainersDLC2.7z",
        "ZA-Demo.zip",
        "ZA-TrainersAnimDLC.zip",
        "ZA-TrainersNPC.zip",
        "ZA-TrainersPlayerDLC.zip",
        "ZA-TrainersSharedTexDLC.zip",
    ]
    assert all(is_switch_pokemon_asset_archive(Path(name)) for name in accepted_archives)
    assert all(not is_switch_pokemon_asset_archive(Path(name)) for name in rejected_archives)
    assert is_switch_texture_archive(Path("SV-PokeTex.zip"))
    assert is_switch_texture_archive(Path("ZA-PokeTexture.zip"))
    assert is_switch_texture_archive(Path("SwSh-Textures.zip"))
    assert is_switch_texture_archive(Path("Textures-SwSh.zip"))
    assert is_switch_texture_archive(Path("SwSh-TexPack.7z"))
    assert not is_switch_texture_archive(Path("SV-Poke.zip"))

    assert infer_form_key(Path("pm0479_16.gfbmdl")) == "16"
    assert infer_form_key(Path("pm0479_16_00_20012_battleidle02.tranm")) == "16"
    assert infer_form_key(Path("pm0479_00_00.trmdl")) == "regular"

    assert national_dex_for_model_id(917, "swsh") == 845
    assert national_dex_for_model_id(920, "swsh") == 823
    assert national_dex_for_model_id(950, "swsh") == 812
    assert national_dex_for_model_id(940, "swsh") == 890
    assert national_dex_for_model_id(983, "swsh") == 892
    assert national_dex_for_model_id(6, "swsh") == 6
    assert national_dex_for_model_id(917, "sv") == 917

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

    legends_arceus_model = {
        "dex": 58,
        "form": "regular",
        "formKey": "regular",
        "game": "la",
        "source": "pm0058_00.gfbmdl",
        "extension": ".gfbmdl",
    }
    legends_arceus_tranm = {
        "dex": 58,
        "form": "regular",
        "formKey": "regular",
        "game": "la",
        "source": "pm0058_00_defaultwait01.tranm",
        "name": "pm0058_00_defaultwait01",
        "extension": ".tranm",
    }
    legends_arceus_gfbanm = {
        **legends_arceus_tranm,
        "source": "pm0058_00_defaultwait01.gfbanm",
        "extension": ".gfbanm",
    }
    jobs = [dict(legends_arceus_model)]
    attach_animations(jobs, [legends_arceus_gfbanm, legends_arceus_tranm])
    assert len(jobs[0]["animations"]) == 1
    assert jobs[0]["animations"][0]["extension"] == ".tranm"

    assert choose_idle(["pm0001_defaultwait01_loop"]) == "pm0001_defaultwait01_loop"
    assert choose_idle(["pm0001_attack01", "pm0001_damage01"]) is None
    assert choose_idle(["pm0001_generic_loop"]) is None

    fully_textured = {
        "textures": [{"source": 0}, {"source": 1}],
        "materials": [
            {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
            {"pbrMetallicRoughness": {"baseColorTexture": {"index": 1}}},
        ],
    }
    partially_textured = {
        "textures": [{"source": 0}],
        "materials": [
            {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}},
            {"pbrMetallicRoughness": {}},
        ],
    }
    assert material_texture_coverage(fully_textured) == (2, 2)
    assert material_texture_coverage(partially_textured) == (1, 2)



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
    parser.add_argument("--no-desktop-install", action="store_true")
    parser.add_argument(
        "--refresh-changed",
        action="store_true",
        help="also reconvert models whose source/model/animation fingerprint changed",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="reconvert every selected model even when a valid GLB already exists",
    )
    parser.set_defaults(allow_broken_textures=False)
    args = parser.parse_args()
    os.environ.pop("POKEDEX3D_ALLOW_BROKEN_TEXTURES", None)

    run_self_tests()
    if args.self_test:
        return 0

    full_runtime_refresh = (
        not args.dex
        and args.limit <= 0
        and not args.no_desktop_install
        and not args.inventory_only
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
    texture_roots: list[Path] = []
    texture_roots_by_game: dict[str, list[Path]] = {}
    for source in args.inputs:
        root, game = extract_input(source)
        if is_switch_texture_archive(source):
            add_texture_root(texture_roots, texture_roots_by_game, root, game)
            image = first_image_asset(root)
            detail = f"; sample={image.name}" if image is not None else "; no supported image files found"
            print(f"{source.name}: texture dependency root ({game}){detail}")
            continue

        found = scan_models(root, game)
        anims = scan_animations(root, game)
        if found and first_image_asset(root) is None:
            decode_bntx_textures(root)
        embedded_image = first_image_asset(root)
        if embedded_image is not None:
            add_texture_root(texture_roots, texture_roots_by_game, root, game)
        texture_note = (
            f", embedded texture images present (sample={embedded_image.name})"
            if embedded_image is not None
            else ""
        )
        print(
            f"{source.name}: {len(found)} model files, {len(anims)} animation files "
            f"({game}){texture_note}"
        )
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

    # Texture names are reused across generations. Give each conversion only
    # the texture roots from its own game first so pm#### basename collisions
    # cannot silently bind a Sword/Shield model to an SV/ZA image.
    textureless_legacy_jobs = 0
    for job in jobs:
        same_game_roots = texture_roots_by_game.get(job.get("game"), [])
        job["textureRoots"] = [str(path.resolve()) for path in same_game_roots]
        if not same_game_roots:
            job["textureRootWarning"] = (
                f"No supported texture image source was discovered for game={job.get('game')}"
            )
            if job.get("extension") == ".gfbmdl":
                textureless_legacy_jobs += 1

    if textureless_legacy_jobs and not args.allow_broken_textures:
        print(
            f"WARNING - {textureless_legacy_jobs} legacy GFBMDL job(s) have no "
            "same-game PNG/DDS/TGA/JPG/WebP texture source. They will be "
            "quarantined instead of wasting Blender conversion time.",
            flush=True,
        )

    write_animation_coverage_report(jobs, all_animations)
    models_with_anim = sum(1 for job in jobs if job.get("animations"))
    incompatible_pairs = sum(
        1
        for job in jobs
        for anim in (job.get("animations") or [])
        if ANIMATION_EXT_FOR_GAME.get(
            job["game"],
            ANIMATION_EXT_FOR_MODEL.get(job["extension"]),
        ) != anim.get("extension")
        or job["game"] != anim.get("game")
        or job.get("formKey") != anim.get("formKey")
    )
    if incompatible_pairs:
        raise RuntimeError(f"Internal compatibility error: {incompatible_pairs} invalid model/animation pair(s)")
    remapped_jobs = sum(
        1
        for job in jobs
        if int(job.get("modelId", job["dex"])) != int(job["dex"])
    )
    print(
        f"Selected {len(jobs)} unique Pokémon/form model jobs; "
        f"{models_with_anim} have compatible same-game/form animations; "
        f"{remapped_jobs} use internal-ID to National-Dex remapping"
    )
    if args.inventory_only:
        inventory = CACHE / "switch-model-inventory.json"
        inventory.parent.mkdir(parents=True, exist_ok=True)
        inventory.write_text(json.dumps(jobs, indent=2) + "\n", encoding="utf-8")
        print(f"Inventory: {inventory}")
        return 0

    if not jobs:
        return 0

    impossible_texture_jobs = [
        job
        for job in jobs
        if job.get("extension") == ".gfbmdl"
        and not job.get("textureRoots")
        and not args.allow_broken_textures
    ]
    for job in impossible_texture_jobs:
        job["conversionFailed"] = True
        job["conversionFailureReason"] = (
            "No supported same-game texture image source was discovered for "
            "legacy GFBMDL conversion."
        )

    convertible_jobs = [
        job for job in jobs if not job.get("conversionFailed")
    ]

    if convertible_jobs:
        blender = find_blender(args.blender)
        addon = ensure_addon()
        blender_deps = ensure_blender_python_deps()
        run_blender(
            convertible_jobs,
            blender,
            addon,
            blender_deps,
            texture_roots=texture_roots,
            refresh_changed=args.refresh_changed,
            force=args.force,
        )
    converted_entries = build_manifest(jobs)

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
        prune_generated_switch_outputs(entries)
        prune_conversion_cache(jobs)

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

    failed_conversions = sum(1 for job in jobs if job.get("conversionFailed"))
    ready = sum(1 for entry in converted_entries if entry.get("ready") is not False)
    staged = len(converted_entries) - ready
    quarantined = sum(
        1
        for entry in converted_entries
        if entry.get("ready") is False and entry.get("animationRejected")
    )
    animated_without_idle = sum(
        1
        for entry in converted_entries
        if entry.get("ready") is False
        and not entry.get("animationRejected")
        and bool(entry.get("animations"))
    )
    missing_compatible_animation = staged - quarantined - animated_without_idle
    verb = "Updated" if partial_run else "Imported"
    print(
        f"{verb} {len(converted_entries)} selected models: "
        f"{ready} active, {staged} staged "
        f"({missing_compatible_animation} missing compatible animation, "
        f"{animated_without_idle} animated but without a verified idle, "
        f"{quarantined} quarantined for rig incompatibility, "
        f"{failed_conversions} conversion failures left unavailable)"
    )
    print(f"Manifest: {MANIFEST_JSON}")
    if staged:
        print("Staged models are intentionally not selected by the app until animations are attached.")

    if full_runtime_refresh:
        if failed_conversions or staged:
            PIPELINE_READY.unlink(missing_ok=True)
            print(
                "Pipeline ready marker was not written because the strict "
                f"baseline is incomplete: {failed_conversions} failed, "
                f"{staged} staged.",
                flush=True,
            )
        else:
            ready_payload = {
                "pipelineVersion": CONVERSION_PIPELINE_VERSION,
                "addonRevision": ADDON_REV,
                "manifest": str(MANIFEST_JSON),
                "selectedModels": len(converted_entries),
                "activeModels": ready,
                "stagedModels": staged,
                "missingCompatibleAnimationModels": missing_compatible_animation,
                "animatedWithoutVerifiedIdleModels": animated_without_idle,
                "quarantinedAnimationModels": quarantined,
                "failedConversionModels": 0,
                "failureReport": str(CACHE / "switch-model-failures.json"),
                "coverageReport": str(COVERAGE_REPORT),
            }
            ready_temp = PIPELINE_READY.with_suffix(".tmp")
            ready_temp.write_text(
                json.dumps(ready_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ready_temp.replace(PIPELINE_READY)
            print(f"Validated pipeline marker: {PIPELINE_READY}")

    if full_runtime_refresh and (failed_conversions or staged):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

