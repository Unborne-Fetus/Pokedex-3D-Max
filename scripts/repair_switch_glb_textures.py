#!/usr/bin/env python3
"""Repair exported Switch materials without re-exporting rigs or animations.

Requires decoded original PNGs and material records from the corresponding
TRMTR/GFBMDL files. No species-color guesses or replacement model assets.
"""

import argparse
import hashlib
import io
import json
import re
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image


def read_glb(path):
    data = Path(path).read_bytes()
    magic, version, size = struct.unpack_from("<III", data)
    if magic != 0x46546C67 or version != 2 or size != len(data):
        raise ValueError(f"Invalid GLB: {path}")
    length, kind = struct.unpack_from("<II", data, 12)
    if kind != 0x4E4F534A:
        raise ValueError("GLB must start with JSON")
    doc = json.loads(data[20 : 20 + length])
    offset = 20 + length
    bin_length, kind = struct.unpack_from("<II", data, offset)
    if kind != 0x004E4942:
        raise ValueError("Missing GLB binary chunk")
    return doc, data[offset + 8 : offset + 8 + bin_length]


def image_bytes(doc, binary, index):
    view = doc["bufferViews"][doc["images"][index]["bufferView"]]
    start = view.get("byteOffset", 0)
    return binary[start : start + view["byteLength"]]


@lru_cache(maxsize=128)
def load_image(path):
    with Image.open(path) as image:
        return image.convert("RGBA").copy()


def pixel_hash(image):
    return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


def source_image(record, reference):
    # References are scoped to their model directory; never search another
    # Pokémon or game for a vaguely similar name.
    name = Path(reference.replace("\\", "/")).with_suffix(".png").name
    directory = Path(record["path"]).parent
    for root in (directory, directory.parent / "tex", directory.parent / "textures"):
        path = root / name
        if path.is_file():
            return path
    return None


def albedo_reference(record, material):
    return material["maps"].get(
        "BaseColorMap" if record["kind"] == "trinity" else "Col0Tex", ""
    )


def choose_record(doc, binary, records, dex):
    names = {m["name"] for m in doc["materials"]}
    embedded = {}
    for image_index, image in enumerate(doc["images"]):
        embedded[image.get("name", "").casefold()] = pixel_hash(
            Image.open(io.BytesIO(image_bytes(doc, binary, image_index)))
        )
    candidates = []
    model_names = {
        match.group(0)
        for name in embedded
        if (match := re.match(r"pm\d{4}(?:_\d{2}){1,2}", name))
    }
    for record in records:
        # The record builder records National Dex for remapped SwSh IDs.
        if record["dex"] != dex or not names.issubset(record["materials"]):
            continue
        if record["kind"] == "trinity" and record["model"] not in model_names:
            continue
        matches = 0
        valid = True
        for name in names:
            material = record["materials"][name]
            reference = albedo_reference(record, material)
            path = source_image(record, reference) if reference else None
            if path is None:
                valid = False
                break
            stem = Path(reference).stem.casefold()
            if stem in embedded and pixel_hash(load_image(str(path))) == embedded[stem]:
                matches += 1
        # Some broken GFB exports contain only Default_lta. The complete
        # original material-name set plus remapped model ID identifies these
        # even though there is no surviving albedo hash to compare.
        if valid and (matches or record["kind"] == "gfb"):
            candidates.append((matches, record.get("priority", 0), record))
    if not candidates:
        raise ValueError(
            "No original material set matches the embedded source textures"
        )
    candidates.sort(key=lambda item: item[:2], reverse=True)
    best_score = candidates[0][:2]
    best = [
        record
        for score, priority, record in candidates
        if (score, priority) == best_score
    ]
    # Duplicate exports in DLC/base archives are common, but conflicting
    # material settings with equally strong provenance must not be guessed.
    fingerprints = {json.dumps(r["materials"], sort_keys=True) for r in best}
    if len(fingerprints) > 1:
        raise ValueError("Ambiguous original material settings")
    return best[0]


def srgb_to_linear(value):
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(value):
    value = np.clip(value, 0, 1)
    return np.where(
        value <= 0.0031308, value * 12.92, 1.055 * value ** (1 / 2.4) - 0.055
    )


