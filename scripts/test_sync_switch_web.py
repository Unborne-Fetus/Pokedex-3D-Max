import json
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


if __name__ == "__main__":
    unittest.main()
