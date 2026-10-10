#!/usr/bin/env python3
"""Fix the +90-degree imported root rotation in the Oct 9 recovered models.

Apply the same GLB-space orientation repair as the Caterpie line, not a camera
rotation. Leave meshes, skinning, animation buffers and embedded textures alone.
The listed IDs are the 144 GLBs added in commit ed92aec.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "web/models/switch"
MANIFEST_JSON = ROOT / "web/models/switch-manifest.json"
MANIFEST_JS = ROOT / "web/models/switch-manifest.js"
RECOVERED_IDS = tuple(int(s) for s in (
    "19,20,21,22,27,28,29,30,31,32,33,34,60,61,62,98,99,109,110,118,119,124,138,139,140,141,161,162,163,164,177,178,186,202,213,218,219,222,238,241,251,261,262,263,264,270,271,272,273,274,275,290,291,292,293,294,295,313,314,320,321,337,338,341,342,343,344,345,346,347,348,360,369,385,540,541,542,580,581,659,660,661,662,663,674,675,677,678,679,680,682,683,684,685,686,687,688,689,690,691,692,693,694,695,696,697,698,699,700,701,708,713,714,715,725,736,750,770,771,776,777,780,781,782,783,784,785,786,787,788,789,790,791,792,793,794,795,796,797,798,799,800,803,804"
).split(","))
assert len(RECOVERED_IDS) == 144 and len(set(RECOVERED_IDS)) == 144

IDENTITY = [0, 0, 0, 1]
QUARTER_TURN = math.sqrt(0.5)
REVISION = "recovered-root-1"


def read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if len(data) < 28 or data[:4] != b"glTF":
        raise ValueError(f"Invalid GLB: {path}")
    version, declared_size = struct.unpack_from("<II", data, 4)
    if version != 2 or declared_size != len(data):
        raise ValueError(f"GLB size/version mismatch: {path}")
    json_size, json_type = struct.unpack_from("<II", data, 12)
    if json_type != 0x4E4F534A or 20 + json_size + 8 > len(data):
        raise ValueError(f"Invalid JSON GLB chunk: {path}")
    doc = json.loads(data[20:20 + json_size])
    remaining_chunks = data[20 + json_size:]
    if remaining_chunks[:8][4:] != b"BIN\x00":
        raise ValueError(f"Expected embedded BIN GLB chunk: {path}")
    return doc, remaining_chunks


def is_quarter_turn_x(rotation: object) -> bool:
    if not isinstance(rotation, list) or len(rotation) != 4:
        return False
    return (abs(rotation[0] - QUARTER_TURN) < 0.0001
            and abs(rotation[1]) < 0.0001
            and abs(rotation[2]) < 0.0001
            and abs(rotation[3] - QUARTER_TURN) < 0.0001)


def fix_one(dex: int) -> str:
    path = MODEL_ROOT / f"{dex:04d}" / "regular.glb"
    if not path.is_file():
        raise FileNotFoundError(path)
    doc, original_bin = read_glb(path)
    scene = doc["scenes"][doc.get("scene", 0)]
    roots = [doc["nodes"][i] for i in scene["nodes"]]
    if not roots or not doc.get("meshes") or not doc.get("animations"):
        raise ValueError(f"Missing mesh, scene, or original animations: #{dex}")
    changed = False
    unexpected = []
    for node in roots:
        rotation = node.get("rotation", IDENTITY)
        if is_quarter_turn_x(rotation):
            node["rotation"] = IDENTITY[:]
            changed = True
        elif rotation != IDENTITY:
            unexpected.append(rotation)
    if unexpected:
        raise ValueError(f"Unexpected root rotation #{dex}: {unexpected}")
    if not changed:
        return "already upright"
    doc.setdefault("asset", {}).setdefault("extras", {})[
        "pokedex3dSwitchRootFix"
    ] = 1

    # Re-encode ONLY the JSON chunk. The entire BIN chunk (mesh, bones,
    # animations, images) is copied byte-for-byte into the repaired GLB.
    payload = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    new_data = (struct.pack("<4sII", b"glTF", 2, 20 + len(payload) + len(original_bin))
                + struct.pack("<II", len(payload), 0x4E4F534A)
                + payload + original_bin)
    path.write_bytes(new_data)

    verified_doc, verified_bin = read_glb(path)
    if verified_bin != original_bin or verified_doc.get("animations") != doc["animations"]:
        raise AssertionError(f"Animation, image or rig bytes changed: #{dex}")
    if any(n.get("rotation", IDENTITY) != IDENTITY
           for n in (verified_doc["nodes"][i] for i in
                     verified_doc["scenes"][verified_doc.get("scene", 0)]["nodes"])):
        raise AssertionError(f"Root remains rotated: #{dex}")
    return "fixed"


def update_manifest(fixed_ids: set[int]) -> None:
    if not fixed_ids:
        return
    entries = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    for entry in entries:
        dex = int(entry.get("dex", -1))
        if dex not in fixed_ids or entry.get("form") != "regular":
            continue
        path = MODEL_ROOT / f"{dex:04d}" / "regular.glb"
        entry["bytes"] = path.stat().st_size
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        entry["url"] = entry["url"].split("?")[0] + f"?v={REVISION}"
        entry["assetRevision"] = REVISION
    MANIFEST_JSON.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    previous_js = MANIFEST_JS.read_text(encoding="utf-8")
    prefix = previous_js.split("window.POKEDEX3D_SWITCH_MODELS = ", 1)[0]
    if "window.POKEDEX3D_MODEL_POLICY" not in prefix:
        raise ValueError("Missing switch-only model policy")
    MANIFEST_JS.write_text(
        prefix + "window.POKEDEX3D_SWITCH_MODELS = "
        + json.dumps(entries, separators=(", ", ": "), ensure_ascii=True) + ";\n",
        encoding="utf-8")


def main() -> None:
    results: Counter[str] = Counter()
    fixed = set()
    for dex in RECOVERED_IDS:
        result = fix_one(dex)
        results[result] += 1
        if result == "fixed":
            fixed.add(dex)
            print(f"FIXED #{dex:04d}", flush=True)
    update_manifest(fixed)
    print(f"Verified {len(RECOVERED_IDS)} imported models: "
          f"{results['fixed']} corrected, {results['already upright']} already upright.")
    print("Original geometry, animation, skeletal and image BIN chunks preserved.")


if __name__ == "__main__":
    main()
