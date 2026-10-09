import os
import json
import struct
import tempfile
import unittest
from unittest.mock import patch
import import_switch_game_assets as importer
from pathlib import Path
from restore_switch_models import restore
from import_switch_game_assets import glb_texture_count


def glb(path, textured=False, animation=True):
    doc = {'asset': {'version': '2.0'}, 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
           'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
           'extras': {'padding': 'x' * 1100}}
    if animation:
        doc['animations'] = [{'name': 'defaultwait', 'channels': [{'sampler': 0, 'target': {'node': 0, 'path': 'translation'}}],
                              'samplers': [{'input': 1, 'output': 2}]}]
    if textured:
        doc['textures'] = [{'source': 0}]
        doc['materials'] = [{'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}}]
    chunk = json.dumps(doc).encode()
    chunk += b' ' * (-len(chunk) % 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<IIIII', 0x46546C67, 2, len(chunk) + 20, len(chunk), 0x4E4F534A) + chunk)


class RestoreTests(unittest.TestCase):
    def test_restore_keeps_textured_pack_instead_of_untextured_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); repo = root / 'repo'; pack = root / 'pack'
            original = repo / 'web/models/switch/0006/regular.glb'
            glb(original)
            glb(pack / 'switch/0006/regular.glb', textured=True)
            verified_bytes = (pack / 'switch/0006/regular.glb').read_bytes()
            glb(repo / 'web/models/switch/0007/regular.glb', animation=False)
            (pack / 'model_catalog.tsv').write_text('dex\tname\tform\tpath\n6\tCharizard\tregular\told.glb\n')
            # Stale metadata cannot reject a complete GLB, or admit a broken one.
            (pack / 'switch-model-metadata.json').write_text(json.dumps([
                {'dex': 6, 'form': 'regular', 'ready': False, 'valid': False}]))
            self.assertEqual(restore(pack, repo), 1)
            restored = pack / 'switch/0006/regular.glb'
            self.assertEqual(restored.read_bytes(), verified_bytes)
            self.assertEqual(glb_texture_count(restored), 1)
            self.assertNotIn('old.glb', (pack / 'model_catalog.tsv').read_text())
            self.assertTrue(json.loads((pack / 'model_source_policy.json').read_text())['switchOnly'])
            manifest = (repo / 'web/models/switch-manifest.js').read_text()
            self.assertIn('window.POKEDEX3D_MODEL_POLICY', manifest)
            metadata = json.loads((pack / 'switch-model-metadata.json').read_text())[0]
            self.assertTrue(metadata['ready'])
            self.assertFalse(metadata['textureIssues'])
            # Later restoration must continue preferring a complete textured export.
            glb(restored, textured=True)
            glb(original, textured=True)
            self.assertEqual(restore(pack, repo), 1)
            self.assertEqual(restored.read_bytes(), verified_bytes)

    def test_importer_reconverts_untextured_exports_even_with_legacy_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            glb(root / '0006/regular.glb')
            job = {'dex': 6, 'form': 'regular', 'animations': [{'name': 'defaultwait'}]}
            with patch.object(importer, 'WEB_ROOT', root), \
                 patch.object(importer, 'CACHE', root / 'cache'), \
                 patch.object(importer, 'load_conversion_cache', return_value={}), \
                 patch.object(importer, 'save_conversion_cache'), \
                 patch.object(importer, 'job_fingerprint', return_value='unchanged'), \
                 patch.dict(os.environ, {'POKEDEX3D_ALLOW_BROKEN_TEXTURES': '1'}), \
                 patch.object(importer.subprocess, 'run', side_effect=RuntimeError('Reconversion requested')):
                with self.assertRaisesRegex(RuntimeError, 'Reconversion requested'):
                    importer.run_blender([job], 'unused', root, root)
                glb(root / '0006/regular.glb', textured=True)
                # The same call reuses a complete textured result without Blender.
                importer.run_blender([job], 'unused', root, root)
            self.assertEqual(glb_texture_count(root / '0006/regular.glb'), 1)

    def test_no_originals_does_not_claim_success_or_replace_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); pack = root / 'pack'; repo = root / 'repo'
            pack.mkdir()
            catalog = pack / 'model_catalog.tsv'
            catalog.write_text('old catalog')
            self.assertEqual(restore(pack, repo), 0)
            self.assertEqual(catalog.read_text(), 'old catalog')
            self.assertFalse((pack / 'model_source_policy.json').exists())


if __name__ == '__main__':
    unittest.main()
