#!/usr/bin/env python3
"""Audit all 1,025 visible National Dex entries against their source-game IDs.

Legacy upload folders are historical storage keys. They are not Pokémon IDs:
the browser normalizes them before displaying them, and validates each GLB.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mapping(filename: str) -> dict[int, int]:
    with (ROOT / "data" / filename).open(encoding="utf-8", newline="") as f:
        return {int(row["model_id"]): int(row["dex"]) for row in csv.DictReader(
            (line for line in f if not line.startswith("#")), delimiter="\t")}


SWSH = mapping("swsh_model_dex.tsv")
SV = mapping("sv_model_dex.tsv")


def canonical(game: str, model_id: int) -> int:
    game = game.lower()
    if game.startswith(("sv", "za")):
        return SV.get(model_id, 0) if model_id >= 1001 else SWSH.get(model_id, model_id)
    if game.startswith("swsh"):
        return SWSH.get(model_id, model_id)
    if game.startswith("la") and 1001 <= model_id <= 1007:
        return SV.get(model_id, 0)
    return model_id


def read_tsv(filename: str) -> list[dict[str, str]]:
    with (ROOT / filename).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def visible(rows: list[dict]) -> dict[int, dict]:
    """Mirror browser's source-ID normalization and first-available priority."""
    selected = {}
    for row in rows:
        original = int(row["dex"])
        source_id = int(row.get("sourceModelId") or row.get("modelId") or 0)
        game = str(row.get("sourceGame") or "")
        corrected = canonical(game, source_id) if source_id else original
        if 1 <= corrected <= 1025:
            selected.setdefault(corrected, row)
    return selected


names = {int(r["dex"]): r["name"] for r in read_tsv("data/species_names.tsv")}
assert set(names) == set(range(1, 1026)), "National Dex must contain exactly #1–#1025"
raw_local = json.loads((ROOT / "web/models/switch-manifest.json").read_text(encoding="utf-8"))
inventory_js = (ROOT / "web/models/github-inventory.js").read_text(encoding="utf-8")
match = re.search(r"window.POKEDEX3D_PUBLIC_INVENTORY = (\{.*\});", inventory_js)
assert match, "Public inventory JavaScript is malformed"
public = json.loads(match[1])
raw_public = public["entries"]
assert len(raw_public) == public["count"]
assert len({int(r["dex"]) for r in raw_local}) == len(raw_local)
assert len({int(r["dex"]) for r in raw_public}) == len(raw_public)

local = visible(raw_local)
remote = visible(raw_public)
audit = read_tsv("data/national-dex-model-audit.tsv")
assert len(audit) == 1025

for dex, record in enumerate(audit, 1):
    assert int(record["dex"]) == dex
    assert record["name"] == names[dex], dex
    current = local.get(dex)
    online = remote.get(dex)
    assert (record["local_model"] == "available") == (current is not None), dex
    assert (record["public_model"] == "available") == (online is not None), dex
    chosen = current or online
    if not chosen:
        assert record["verification"] == "missing", dex
        continue
    original = int(chosen["dex"])
    internal = int(chosen.get("sourceModelId") or chosen.get("modelId") or 0)
    game = str(chosen.get("sourceGame") or "")
    assert int(record["original_catalog_dex"] or dex) == original, dex
    assert record["source_game"] == game, dex
    assert str(record["source_model_id"]) == (str(internal) if internal else ""), dex
    if internal:
        assert canonical(game, internal) == dex, (dex, game, internal)
    if original != dex:
        assert record["verification"].startswith("reindexed-"), dex

# Regression: these Gen 8 game-internal IDs used to impersonate Gen 9 species.
for internal, real_dex, wrong_dex in [
    (942, 876, 942), (964, 852, 964), (965, 853, 965),
    (920, 823, 920), (1025, 920, 1025),
]:
    game = "sv" if internal == 1025 else "za"
    assert canonical(game, internal) == real_dex
    if wrong_dex in (942, 964, 965, 1025):
        assert wrong_dex not in remote, f"Wrong model still masquerades as #{wrong_dex}"
assert 1025 not in local and 1025 not in remote, "Never show Lokix as Pecharunt"
assert 852 in remote and 853 in remote and 876 in remote
assert set(range(1, 1026)) == set(names), "Even missing models retain their correct Dex labels"
print(f"Audited 1,025 slots: {len(local)} local, {len(remote)} public, "
      f"{sum(1 for r in audit if r['verification'].startswith('reindexed-'))} reindexed")
