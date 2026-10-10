#!/usr/bin/env python3
"""Recover the missing Switch regular models, in three stable batches.

The missing-Dex snapshot was taken from web/models/switch-manifest.json on
2026-10-09 (759 ready regular models out of 1025). Running a batch never
changes its membership when earlier batches succeed. Existing usable models
are not replaced. No dummy/static model or animation is invented.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "web" / "models" / "switch-manifest.json"
MODEL_ROOT = ROOT / "web" / "models" / "switch"
REPORT_ROOT = ROOT / ".cache" / "missing-model-batches"

# Frozen missing set; do not derive batch 2/3 from a shrinking current catalog.
BASELINE_MISSING = tuple(int(part) for part in (
    "19,20,21,22,27,28,29,30,31,32,33,34,60,61,62,98,99,109,110,118,119,124,138,139,140,141,161,162,163,164,165,166,177,178,186,201,202,213,218,219,222,238,241,251,261,262,263,264,270,271,272,273,274,275,276,277,290,291,292,293,294,295,300,301,313,314,320,321,327,337,338,341,342,343,344,345,346,347,348,351,360,366,367,368,369,385,386,412,413,421,422,423,479,487,492,493,540,541,542,550,555,580,581,585,586,641,642,645,646,647,648,649,650,651,652,653,654,655,656,657,658,659,660,661,662,663,664,665,666,667,668,669,670,671,672,673,674,675,676,677,678,679,680,681,682,683,684,685,686,687,688,689,690,691,692,693,694,695,696,697,698,699,700,701,708,713,714,715,725,735,736,746,750,770,771,774,775,776,777,778,779,780,781,782,783,784,785,786,787,788,789,790,791,792,793,794,795,796,797,798,799,800,803,804,854,862,864,865,875,877,889,893,898,899,900,905,906,907,908,911,912,915,916,917,922,925,928,930,931,932,938,939,941,943,947,960,961,962,963,972,973,975,979,980,981,983,986,987,988,991,992,993,994,995,996,997,998,999,1000,1003,1004,1005,1006,1008,1009,1021"
).split(","))
BATCHES = (BASELINE_MISSING[:100], BASELINE_MISSING[100:200],
           BASELINE_MISSING[200:])
assert len(BASELINE_MISSING) == 266 and len(set(BASELINE_MISSING)) == 266
assert tuple(len(group) for group in BATCHES) == (100, 100, 66)


def loaded_manifest() -> dict[int, dict]:
    if not MANIFEST.is_file():
        return {}
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("switch-manifest.json must be a list")
    return {int(e["dex"]): e for e in entries if isinstance(e, dict)
            and e.get("form") == "regular" and e.get("ready") is not False}


def is_usable(dex: int, entries: dict[int, dict]) -> bool:
    """Validate structure, embedded base-color textures, and an actual idle."""
    if dex not in entries:
        return False
    path = MODEL_ROOT / f"{dex:04d}" / "regular.glb"
    if not path.is_file() or path.stat().st_size <= 1024:
        return False
    from import_switch_game_assets import (
        choose_idle, glb_textures_complete, parse_glb_doc,
    )
    try:
        document = parse_glb_doc(path)
        if not isinstance(document, dict) or not document.get("meshes") or not document.get("scenes"):
            return False
        if not glb_textures_complete(path):
            return False
        clips = [clip.get("name") for clip in document.get("animations", [])
                 if isinstance(clip, dict) and clip.get("channels") and clip.get("samplers")]
        idle = entries[dex].get("idleAnimation")
        return bool((idle in clips if idle else False) or choose_idle(clips))
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return False


def pending_for(batch: tuple[int, ...]) -> list[int]:
    entries = loaded_manifest()
    return [dex for dex in batch if not is_usable(dex, entries)]


def run_script(script: str, args: list[str]) -> int:
    command = [sys.executable, "-u", str(ROOT / "scripts" / script), *args]
    print("\nRunning: " + script + " (" + str(len(args)) + " arguments)", flush=True)
    return subprocess.call(command, cwd=ROOT)


def recover_from_release(pending: list[int]) -> None:
    """Use verified existing releases where possible, without requiring all IDs."""
    from remote_model_pack import DEFAULT_MANIFEST_URL, download_json
    url = os.environ.get("POKEDEX3D_MODEL_PACK_MANIFEST", DEFAULT_MANIFEST_URL)
    try:
        remote = download_json(url)
        available = {int(e["dex"]) for e in remote.get("entries", [])
                     if isinstance(e, dict) and e.get("form", "regular") == "regular"}
    except (OSError, TimeoutError, ValueError, KeyError, TypeError,
            urllib.error.URLError) as exc:
        print(f"Online model pack unavailable: {exc}. Checking local Switch archives.")
        return
    selected = [dex for dex in pending if dex in available]
    if not selected:
        print("No missing members of this batch exist in the current verified release.")
        return
    print(f"Found {len(selected)} available in the verified remote model pack.")
    code = run_script("remote_model_pack.py", [
        "install", "--manifest-url", url,
        *(value for dex in selected for value in ("--dex", str(dex))),
    ])
    if code:
        print(f"Online recovery returned {code}; local recovery can still succeed.")


def names() -> dict[int, str]:
    result = {}
    path = ROOT / "data" / "species_names.tsv"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split("\t", 1)
            if len(parts) == 2 and parts[0].isdigit():
                result[int(parts[0])] = parts[1].strip()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=int, choices=(1, 2, 3))
    parser.add_argument("--local-only", action="store_true",
                        help="skip downloading the signed/checksummed remote model pack")
    parser.add_argument("--report-only", action="store_true",
                        help="check models already installed without importing")
    parser.add_argument("sources", nargs="*", type=Path,
                        help="optional locally owned Switch asset ZIP/7z files or folders")
    args = parser.parse_args()
    batch = BATCHES[args.batch - 1]
    labels = names()
    print(f"Missing regular Switch models - batch {args.batch}/3 "
          f"({len(batch)} species; #{batch[0]:04d} to #{batch[-1]:04d})", flush=True)
    initial_pending = pending_for(batch)
    print(f"Already recovered: {len(batch) - len(initial_pending)}; "
          f"still missing or invalid: {len(initial_pending)}", flush=True)

    importer_exit = 0
    if initial_pending and not args.report_only:
        if not args.local_only:
            recover_from_release(initial_pending)
        unresolved = pending_for(batch)
        if unresolved:
            print(f"Trying original Switch game model/animation/texture archives "
                  f"for {len(unresolved)} models...")
            # Targeted import merges the manifest and preserves all other models.
            # It will not silently use older generic 3D models or static stand-ins.
            importer_exit = run_script("import_switch_game_assets.py", [
                *(str(p) for p in args.sources),
                *(value for dex in unresolved for value in ("--dex", str(dex))),
            ])
            if importer_exit:
                print(f"Local importer returned exit code {importer_exit}.")

    still_missing = pending_for(batch)
    recovered = [dex for dex in batch if dex not in still_missing]
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        "batch": args.batch,
        "total": len(batch),
        "recovered": len(recovered),
        "missing": len(still_missing),
        "recoveredDex": recovered,
        "missingDex": still_missing,
        "importerExitCode": importer_exit,
    }
    target = REPORT_ROOT / f"batch-{args.batch}.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nBatch {args.batch}: {len(recovered)}/{len(batch)} verified regular "
          f"models (texture bindings and embedded idle checked).")
    if still_missing:
        for dex in still_missing:
            print(f"  MISSING #{dex:04d} {labels.get(dex, '')}")
        print("Supply legitimately obtained original Switch model, animation, "
              "and texture archives, then rerun this batch.")
        print("Incomplete and static models are intentionally not marked finished.")
    else:
        print("All batch models are installed and structurally verified.")
        print("Visual texture, pose, and animation review is still required.")
    print(f"Report: {target}")
    return 0 if not still_missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
