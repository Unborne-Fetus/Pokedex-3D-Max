#!/usr/bin/env python3
"""Regression test: Switch game model IDs must not replace National Dex species."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = [line.split("\t") for line in (ROOT / "data/sv_model_dex.tsv").read_text(encoding="utf-8").splitlines()
        if line and line[0].isdigit()]
national = {int(source): int(dex) for source, dex, *_ in rows}
models = json.loads((ROOT / "web/models/switch-manifest.json").read_text(encoding="utf-8"))
by_dex = {int(model["dex"]): model for model in models}
assert len(models) == len(by_dex), "Duplicate National Dex slots"
for source_id in [*range(1010, 1021), *range(1022, 1026)]:
    target = national[source_id]
    # A misplaced GLB must never be republished just because the old
    # source-game asset number happens to be a real National Dex number.
    assert not (ROOT / "web/models/switch" / f"{source_id:04d}" / "regular.glb").exists(), (
        "Misnumbered Switch GLB remains in the repository", source_id)
    assert target != source_id, f"Bad internal ID table: {source_id}"
    destination = by_dex.get(target)
    assert destination is not None, f"Missing restored model at #{target}"
    assert int(destination["dex"]) == target
    assert (ROOT / "web/models/switch" / f"{target:04d}" / "regular.glb").is_file(), (
        "Correctly numbered original GLB missing", source_id, target)
    if target <= 917:
        assert int(destination.get("sourceModelId", -1)) == source_id, (source_id, target)
    # A high Dex number may be legitimate once sourced from the *correct* model ID,
    # but the old pm1010-pm1025 models must never masquerade as those species.
    legacy = by_dex.get(source_id)
    if legacy is not None:
        assert int(legacy.get("sourceModelId", source_id)) != source_id, source_id
pecharunt = by_dex.get(1025)
if pecharunt is not None:
    assert int(pecharunt.get("sourceModelId", 0)) == 1131, "Lokix cannot be Pecharunt"
assert by_dex[920]["dex"] == 920, "Lokix is #920"
print("National Dex alignment verified for SV internal IDs 1010-1025")
