#!/usr/bin/env python3
"""Verify every published National Dex slot against its original Switch ID."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mapping(filename: str) -> dict[int, int]:
    with (ROOT / "data" / filename).open(encoding="utf-8", newline="") as f:
        return {int(r["model_id"]): int(r["dex"]) for r in csv.DictReader(
            (line for line in f if not line.startswith("#")), delimiter="\t")}


SWSH = mapping("swsh_model_dex.tsv")
SV = mapping("sv_model_dex.tsv")


def canonical(game: str, model_id: int) -> int:
    game = game.lower()
    if game.startswith("sv"):
        return SV.get(model_id, 0) if model_id >= 1001 else SWSH.get(model_id, model_id)
    if game.startswith("swsh"):
        return SWSH.get(model_id, model_id)
    if (game.startswith("la") or game.startswith("za")) and 1001 <= model_id <= 1007:
        return SV.get(model_id, 0)
    return model_id


def read_tsv(filename: str) -> list[dict[str, str]]:
    with (ROOT / filename).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


names = {int(r["dex"]): r["name"] for r in read_tsv("data/species_names.tsv")}
assert set(names) == set(range(1, 1026)), "National Dex names must include #1–#1025 exactly"
models = json.loads((ROOT / "web/models/switch-manifest.json").read_text(encoding="utf-8"))
by_dex = {int(r["dex"]): r for r in models}
assert len(by_dex) == len(models), "Duplicate National Dex numbers"
inventory_js = (ROOT / "web/models/github-inventory.js").read_text(encoding="utf-8")
match = re.search(r"window.POKEDEX3D_PUBLIC_INVENTORY = (\{.*\});", inventory_js)
assert match, "Public inventory JavaScript is malformed"
public = json.loads(match[1])
public_by_dex = {int(r["dex"]): r for r in public["entries"]}
assert len(public_by_dex) == len(public["entries"]) == public["count"], "Duplicate public model IDs"

history = {int(r["dex"]): r for r in json.loads(
    (ROOT / "data/switch-texture-repair-report.json").read_text(encoding="utf-8")
)["repaired"]}
audit = read_tsv("data/national-dex-model-audit.tsv")
assert len(audit) == 1025, "Audit must include every National Dex slot"
for dex, record in enumerate(audit, 1):
    assert int(record["dex"]) == dex
    assert record["name"] == names[dex]
    current = by_dex.get(dex)
    online = public_by_dex.get(dex)
    assert (record["local_model"] == "available") == (current is not None), dex
    assert (record["public_model"] == "available") == (online is not None), dex
    if online:
        assert online["path"] == f"{dex:04d}/regular.glb", (dex, online["path"])
        if online.get("sourceModelId"):
            assert canonical(str(online["sourceGame"]), int(online["sourceModelId"])) == dex, dex
    if not current:
        continue
    assert current.get("name", names[dex]) == names[dex], (dex, current.get("name"))
    assert "switch/" + f"{dex:04d}/regular.glb" in current["url"], dex
    if current.get("sourceModelId"):
        assert canonical(str(current["sourceGame"]), int(current["sourceModelId"])) == dex, dex
    elif dex in history:
        old = history[dex]
        source_id = int(re.search(r"pm(\d{4})", old["source"])[1])
        assert canonical(old["game"], source_id) == dex, (
            dex, old["game"], source_id, canonical(old["game"], source_id))
    # Entries without original source IDs are name-checked catalog records,
    # not represented as binary/visual proof.
assert 1025 not in by_dex and 1025 not in public_by_dex, "Pecharunt must never display Lokix"
assert 920 in by_dex and 920 in public_by_dex, "Lokix belongs to #920"
print(f"Audited 1,025 slots: {len(by_dex)} local models; {len(public_by_dex)} public models")