def compose_layers(albedo, mask, colors, scales, base_color=(1, 1, 1)):
    """Evaluate the original ColorProcess/LayeredMaskScaling in linear RGB.

    Each mask channel is doubled, scaled, and clamped, then mixes the
    unmodified albedo times its layer color into the previous layer result.
    Mask channels are data, not sRGB colors or material opacity.
    """
    source = srgb_to_linear(np.asarray(albedo, dtype=np.float32)[..., :3] / 255)
    source = source * np.asarray(base_color[:3], dtype=np.float32)
    result = source.copy()
    if mask is not None:
        values = np.asarray(mask, dtype=np.float32) / 255
        for channel in range(4):
            weight = np.clip(
                values[..., channel : channel + 1] * 2 * scales[channel], 0, 1
            )
            tinted = source * np.asarray(colors[channel][:3], dtype=np.float32)
            result = result * (1 - weight) + tinted * weight
    return np.rint(linear_to_srgb(result) * 255).astype(np.uint8)


def repair_material(record, material):
    reference = albedo_reference(record, material)
    path = source_image(record, reference)
    if path is None:
        raise ValueError(f"Missing original albedo: {reference}")
    original = load_image(str(path))
    output = np.asarray(original).copy()
    colors = material.get("colors", {})
    if record["kind"] == "trinity":
        mask_reference = material["maps"].get("LayerMaskMap")
        mask = None
        if mask_reference:
            mask_path = source_image(record, mask_reference)
            if mask_path is None:
                raise ValueError(f"Missing original layer mask: {mask_reference}")
            mask = load_image(str(mask_path))
            # Packed alpha is another layer weight. PIL's normal RGBA resize
            # premultiplies RGB by alpha, destroying masks in alpha-zero areas.
            size = (max(original.width, mask.width), max(original.height, mask.height))
            if original.size != size:
                original = Image.merge(
                    "RGBA",
                    [
                        channel.resize(size, Image.Resampling.BILINEAR)
                        for channel in original.split()
                    ],
                )
                output = np.asarray(original).copy()
            if mask.size != original.size:
                mask = Image.merge(
                    "RGBA",
                    [
                        channel.resize(original.size, Image.Resampling.BILINEAR)
                        for channel in mask.split()
                    ],
                )
        output[..., :3] = compose_layers(
            original,
            mask,
            [colors.get(f"BaseColorLayer{i}", [1, 1, 1, 1]) for i in range(1, 5)],
            [
                material.get("floats", {}).get(f"LayerMaskScale{i}", 0)
                for i in range(1, 5)
            ],
            colors.get("BaseColor", [1, 1, 1, 1]),
        )
        source_alpha = material["alpha"].casefold()
        if material.get("alphaTest"):
            mode = "MASK"
        elif "opaque" in source_alpha:
            mode = "OPAQUE"
            output[..., 3] = 255
        elif any(token in source_alpha for token in ("mask", "test", "cutout")):
            mode = "MASK"
        elif "blend" in source_alpha or source_alpha == "add":
            mode = "BLEND"
        else:
            raise ValueError(f"Unknown original alpha policy: {source_alpha}")
    else:
        # GFBMDL Col0Tex is an explicit zero-based binding. Lookup tables,
        # neighboring texture indexes and reflection maps are never albedo.
        output[..., :3] = compose_layers(
            original, None, [], [], colors.get("ConstantColor0", [1, 1, 1])
        )
        alpha = output[..., 3]
        mode = (
            "OPAQUE"
            if np.min(alpha) >= 254
            else "MASK" if np.all((alpha <= 1) | (alpha >= 254)) else "BLEND"
        )
    target = io.BytesIO()
    Image.fromarray(output).save(target, format="PNG", optimize=True)
    return target.getvalue(), mode, path.name


