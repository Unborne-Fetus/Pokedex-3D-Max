import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from repair_switch_glb_textures import (
    compose_layers,
    read_glb,
    repair_material,
    write_repaired_glb,
)


class TextureRepairTests(unittest.TestCase):
    def test_layers_use_linear_colors_and_packed_alpha(self):
        base = Image.fromarray(np.full((1, 1, 4), 255, dtype=np.uint8))
        mask = Image.fromarray(np.array([[[128, 0, 0, 0]]], dtype=np.uint8))
        result = compose_layers(
            base, mask, [[0.25, 0, 0], [1, 1, 1], [1, 1, 1], [1, 1, 1]], [1, 1, 1, 1]
        )
        self.assertEqual(result.tolist(), [[[137, 0, 0]]])

    def test_mask_resize_preserves_rgb_when_alpha_is_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGBA", (1, 1), (255, 255, 255, 255)).save(root / "eye_alb.png")
            Image.new("RGBA", (4, 4), (128, 0, 0, 0)).save(root / "eye_lym.png")
            record = {"path": str(root / "model.trmtr"), "kind": "trinity"}
            material = {
                "maps": {
                    "BaseColorMap": "eye_alb.bntx",
                    "LayerMaskMap": "eye_lym.bntx",
                },
                "colors": {"BaseColorLayer1": [0.25, 0, 0, 1]},
                "floats": {"LayerMaskScale1": 1},
                "alpha": "Opaque",
            }
            png, mode, _ = repair_material(record, material)
            result = Image.open(io.BytesIO(png))
            self.assertEqual(result.size, (4, 4))
            self.assertEqual(result.getpixel((0, 0)), (137, 0, 0, 255))
            self.assertEqual(mode, "OPAQUE")

    def test_repacking_preserves_geometry_and_animation_payloads(self):
        doc = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 12}],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": 4},
                {"buffer": 0, "byteOffset": 4, "byteLength": 4},
                {"buffer": 0, "byteOffset": 8, "byteLength": 4},
            ],
            "accessors": [{"bufferView": 0}, {"bufferView": 2}],
            "images": [{"bufferView": 1}],
            "textures": [{"source": 0}],
            "samplers": [{}],
            "materials": [
                {
                    "name": "body",
                    "pbrMetallicRoughness": {
                        "baseColorTexture": {"index": 0, "texCoord": 1}
                    },
                }
            ],
            "animations": [{"samplers": [{"input": 0, "output": 1}], "channels": []}],
        }
        png = io.BytesIO()
        Image.new("RGBA", (1, 1), "green").save(png, format="PNG")
        source = {"body": {"colors": {"UVScaleOffset": [2, 1, 0, 0]}}}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "model.glb"
            write_repaired_glb(
                doc,
                b"GEOMOLD!ANIM",
                [(png.getvalue(), "OPAQUE", "body")],
                target,
                source,
            )
            result, binary = read_glb(target)
            for accessor, expected in zip(result["accessors"], [b"GEOM", b"ANIM"]):
                view = result["bufferViews"][accessor["bufferView"]]
                self.assertEqual(
                    binary[
                        view["byteOffset"] : view["byteOffset"] + view["byteLength"]
                    ],
                    expected,
                )
            slot = result["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]
            self.assertEqual(slot["texCoord"], 1)
            self.assertEqual(
                slot["extensions"]["KHR_texture_transform"]["scale"], [2, 1]
            )
            self.assertEqual(result["animations"], doc["animations"])


if __name__ == "__main__":
    unittest.main()
