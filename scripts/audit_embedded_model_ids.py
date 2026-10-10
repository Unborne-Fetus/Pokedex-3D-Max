#!/usr/bin/env python3
"""Audit the identity and integrity of every published Switch GLB.

Use original Git blob hashes when known, otherwise extract the pmNNNN game
model ID from the actual GLB images/meshes/nodes. Do not trust numbered
folders or Pokémon labels as evidence of model identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = re.compile(r"(?<![A-Za-z0-9])pm(\d{4})(?!\d)", re.I)
CATEGORIES = ("images", "meshes", "nodes", "materials")


def mapping(name: str) -> dict[int, int]:
    result = {}
    for line in (ROOT / "data" / name).read_text(encoding="utf-8").splitlines():
        cells = line.split("\t")
        if len(cells) > 1 and cells[0].isdigit() and cells[1].isdigit():
            result[int(cells[0])] = int(cells[1])
    return result


SWSH = mapping("swsh_model_dex.tsv")
SV = mapping("sv_model_dex.tsv")


def national_id(source: int, game: str) -> int:
    game = str(game).lower().replace("official-game-assets:", "")
    if game.startswith("sv"):
        return SV.get(source, 0) if source >= 1001 else SWSH.get(source, source)
    if game.startswith("swsh"):
        return SWSH.get(source, source)
    if game.startswith(("la", "za")) and 1001 <= source <= 1007:
        return SV.get(source, 0)
    return source


def read_glb(path: Path) -> dict:
    with path.open("rb") as handle:
        header = handle.read(20)
        if len(header) != 20:
            raise ValueError("truncated GLB header")
        magic, version, total, size, kind = struct.unpack("<5I", header)
        if (magic, version, kind) != (0x46546C67, 2, 0x4E4F534A):
            raise ValueError("incorrect GLB header")
        if total != path.stat().st_size or size < 2 or size > 32 * 1024 * 1024:
            raise ValueError("invalid GLB length")
        payload = handle.read(size)
        if len(payload) != size:
            raise ValueError("truncated GLB JSON")
        return json.loads(payload)


def git_blob_sha(path: Path) -> str:
    digest = hashlib.sha1()
    digest.update(("blob " + str(path.stat().st_size)).encode() + b"\0")
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_ids(doc: dict) -> dict[str, list[int]]:
    result = {}
    for section in CATEGORIES:
        observed = []
        for entry in doc.get(section, []):
            if not isinstance(entry, dict):
                continue
            observed.extend(int(m.group(1)) for m in
                            MODEL.finditer(str(entry.get("name", ""))))
        if observed:
            result[section] = sorted(set(observed))
    return result


def embedded_id(doc: dict) -> tuple[int | None, bool, dict[str, list[int]]]:
    groups = source_ids(doc)
    all_ids = {value for values in groups.values() for value in values}
    if len(all_ids) > 1:
        return None, True, groups
    return (next(iter(all_ids)) if all_ids else None), False, groups


def audit(strict: bool = False) -> dict:
    manifest = json.loads(
        (ROOT / "web/models/switch-manifest.json").read_text(encoding="utf-8")
    )
    known = json.loads(
        (ROOT / "data/verified_switch_glb_provenance.json").read_text(encoding="utf-8")
    )["models"]
    names = {}
    for line in (ROOT / "data/species_names.tsv").read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit():
            names[int(parts[0])] = parts[1]
    problems, uncertain, warnings = [], [], []
    checks = []
    found_ids = set()
    for entry in manifest:
        dex = int(entry["dex"])
        if dex in found_ids or not 1 <= dex <= 1025:
            problems.append({"dex": dex, "reason": "duplicate/invalid National Dex slot"})
            continue
        found_ids.add(dex)
        file = ROOT / "web/models/switch" / f"{dex:04d}" / "regular.glb"
        if not file.is_file():
            problems.append({"dex": dex, "reason": "model file missing"})
            continue
        try:
            doc = read_glb(file)
            blob = git_blob_sha(file)
            if entry.get("sourceBlobSha") and entry["sourceBlobSha"] != blob:
                problems.append({"dex": dex, "reason": "catalog SHA mismatches model file"})
            internal, conflict, sections = embedded_id(doc)
            original = known.get(blob)
            if original:
                source = int(original["sourceModelId"])
                game = original["sourceGame"]
                certainty = "original-glb-sha1"
                if conflict or (internal is not None and internal != source):
                    warnings.append({"dex": dex, "reason": "embedded names differ from original proof",
                                     "embedded": sections, "source": source})
            else:
                source = internal
                game = entry.get("sourceGame")
                certainty = "embedded-game-source-id" if source is not None and game else "unverified"
                if conflict:
                    warnings.append({"dex": dex, "reason": "multiple embedded source IDs",
                                     "embedded": sections})
            expected = national_id(source, game) if source is not None and game else None
            if expected is None:
                uncertain.append({"dex": dex, "name": names.get(dex), "embedded": sections,
                                  "sourceGame": game})
            elif dex != expected:
                problems.append({"dex": dex, "name": names.get(dex),
                                 "reason": "wrong Pokémon in GLB", "source": source,
                                 "sourceGame": game, "actualDex": expected})
            checks.append({"dex": dex, "name": names.get(dex), "sourceModelId": source,
                           "sourceGame": game, "verified": certainty,
                           "actualDex": expected})
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError,
                json.JSONDecodeError) as error:
            problems.append({"dex": dex, "reason": str(error)})
    summary = {
        "examined": len(checks),
        "catalogCount": len(manifest),
        "verifiedByOriginalHash": sum(x["verified"] == "original-glb-sha1" for x in checks),
        "verifiedByEmbeddedId": sum(x["verified"] == "embedded-game-source-id" for x in checks),
        "unverified": uncertain,
        "wrongOrBroken": problems,
        "warnings": warnings,
        "records": checks,
    }
    report = ROOT / ".cache/national-dex-embedded-audit.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(
        f"GLB audit: {summary['examined']}/{summary['catalogCount']} examined; "
        f"{summary['verifiedByOriginalHash']} SHA-proven, "
        f"{summary['verifiedByEmbeddedId']} embedded-ID-proven, "
        f"{len(uncertain)} unverified, {len(problems)} wrong/broken, "
        f"{len(warnings)} source-name warnings."
    )
    for problem in problems:
        print("ERROR", json.dumps(problem, ensure_ascii=False))
    for item in uncertain[:15]:
        print("UNVERIFIED", json.dumps(item, ensure_ascii=False))
    for warning in warnings[:15]:
        print("WARNING", json.dumps(warning, ensure_ascii=False))
    print("Detailed report:", report)
    if strict and problems:
        raise SystemExit(1)
    return summary


def self_test() -> None:
    assert national_id(761, "swsh") == 701
    assert national_id(1025, "sv") == 920
    assert national_id(1010, "sv") == 906
    assert national_id(1002, "la") == 900
    assert embedded_id({"images": [{"name": "pm1025_00_body"}]})[0] == 1025
    assert embedded_id({"meshes": [{"name": "pm0701_00"}, {"name": "pm0761_00"}]})[1]
    print("GLB embedded-source parser self-test passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        audit(args.strict)