def write_repaired_glb(doc, binary, replacements, destination, source_materials=None):
    # Repack only image buffer views. Every geometry, skin and animation
    # buffer view is copied byte-for-byte, then its index is remapped.
    image_views = {image["bufferView"] for image in doc["images"]}
    views, payloads, remap = [], [], {}
    for index, view in enumerate(doc["bufferViews"]):
        if index in image_views:
            continue
        remap[index] = len(views)
        start = view.get("byteOffset", 0)
        payloads.append(binary[start : start + view["byteLength"]])
        views.append(dict(view))

    def remap_views(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "bufferView":
                    value[key] = remap[item]
                else:
                    remap_views(item)
        elif isinstance(value, list):
            for item in value:
                remap_views(item)

    doc["images"] = []
    doc["textures"] = []
    doc.pop("bufferViews")
    remap_views(doc)
    used = {}
    for material, (png, alpha_mode, name) in zip(doc["materials"], replacements):
        digest = hashlib.sha256(png).hexdigest()
        if digest not in used:
            image_index = len(doc["images"])
            doc["images"].append(
                {"bufferView": len(views), "mimeType": "image/png", "name": name}
            )
            views.append({"buffer": 0, "byteLength": len(png)})
            payloads.append(png)
            used[digest] = image_index
        texture_index = len(doc["textures"])
        texture = {"source": used[digest]}
        if doc.get("samplers"):
            texture["sampler"] = 0
        if source_materials is not None:
            settings = source_materials[material["name"]].get("sampler", {})
            if settings:
                sampler = {"magFilter": 9729, "minFilter": 9987, **settings}
                samplers = doc.setdefault("samplers", [])
                if sampler not in samplers:
                    samplers.append(sampler)
                texture["sampler"] = samplers.index(sampler)
        doc["textures"].append(texture)
        slot = material["pbrMetallicRoughness"]["baseColorTexture"]
        slot["index"] = texture_index
        if source_materials is not None:
            transform = (
                source_materials[material["name"]]
                .get("colors", {})
                .get("UVScaleOffset", [1, 1, 0, 0])
            )
            if not np.allclose(transform, [1, 1, 0, 0], atol=1e-7):
                # glTF V runs downward; source UV offsets run upward.
                extension = {
                    "scale": transform[:2],
                    "offset": [transform[2], 1 - transform[1] - transform[3]],
                }
                slot.setdefault("extensions", {})["KHR_texture_transform"] = extension
                extensions = doc.setdefault("extensionsUsed", [])
                if "KHR_texture_transform" not in extensions:
                    extensions.append("KHR_texture_transform")
        material["pbrMetallicRoughness"]["baseColorFactor"] = [1, 1, 1, 1]
        material["alphaMode"] = alpha_mode
        if alpha_mode == "MASK":
            material["alphaCutoff"] = 0.5
        else:
            material.pop("alphaCutoff", None)
        material.setdefault("extras", {})["switchTextureRepair"] = 1
    packed = bytearray()
    for view, payload in zip(views, payloads):
        packed.extend(b"\0" * (-len(packed) % 4))
        view["byteOffset"] = len(packed)
        view["byteLength"] = len(payload)
        packed.extend(payload)
    doc["bufferViews"] = views
    doc["buffers"] = [{"byteLength": len(packed)}]
    packed.extend(b"\0" * (-len(packed) % 4))
    metadata = json.dumps(doc, separators=(",", ":")).encode()
    metadata += b" " * (-len(metadata) % 4)
    result = struct.pack("<III", 0x46546C67, 2, 28 + len(metadata) + len(packed))
    result += struct.pack("<II", len(metadata), 0x4E4F534A) + metadata
    result += struct.pack("<II", len(packed), 0x004E4942) + packed
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Path(destination).write_bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.records.read_text())
    report = {"repaired": [], "failed": []}
    by_dex = {}
    for record in records:
        by_dex.setdefault(record["dex"], []).append(record)

    def repair(path):
        dex = int(path.parent.name)
        try:
            doc, binary = read_glb(path)
            record = choose_record(doc, binary, by_dex.get(dex, []), dex)
            replacements = [
                repair_material(record, record["materials"][m["name"]])
                for m in doc["materials"]
            ]
            write_repaired_glb(
                doc,
                binary,
                replacements,
                args.output / path.parent.name / path.name,
                record["materials"],
            )
            game = next(
                (
                    part
                    for part in Path(record["path"]).parts
                    if part.startswith(("ZA-", "SV-", "LA-", "SwSh-", "LGPE-"))
                ),
                "unknown",
            )
            return "repaired", {
                "dex": dex,
                "source": Path(record["path"]).name,
                "game": game,
                "materials": len(replacements),
            }
        except Exception as error:
            return "failed", {"dex": dex, "error": str(error)}

    with ThreadPoolExecutor(max_workers=4) as executor:
        pending = [
            executor.submit(repair, path)
            for path in sorted(args.input.glob("*/regular.glb"))
        ]
        for future in as_completed(pending):
            kind, result = future.result()
            report[kind].append(result)
            if kind == "failed":
                print(result["dex"], result["error"], flush=True)
            if (len(report["repaired"]) + len(report["failed"])) % 50 == 0:
                print(
                    f"Repaired {len(report['repaired'])}; failed {len(report['failed'])}",
                    flush=True,
                )
    for values in report.values():
        values.sort(key=lambda value: value["dex"])
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Repaired {len(report['repaired'])}; failed {len(report['failed'])}")


if __name__ == "__main__":
    main()
