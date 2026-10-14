#!/usr/bin/env python3
"""Regression tests for GFPAK -> Pokédex 3D Max ZIP interchange."""
from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import import_gfpak_zip as bridge


def minimal_glb(idle: bool = True, textured: bool = True, model_id: int = 942) -> bytes:
    # Compact structural GLB fixture; validates archive routing and manifest
    # invariants, not pixel rendering in a GPU driver.
    materials = [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}] if textured else [{}]
    name = f"pm{model_id:04d}_body"
    doc = {
        "asset": {"version": "2.0"},
        "scenes": [{"nodes": [0]}], "scene": 0,
        "nodes": [{"name": name, "mesh": 0}],
        "meshes": [{"name": name, "primitives": [
            {"attributes": {"POSITION": 0}, "material": 0}
        ]}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
        "bufferViews": [{"buffer": 0, "byteLength": 36},
                        {"buffer": 0, "byteOffset": 36, "byteLength": 1280}],
        "buffers": [{"byteLength": 1316}],
        "materials": materials,
        "textures": [{"source": 0}],
        "images": [{"bufferView": 1, "mimeType": "image/png"}],
        "animations": ([{"name": "battle_idle", "channels": [{"sampler": 0,
                           "target": {"node": 0, "path": "rotation"}}],
                         "samplers": [{"input": 0, "output": 0}]}] if idle else []),
    }
    payload = json.dumps(doc).encode()
    payload += b" " * ((-len(payload)) % 4)
    binary = bytes(1316)
    binary += b"\x00" * ((-len(binary)) % 4)
    total = 12 + 8 + len(payload) + 8 + len(binary)
    return (struct.pack("<III", 0x46546c67, 2, total)
            + struct.pack("<II", len(payload), 0x4e4f534a) + payload
            + struct.pack("<II", len(binary), 0x004e4942) + binary)


def make_zip(path: Path, *, glb: bytes | None = None, game="za", model_id: int = 942) -> None:
    metadata = {
        "format": "gfpak-pokemon-export",
        "version": 1,
        "sourceGame": game,
        "selectedModel": f"pm{model_id:04d}_00_00.trmdl",
        "convertedModel": bridge.EXPORT_GLb if glb else None,
        "conversion": "glb-included" if glb else "original-assets-only",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(bridge.EXPORT_MANIFEST, json.dumps(metadata))
        archive.writestr(f"pm{model_id:04d}_00_00.trmdl", b"native game data")
        if glb is not None:
            archive.writestr(bridge.EXPORT_GLb, glb)


class GfpakZipTests(unittest.TestCase):
    def test_correct_internal_id_mapping(self):
        metadata = {"selectedModel": "pm0942_00_00.trmdl", "sourceGame": "za"}
        dex, model_id, game = bridge.resolve_identity(metadata, None, None)
        self.assertEqual((dex, model_id, game), (876, 942, "za"))
        with self.assertRaisesRegex(ValueError, "conflicts"):
            bridge.resolve_identity(metadata, None, 942)

    def test_egg_can_only_target_victini_explicitly(self):
        metadata = {"selectedModel": "pm0000_resource_0009.gfbmdl", "sourceGame": "swsh"}
        with self.assertRaisesRegex(ValueError, "Pokémon Egg"):
            bridge.resolve_identity(metadata, None, None)
        with self.assertRaisesRegex(ValueError, "Pokémon Egg"):
            bridge.resolve_identity(metadata, None, 493)
        self.assertEqual(bridge.resolve_identity(metadata, None, 494), (494, 0, "swsh"))
        with self.assertRaisesRegex(ValueError, "Pokémon Egg"):
            bridge.resolve_identity({**metadata, "sourceGame": "sv"}, None, 494)

    def test_egg_import_into_victini_keeps_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            archive = folder / "pm0000.zip"
            make_zip(archive, glb=minimal_glb(model_id=0), game="swsh", model_id=0)
            captured = []
            with patch.object(bridge, "WEB_ROOT", folder / "switch"), \
                 patch.object(bridge, "load_existing_manifest", return_value=[]), \
                 patch.object(bridge, "write_manifest", side_effect=captured.append):
                result = bridge.import_archive(archive, dex_override=494, desktop=False)
            self.assertEqual((result["dex"], result["modelId"]), (494, 0))
            self.assertTrue((folder / "switch" / "0494" / "regular.glb").is_file())
            self.assertTrue(captured[0][0]["eggPlaceholder"])
            self.assertEqual(captured[0][0]["modelId"], 0)

    def test_egg_rejects_different_embedded_species(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            archive = folder / "pm0000.zip"
            make_zip(archive, glb=minimal_glb(model_id=494), game="swsh", model_id=0)
            with patch.object(bridge, "WEB_ROOT", folder / "switch"), \
                 patch.object(bridge, "load_existing_manifest", return_value=[]):
                with self.assertRaisesRegex(ValueError, "original pm0000 geometry"):
                    bridge.import_archive(archive, dex_override=494, desktop=False)

    def test_requires_game_identity(self):
        with self.assertRaisesRegex(ValueError, "Unknown source game"):
            bridge.resolve_identity(
                {"selectedModel": "pm0942_00_00.trmdl", "sourceGame": "auto"}, None, None
            )

    def test_raw_only_reports_missing_converted_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pm0942.zip"
            make_zip(path)
            with self.assertRaisesRegex(ValueError, "original assets"):
                bridge.import_archive(path, desktop=False)

    def test_converted_model_imports_without_blender_and_preserves_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "pm0942.zip"
            make_zip(path, glb=minimal_glb())
            catalog = [{"dex": 25, "form": "regular", "ready": True}]
            captured = []
            with patch.object(bridge, "WEB_ROOT", folder / "switch"), \
                 patch.object(bridge, "load_existing_manifest", return_value=catalog), \
                 patch.object(bridge, "write_manifest", side_effect=captured.append):
                result = bridge.import_archive(path, desktop=False)
            self.assertEqual(result["dex"], 876)
            self.assertEqual(result["idle"], "battle_idle")
            self.assertTrue((folder / "switch" / "0876" / "regular.glb").is_file())
            self.assertEqual({int(entry["dex"]) for entry in captured[0]}, {25, 876})

    def test_bad_textures_do_not_overwrite_installed_model(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "pm0942.zip"
            make_zip(path, glb=minimal_glb(textured=False))
            target = folder / "switch" / "0876" / "regular.glb"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"existing verified model")
            with patch.object(bridge, "WEB_ROOT", folder / "switch"), \
                 patch.object(bridge, "load_existing_manifest", return_value=[]):
                with self.assertRaisesRegex(ValueError, "base-color"):
                    bridge.import_archive(path, desktop=False)
            self.assertEqual(target.read_bytes(), b"existing verified model")

    def test_missing_idle_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "pm0942.zip"
            make_zip(path, glb=minimal_glb(idle=False))
            with patch.object(bridge, "WEB_ROOT", folder / "switch"), \
                 patch.object(bridge, "load_existing_manifest", return_value=[]):
                with self.assertRaisesRegex(ValueError, "no verified idle"):
                    bridge.import_archive(path, desktop=False)


if __name__ == "__main__":
    unittest.main()
