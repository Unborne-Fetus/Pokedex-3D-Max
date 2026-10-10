#!/usr/bin/env python3
"""Diagnose locally available source material for 122 reported missing Switch models.

This diagnostic never generates placeholders, modifies the live manifest, or
claims that locating a model alone proves textures and animation quality.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from import_switch_game_assets import (
    ANIM_EXTS,
    DEX_RE,
    IMAGE_EXTS,
    MODEL_EXTS,
    attach_animations,
    canonical_regular_form,
    dedupe_jobs,
    detect_game,
    discover_default_inputs,
    extract_input,
    infer_form,
    national_dex_for_model_id,
    scan_animations,
    scan_models,
)
from recover_missing_switch_models import is_usable, loaded_manifest, ROOT

MISSING_LIST = ROOT / "data" / "reported-missing-models-2026-10-09.tsv"
REPORT_ROOT = ROOT / ".cache" / "remaining-model-diagnosis"


def read_reported() -> dict[int, str]:
    data: dict[int, str] = {}
    for line in MISSING_LIST.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t", 1)
        if len(fields) == 2 and fields[0].isdigit():
            data[int(fields[0])] = fields[1].strip()
    if len(data) != 122:
        raise ValueError(f"Expected 122 reported species; got {len(data)}")
    return data


def source_files(args: list[Path]) -> list[Path]:
    paths = list(args) if args else discover_default_inputs()
    seen: set[Path] = set()
    out = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


def analyze(paths: list[Path], requested: dict[int, str]) -> dict:
    jobs = []
    animations = []
    other_forms: dict[int, set[str]] = defaultdict(set)
    texture_possible: dict[str, bool] = defaultdict(bool)
    sources_by_game: Counter = Counter()
    errors: list[str] = []
    discovered: list[dict] = []

    for source in paths:
        game = detect_game(source)
        if game == "unknown":
            errors.append(f"Unknown source game for {source}; use an SV, SwSh, LA, ZA, LGPE, or BDSP folder/name")
            continue
        if not source.exists():
            errors.append(f"Source not found: {source}")
            continue
        try:
            extracted, game = extract_input(source)
            source_models = scan_models(extracted, game)
            source_anims = scan_animations(extracted, game)
            texture_available = False
            # Also look for BNTX sources that the conversion pipeline can decode.
            for file in extracted.rglob("*"):
                if not file.is_file():
                    continue
                suffix = file.suffix.lower()
                if suffix in IMAGE_EXTS or suffix == ".bntx":
                    texture_available = True
                if suffix not in MODEL_EXTS:
                    continue
                match = DEX_RE.search(str(file))
                if not match:
                    continue
                dex = national_dex_for_model_id(int(match.group(1)), game)
                if dex in requested:
                    catalog_form, _ = canonical_regular_form(file, dex, game)
                    if catalog_form != "regular":
                        other_forms[dex].add(catalog_form)
            texture_possible[game] |= texture_available
            sources_by_game[game] += 1
            jobs.extend(source_models)
            animations.extend(source_anims)
            discovered.append({
                "input": str(source),
                "game": game,
                "modelCandidates": len(source_models),
                "animationCandidates": len(source_anims),
                "hasPotentialTextures": texture_available,
            })
            print(f"{source.name}: {len(source_models)} regular models, "
                  f"{len(source_anims)} animations, game={game}", flush=True)
        except Exception as exc:
            # An invalid archive must not prevent diagnostics of other sources.
            errors.append(f"{source}: {type(exc).__name__}: {exc}")

    attach_animations(jobs, animations)
    candidates = defaultdict(list)
    for job in jobs:
        if int(job["dex"]) in requested:
            candidates[int(job["dex"])].append(job)
    installed = loaded_manifest()
    rows = []
    for dex, name in requested.items():
        options = candidates[dex]
        chosen = dedupe_jobs(options)[0] if options else None
        ready = is_usable(dex, installed)
        with_idle = bool(chosen and chosen.get("animations"))
        possible_texture = bool(chosen and texture_possible.get(chosen["game"], False))
        if ready:
            status = "already_valid_locally"
        elif not paths:
            status = "no_local_switch_sources"
        elif not options and other_forms[dex]:
            status = "only_other_forms_found"
        elif not options:
            status = "regular_model_not_found_in_sources"
        elif not with_idle:
            status = "matching_idle_animation_not_found"
        elif not possible_texture:
            status = "texture_source_not_confirmed"
        else:
            status = "ready_to_attempt_conversion"
        rows.append({
            "dex": dex,
            "name": name,
            "status": status,
            "installedValid": ready,
            "sourceGame": chosen["game"] if chosen else None,
            "sourceModelId": chosen.get("modelId") if chosen else None,
            "sourceModel": str(chosen["source"]) if chosen else None,
            "matchingIdleCandidates": len(chosen.get("animations", [])) if chosen else 0,
            "potentialTextureSourcesByGame": possible_texture,
            "otherForms": sorted(other_forms[dex]),
        })

    counts = dict(sorted(Counter(row["status"] for row in rows).items()))
    return {
        "note": "Candidate detection is not proof of a visually correct GLB. "
                "Use the converter and verify original textures, poses and idle animations.",
        "reportedCount": len(rows),
        "sourcesScanned": discovered,
        "sourceSearchHint": "Original sources: project switch-assets, Downloads, Desktop, MEGA cached archives, or .cache/switch-game-assets/extracted. Published GLBs are not original source archives.",
        "sourceCountsByGame": dict(sources_by_game),
        "countsByStatus": counts,
        "scanErrors": errors,
        "pokemon": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="*", type=Path,
                        help="optional original Switch archive files or extracted source folders")
    args = parser.parse_args()
    requested = read_reported()
    sources = source_files(args.sources)
    print(f"Diagnosing {len(requested)} user-reported missing regular Switch models.")
    print(f"Available original source archives/folders: {len(sources)}", flush=True)
    if sources:
        for source in sources:
            print(f"  FOUND {source}", flush=True)
    else:
        print("\\nNo original model, animation, or texture sources were found.")
        print("This does NOT mean these 122 Pokemon are impossible to recover.")
        print("Checked the project switch-assets folder, Downloads, Desktop,")
        print("the MEGA archive cache, and earlier extracted importer caches.")
        print("To continue, place archives extracted from your own Switch games")
        print("under switch-assets in a clearly named game folder (SV, SwSh,")
        print("LA, ZA, BDSP or LGPE), or drag the source folder onto this BAT.")
        print("Then run the matching recovery batches again.")
        print("The already-published GLB models cannot supply missing original")
        print("model/animation source files.", flush=True)
    result = analyze(sources, requested)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    path = REPORT_ROOT / "report.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tsv = REPORT_ROOT / "report.tsv"
    columns = ("dex", "name", "status", "sourceGame", "sourceModelId",
               "matchingIdleCandidates", "potentialTextureSourcesByGame")
    tsv.write_text("\t".join(columns) + "\n" + "".join(
        "\t".join(str(row.get(c, "") if row.get(c) is not None else "") for c in columns) + "\n"
        for row in result["pokemon"]), encoding="utf-8")
    print("\nDiagnosis summary:")
    for status, count in result["countsByStatus"].items():
        print(f"  {status}: {count}")
    for error in result["scanErrors"]:
        print(f"  SOURCE ISSUE: {error}")
    print(f"Full JSON report: {path}")
    print(f"Spreadsheet-friendly report: {tsv}")
    print("These are candidate-source checks only; no Pokemon was marked finished.")
    return 0 if not result["scanErrors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
