import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from sync_switch_web import sync_pack


def glb(path, names):
    doc = json.dumps({"asset":{"version":"2.0"}, "animations":[{"name":n} for n in names]}).encode()
    doc += b" " * (-len(doc) % 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<IIIII", 0x46546C67, 2, 20 + len(doc), len(doc), 0x4E4F534A) + doc)


class SyncTests(unittest.TestCase):
    def test_installed_switch_assets_are_available_to_index(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); pack = root / "pack"; repo = root / "repo"
            glb(pack / "switch/0001/regular.glb", ["idle", "wave"])
            glb(pack / "switch/0002/regular.glb", [])
            glb(pack / "generic/0003.glb", ["idle"])
            (pack / "model_catalog.tsv").write_text("dex\tname\tform\tpath\n1\tBulbasaur\tregular\tswitch/0001/regular.glb\n2\tIvysaur\tregular\tswitch/0002/regular.glb\n3\tVenusaur\tregular\tgeneric/0003.glb\n4\tBad\tregular\tswitch/../outside.glb\n")
            (pack / "switch-model-metadata.json").write_text(json.dumps([{"dex":1,"form":"regular","idleAnimation":"idle","idleBreaks":["wave","missing"]}]))
            self.assertEqual(sync_pack(pack, repo), 1)
            entries = json.loads((repo / "web/models/switch-manifest.json").read_text())
            self.assertEqual(entries[0]["idleBreaks"], ["wave"])
            self.assertEqual((repo / entries[0]["url"]).read_bytes(), (pack / "switch/0001/regular.glb").read_bytes())
            self.assertIn('window.POKEDEX3D_SWITCH_MODELS', (repo / "web/models/switch-manifest.js").read_text())
            self.assertEqual(sync_pack(pack, repo), 1)
            glb(pack / "switch/0001/regular.glb", ["wait", "wave"])
            sync_pack(pack, repo)
            self.assertEqual(json.loads((repo / "web/models/switch-manifest.json").read_text())[0]["idleAnimation"], "wait")


    def test_same_size_and_timestamp_different_model_must_be_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); pack = root / "pack"; repo = root / "repo"
            installed = pack / "switch/0001/regular.glb"
            published = repo / "web/models/switch/0001/regular.glb"
            glb(installed, ["idle"])
            glb(published, ["wait"])
            self.assertEqual(installed.stat().st_size, published.stat().st_size)
            os.utime(published, ns=(installed.stat().st_atime_ns, installed.stat().st_mtime_ns))
            self.assertEqual(installed.stat().st_mtime_ns, published.stat().st_mtime_ns)
            (pack / "model_catalog.tsv").write_text(
                "dex\tname\tform\tpath\n1\tBulbasaur\tregular\tswitch/0001/regular.glb\n"
            )
            (pack / "switch-model-metadata.json").write_text(json.dumps([
                {"dex": 1, "form": "regular", "idleAnimation": "idle"}
            ]))
            self.assertEqual(sync_pack(pack, repo), 1)
            self.assertEqual(published.read_bytes(), installed.read_bytes())

    def test_reject_catalog_entry_with_another_pokemons_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); pack = root / "pack"; repo = root / "repo"
            glb(pack / "switch/0002/regular.glb", ["idle"])
            (pack / "model_catalog.tsv").write_text(
                "dex\tname\tform\tpath\n1\tBulbasaur\tregular\tswitch/0002/regular.glb\n"
            )
            self.assertEqual(sync_pack(pack, repo), 0)
            models = json.loads((repo / "web/models/switch-manifest.json").read_text())
            self.assertEqual(models, [])
            self.assertFalse((repo / "web/models/switch/0001/regular.glb").exists())


if __name__ == "__main__":
    unittest.main()
