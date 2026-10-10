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

    def test_blatoise_front_material_diagnostic(self):
        # Inspection of the exported GLB keeps the binary's geometry untouched.
        import json
        import struct
        path = Path(__file__).resolve().parents[1] / "web/models/switch/0009/regular.glb"
        raw = path.read_bytes()
        length, kind = struct.unpack_from("<II", raw, 12)
        doc = json.loads(raw[20:20 + length])
        start = 28 + length
        def points(index, width):
            acc = doc["accessors"][index]
            if acc["componentType"] != 5126:
                return []
            bv = doc["bufferViews"][acc["bufferView"]]
            off = start + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            stride = bv.get("byteStride", width * 4)
            return [struct.unpack_from("<" + "f" * width, raw, off + j * stride)
                    for j in range(acc["count"])]
        print("BLASTOISE_DIAG animations", len(doc.get("animations", [])))
        for i, image in enumerate(doc.get("images", [])):
            print("BLASTOISE_DIAG image", i, image.get("name"),
                  "view", image.get("bufferView"))
        for i, mat in enumerate(doc["materials"]):
            pbr = mat.get("pbrMetallicRoughness", {})
            slot = pbr.get("baseColorTexture", {})
            t = doc.get("textures", [])[slot["index"]] if "index" in slot else {}
            print("BLASTOISE_DIAG material", i, mat.get("name"),
                  "texture", slot.get("index"), "source", t.get("source"),
                  "texCoord", slot.get("texCoord"),
                  "factor", pbr.get("baseColorFactor"))
        for mesh in doc["meshes"]:
            for k, primitive in enumerate(mesh.get("primitives", [])):
                mid = primitive.get("material", 0)
                name = doc["materials"][mid].get("name")
                attrs = primitive["attributes"]
                xyz = points(attrs["POSITION"], 3) if "POSITION" in attrs else []
                coordslot = doc["materials"][mid].get("pbrMetallicRoughness", {}).get("baseColorTexture", {}).get("texCoord", 0)
                uvkey = "TEXCOORD_" + str(coordslot)
                uv = points(attrs[uvkey], 2) if uvkey in attrs else []
                def bounds(items, n):
                    return [(round(min(v[i] for v in items), 3), round(max(v[i] for v in items), 3)) for i in range(n)] if items else None
                print("BLASTOISE_DIAG primitive", mesh.get("name"), k, name,
                      "vertices", len(xyz), "xyz", bounds(xyz, 3),
                      "uv", bounds(uv, 2))

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
