#!/usr/bin/env python3
"""Structural regression check for the repaired animated SwSh Caterpie line.

Use after merging model assets or running a new importer. This does not replace
visual review of textures and animation in the browser.
"""
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "web" / "models" / "switch"
EXPECTED_MATERIALS = {
    10: {"BodyVco00", "BodyVco01", "BodySpc"},
    11: {"BodySpc", "Eye"},
    12: set(),
}


def read_glb(path):
    data = path.read_bytes()
    assert len(data) > 32 and data[:4] == b"glTF", path
    assert struct.unpack_from("<I", data, 4)[0] == 2, path
    assert struct.unpack_from("<I", data, 8)[0] == len(data), path
    length, kind = struct.unpack_from("<II", data, 12)
    assert kind == 0x4E4F534A, path
    doc = json.loads(data[20:20 + length])
    binary_offset = 20 + length
    binary_length, binary_type = struct.unpack_from("<II", data, binary_offset)
    assert binary_type == 0x004E4942, path
    assert binary_offset + 8 + binary_length == len(data), path
    return doc, data[binary_offset + 8:]


def verify(dex):
    path = MODELS / f"{dex:04d}" / "regular.glb"
    doc, binary = read_glb(path)
    root = doc["nodes"][doc["scenes"][doc.get("scene", 0)]["nodes"][0]]
    assert root.get("rotation") == [0, 0, 0, 1], (dex, "root orientation")
    assert root.get("scale", [1, 1, 1]) == [1, 1, 1], (dex, "root scale")
    assert doc["meshes"] and doc["skins"], (dex, "mesh or rig missing")
    assert doc["animations"] and all(
        clip.get("channels") and clip.get("samplers")
        for clip in doc["animations"]
    ), (dex, "animation missing")
    assert doc["asset"].get("extras", {}).get("pokedex3dSwshColorRecovery") == 2
    material_by_name = {m["name"]: m for m in doc["materials"]}
    for name in EXPECTED_MATERIALS[dex]:
        material = material_by_name[name]
        slot = material["pbrMetallicRoughness"]["baseColorTexture"]
        texture = doc["textures"][slot["index"]]
        image = doc["images"][texture["source"]]
        view = doc["bufferViews"][image["bufferView"]]
        offset = view.get("byteOffset", 0)
        assert binary[offset:offset + 8] == bytes((137, 80, 78, 71, 13, 10, 26, 10)), (dex, name)
        assert material.get("alphaMode") == "OPAQUE", (dex, name)
    if dex == 11:
        eye = material_by_name["Eye"]["pbrMetallicRoughness"]["baseColorTexture"]
        transform = eye["extensions"]["KHR_texture_transform"]
        assert transform["offset"] == [0, 1], "Metapod's negative-V eye UV offset was lost"
    print(f"#{dex:04d}: model, original rig, animation and repaired albedo verified")


if __name__ == "__main__":
    for dex in (10, 11, 12):
        verify(dex)
