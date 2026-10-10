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

    def test_blatoise_front_uv_diagnostic(self):
        import json, struct, io, subprocess, sys
        try:
            from PIL import Image
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "-q", "install", "Pillow"])
            from PIL import Image
        raw = (Path(__file__).resolve().parents[1] / "web/models/switch/0009/regular.glb").read_bytes()
        length = struct.unpack_from("<I", raw, 12)[0]
        doc = json.loads(raw[20:20+length])
        start = 28 + length
        images = []
        for im in doc["images"]:
            view = doc["bufferViews"][im["bufferView"]]
            at = start + view.get("byteOffset", 0)
            images.append(Image.open(io.BytesIO(raw[at:at+view["byteLength"]])).convert("RGB"))
        def vals(index,width):
            a=doc["accessors"][index];v=doc["bufferViews"][a["bufferView"]]
            at=start+v.get("byteOffset",0)+a.get("byteOffset",0)
            stride=v.get("byteStride",width*4)
            return [struct.unpack_from("<"+"f"*width,raw,at+j*stride) for j in range(a["count"])]
        def shade(color):
            r,g,b=color
            if b>r*1.08 and b>g*1.02: return "BLUE"
            if r>b*1.16 and g>b*1.12: return "BEIGE"
            if max(color)-min(color)<25 and min(color)>160: return "WHITE"
            if r<145 and g<135 and b<120: return "DARK"
            return "other"
        for i, im in enumerate(images[:2]):
            print("BLASTOISE_COLOR atlas", i, im.size)
            for row in range(4):
                summary=[]
                for col in range(4):
                    from collections import Counter
                    colors=Counter(shade(im.getpixel((min(im.width-1,int((col+dx/8)/4*im.width)),min(im.height-1,int((row+dy/8)/4*im.height))))) for dx in range(8) for dy in range(8))
                    summary.append(dict(colors))
                print("BLASTOISE_COLOR regions",i,row,summary)
        for mesh in doc["meshes"]:
            if "body_mesh" not in mesh.get("name",""): continue
            for prim in mesh["primitives"]:
                mat=doc["materials"][prim["material"]]
                a=prim["attributes"]
                xyz=vals(a["POSITION"],3)
                uv=vals(a["TEXCOORD_0"],2)
                slot=mat["pbrMetallicRoughness"]["baseColorTexture"]
                tex=doc["textures"][slot["index"]]
                im=images[tex["source"]]
                print("BLASTOISE_COLOR BODY",mat["name"],"num",len(xyz))
                for side in ("center","side"):
                    selected=[]
                    for p,t in zip(xyz,uv):
                        x,y,z=p
                        if not (-0.25<y<0.42): continue
                        if side=="center" and not abs(x)<0.18:continue
                        if side=="side" and not 0.23<abs(x)<0.47:continue
                        u=t[0]%1
                        v=(t[1]+(2 if mat["name"].startswith("body_b") else 1))%1
                        pixel=im.getpixel((min(im.width-1,int(u*im.width)),min(im.height-1,int(v*im.height))))
                        selected.append((round(x,3),round(y,3),round(z,3),round(t[0],3),round(t[1],3),shade(pixel),pixel))
                    print("BLASTOISE_COLOR area",mat["name"],side,"total",len(selected))
                    for item in sorted(selected,key=lambda p:p[2])[:25]:
                        print("BLASTOISE_COLOR v",item)

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
