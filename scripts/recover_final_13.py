#!/usr/bin/env python3
"""Target only the last 13 original Switch Pokémon models.

Requires locally available original Switch model/animation/texture archives
from games the user is authorized to extract. Never downloads or publishes
third-party model binaries; never accepts static substitutes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from import_switch_game_assets import (
    CACHE, detect_game, discover_default_inputs, extract_input,
    scan_models, scan_animations, attach_animations, dedupe_jobs,
)
from recover_missing_switch_models import is_usable, loaded_manifest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".cache" / "final-13-recovery"
TARGETS = {
    854: ("Sinistea", "swsh", 972),
    864: ("Cursola", "swsh", 947),
    931: ("Squawkabilly", "sv", 1064),
    938: ("Tadbulb", "sv", 1044),
    939: ("Bellibolt", "sv", 1045),
    961: ("Wugtrio", "sv", 1034),
    963: ("Finizen", "sv", 1037),
    972: ("Houndstone", "sv", 1029),
    986: ("Brute Bonnet", "sv", 1083),
    988: ("Slither Wing", "sv", 1088),
    991: ("Iron Bundle", "sv", 1096),
    992: ("Iron Hands", "sv", 1093),
    993: ("Iron Jugulis", "sv", 1094),
}


def self_test() -> None:
    from import_switch_game_assets import national_dex_for_model_id
    assert len(TARGETS) == 13 and len(set(TARGETS)) == 13
    for dex, (_name, game, model_id) in TARGETS.items():
        assert national_dex_for_model_id(model_id, game) == dex, (
            f"{game} internal model {model_id} mapped to the wrong Pokemon"
        )
    print("All 13 game-specific model ID mappings passed.")


def find_sources(user_paths: list[Path]) -> list[Path]:
    paths = user_paths if user_paths else discover_default_inputs()
    selected: dict[Path, Path] = {}
    for path in paths:
        source = path.expanduser().resolve()
        if detect_game(source) in {"sv", "swsh"} and source.exists():
            selected[source] = source
    return sorted(selected.values(), key=lambda p: str(p).lower())


def inspect_sources(paths: list[Path]) -> tuple[list[dict], list[str]]:
    models: list[dict] = []
    animations: list[dict] = []
    errors = []
    for path in paths:
        try:
            root, game = extract_input(path)
            found_models = scan_models(root, game)
            found_animations = scan_animations(root, game)
            models.extend(found_models)
            animations.extend(found_animations)
            print(f"  {path.name}: {len(found_models)} source models, "
                  f"{len(found_animations)} animations ({game})", flush=True)
        except Exception as exc:
            error = f"{path}: {type(exc).__name__}: {exc}"
            print("  SOURCE ERROR: " + error, flush=True)
            errors.append(error)
    attach_animations(models, animations)
    return dedupe_jobs(models), errors


def make_report(
    jobs: list[dict], sources: list[Path], importer_exit: int | None,
    source_errors: list[str],
) -> dict:
    by_dex = {int(job["dex"]): job for job in jobs if int(job["dex"]) in TARGETS}
    manifest = loaded_manifest()
    rows = []
    for dex, (name, game, source_id) in TARGETS.items():
        job = by_dex.get(dex)
        installed = is_usable(dex, manifest)
        status = (
            "structurally_valid_on_disk" if installed else
            "no_source_archives" if not sources else
            "missing_source_model" if job is None else
            "model_present_idle_missing" if not job.get("animations") else
            "source_found_conversion_not_validated"
        )
        rows.append({
            "dex": dex, "name": name, "game": game,
            "gameModelId": source_id,
            "status": status, "validGLB": installed,
            "sourceModel": job["source"] if job else "",
            "idleSourceFiles": len(job.get("animations", [])) if job else 0,
            "convertedWithOriginalTextures": installed,
        })
    REPORT.mkdir(parents=True, exist_ok=True)
    result = {
        "targetCount": 13, "validModels": sum(x["validGLB"] for x in rows),
        "sourceArchives": [str(source) for source in sources],
        "importerExitCode": importer_exit,
        "sourceErrors": source_errors,
        "models": rows,
        "note": "Structural validation is not visual review. Only original source assets "
                "owned/authorized for use should be processed; no third-party binaries are republished.",
    }
    (REPORT / "report.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    columns = ("dex", "name", "game", "gameModelId", "status", "validGLB", "idleSourceFiles", "sourceModel")
    (REPORT / "report.tsv").write_text(
        "\t".join(columns) + "\n" +
        "".join("\t".join(str(row[key]) for key in columns) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"\nFinal 13: {result['validModels']}/13 structurally valid model(s).")
    for row in rows:
        label = "PASS" if row["validGLB"] else "MISSING"
        print(f"  {label} #{row['dex']:04d} {row['name']}: "
              f"{row['status']} (source ID pm{row['gameModelId']:04d})")
    print(f"Report: {REPORT / 'report.tsv'}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="*", type=Path,
                        help="optional original SV / SwSh archives or extracted folders")
    parser.add_argument("--scan-only", action="store_true",
                        help="inventory only; never attempt conversion")
    parser.add_argument("--self-test", action="store_true",
                        help="verify all 13 National-Dex/source-ID pairs")
    parser.add_argument("--force", action="store_true",
                        help="reconvert target species even when a usable GLB exists")
    args = parser.parse_args()
    self_test()
    if args.self_test:
        return 0
    sources = find_sources(args.sources)
    print("\nPokedex 3D Max - original Switch recovery, final 13 species")
    print(f"Found {len(sources)} local SV / SwSh source archive(s) or folder(s).")
    if not sources:
        print("No source archives were found. The original model binary files "
              "are not stored in this GitHub repo.")
        print("Place your legitimately obtained SV and SwSh model, animation "
              "and texture archives into switch-assets or drag the files "
              "onto recover-final-13.bat.")
        print("Expected game prefixes include SV-Poke..., SV-PokeAnim..., "
              "SwSh-Poke... and SwSh-PokeAnim....")
        make_report([], sources, None, [])
        return 2

    jobs, errors = inspect_sources(sources)
    candidates = [job for job in jobs if job["dex"] in TARGETS]
    found = {job["dex"] for job in candidates}
    print(f"\nFound {len(found)}/13 original source model(s).")
    for job in candidates:
        print(f"  #{job['dex']:04d}: pm{job['modelId']:04d} ({job['game']}), "
              f"compatible idle source clips: {len(job.get('animations') or [])}")
    if args.scan_only:
        make_report(jobs, sources, None, errors)
        return 1 if errors else 0

    # The main importer already checks complete embedded textures and an
    # actual compatible idle and preserves unselected Dex entries.
    cmd = [
        sys.executable, "-u", str(ROOT / "scripts" / "import_switch_game_assets.py"),
        *map(str, sources),
        *(item for dex in sorted(TARGETS) for item in ("--dex", str(dex))),
    ]
    if args.force:
        cmd.append("--force")
    print("\nImporting only the requested 13; existing other models untouched.", flush=True)
    importer_exit = subprocess.call(cmd, cwd=ROOT)
    result = make_report(jobs, sources, importer_exit, errors)
    if importer_exit:
        print(f"Importer exited {importer_exit}. Review the errors above.")
    if result["validModels"] < 13:
        print("Remaining species need matching original rig, animation or "
              "texture sources, or conversion repairs.")
    print("Do not mark these Pokemon Finished until textures, pose and idles "
          "are visually reviewed.")
    return 0 if result["validModels"] == 13 and importer_exit == 0 and not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
