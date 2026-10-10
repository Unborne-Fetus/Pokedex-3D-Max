"""Exercise material selection without requiring Blender or game archives."""
import ast
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


class MaterialTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).with_name("blender_import_switch_game_model.py").read_text()
        tree = ast.parse(source)
        imports = {alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names}
        self.assertIn("os", imports)
        self.assertIn("re", imports)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_linked_base_color_image")
        context = {"os": os, "re": re}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "materials", "exec"), context)
        self.select = context[function.name]

    def material(self, images):
        class Material(dict):
            use_nodes = True
        material = Material()
        material.node_tree = SimpleNamespace(nodes=[SimpleNamespace(type="TEX_IMAGE", image=image, outputs=[]) for image in images])
        return material

    def test_blastoise_belly_restores_original_uvs(self):
        source = (Path(__file__).resolve().parents[1] /
                  "web/species-texture-repairs.js").read_text()
        block = source.split("if (dex === 9) {", 1)[1].split("      let newBinSize", 1)[0]
        self.assertIn('offsetTextureV(doc, "body_a", 1);', block)
        self.assertIn('offsetTextureV(doc, "body_b_00", 2);', block)
        self.assertIn('offsetTextureV(doc, "body_b_01", 2);', block)
        self.assertNotIn("setTexture(doc,", block)

    def test_directory_names_do_not_reject_albedo(self):
        image = SimpleNamespace(name="pm0025_body_albedo.png", filepath="/download/pokemon/pm0025_body_albedo.png")
        self.assertIs(self.select(self.material([image])), image)

    def test_normal_and_ao_maps_are_skipped(self):
        normal = SimpleNamespace(name="body_normal.png", filepath="")
        ao = SimpleNamespace(name="body_ao.png", filepath="")
        color = SimpleNamespace(name="body_albedo.png", filepath="")
        self.assertIs(self.select(self.material([normal, ao, color])), color)

    def test_missing_material_has_no_image(self):
        self.assertIsNone(self.select(None))

    def test_switch_importer_patch_skips_empty_texture_references(self):
        source = Path(__file__).with_name("import_switch_game_assets.py").read_text()
        self.assertIn("__pokedex3d_missing_texture__", source)
        self.assertNotIn(
            'if not reference:\\n        return os.path.join(filep, reference)',
            source,
        )


if __name__ == "__main__":
    unittest.main()
