#!/usr/bin/env python3
import argparse
import sys, json, re
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Read original Switch material bindings and palette parameters from extracted assets."
)
parser.add_argument("--sources", type=Path, required=True)
parser.add_argument(
    "--schema-root",
    type=Path,
    required=True,
    help="Pokemon-Switch-Model-Importer-Blender checkout",
)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.schema_root))
from Titan.Model.TRMTR import TRMTR
from GFLib.Model.Model import Model

root = args.sources
records = []


def text(v):
    return v.decode() if isinstance(v, bytes) else str(v or "")


for p in root.rglob("*.trmtr"):
    if "_rare" in p.stem or "_edit" in p.stem:
        continue
    try:
        d = TRMTR.GetRootAs(p.read_bytes())
        mats = {}
        for i in range(d.MaterialsLength()):
            m = d.Materials(i)
            maps = {
                text(m.Textures(j).TextureName()): text(m.Textures(j).TextureFile())
                for j in range(m.TexturesLength())
            }
            base = next(
                (
                    m.Textures(j)
                    for j in range(m.TexturesLength())
                    if m.Textures(j).TextureName() == b"BaseColorMap"
                ),
                None,
            )
            wraps = {}
            if base is not None and base.TextureSlot() < m.SamplersLength():
                sampler = m.Samplers(base.TextureSlot())
                wrap_modes = {0: 10497, 1: 33071, 6: 33648, 7: 33648}
                wraps = {
                    "wrapS": wrap_modes[sampler.RepeatU()],
                    "wrapT": wrap_modes[sampler.RepeatV()],
                }
            alpha_test = any(
                text(m.Shaders(j).ShaderValues(k).StringName()) == "EnableAlphaTest"
                and text(m.Shaders(j).ShaderValues(k).StringValue()).casefold()
                == "true"
                for j in range(m.ShadersLength())
                for k in range(m.Shaders(j).ShaderValuesLength())
            )
            cols = {
                text(m.Float4Parameter(j).ColorName()): [
                    getattr(m.Float4Parameter(j).ColorValue(), k)()
                    for k in ["R", "G", "B", "A"]
                ]
                for j in range(m.Float4ParameterLength())
            }
            floats = {
                text(m.FloatParameter(j).FloatName()): m.FloatParameter(j).FloatValue()
                for j in range(m.FloatParameterLength())
            }
            ints = {
                text(m.IntParameter(j).IntName()): m.IntParameter(j).IntValue()
                for j in range(m.IntParameterLength())
            }
            mats[text(m.Name())] = {
                "maps": maps,
                "colors": cols,
                "floats": floats,
                "ints": ints,
                "alpha": text(m.AlphaType()),
                "alphaTest": alpha_test,
                "sampler": wraps,
            }
        records.append(
            {"path": str(p), "model": p.stem, "kind": "trinity", "materials": mats}
        )
    except Exception as e:
        print("error", p, e)
for p in root.rglob("*.gfbmdl"):
    if "_rare" in p.stem or "_edit" in p.stem:
        continue
    try:
        d = Model.GetRootAsModel(p.read_bytes(), 0)
        mats = {}
        for i in range(d.MaterialsLength()):
            m = d.Materials(i)
            maps = {
                text(m.TextureMaps(j).Sampler()): text(
                    d.TextureNames(m.TextureMaps(j).Index())
                )
                for j in range(m.TextureMapsLength())
            }
            cols = {
                text(m.Colors(j).Name()): [
                    getattr(m.Colors(j).Color(), k)() for k in ["R", "G", "B"]
                ]
                + [1]
                for j in range(m.ColorsLength())
            }
            switches = {
                text(m.Switches(j).Name()): m.Switches(j).Value()
                for j in range(m.SwitchesLength())
            }
            values = {
                text(m.Values(j).Name()): m.Values(j).Value()
                for j in range(m.ValuesLength())
            }
            cols["UVScaleOffset"] = [
                values.get("ColorUVScaleU", 1),
                values.get("ColorUVScaleV", 1),
                values.get("ColorUVTranslateU", 0),
                values.get("ColorUVTranslateV", 0),
            ]
            base = next(
                (
                    m.TextureMaps(j)
                    for j in range(m.TextureMapsLength())
                    if m.TextureMaps(j).Sampler() == b"Col0Tex"
                ),
                None,
            )
            wrap_modes = {0: 10497, 1: 33071, 2: 33648}
            wraps = (
                {}
                if base is None or base.Params() is None
                else {
                    "wrapS": wrap_modes[base.Params().WrapModeX()],
                    "wrapT": wrap_modes[base.Params().WrapModeY()],
                }
            )
            mats[text(m.Name())] = {
                "maps": maps,
                "colors": cols,
                "switches": switches,
                "floats": values,
                "alpha": "SOURCE_IMAGE",
                "sampler": wraps,
            }
        records.append(
            {"path": str(p), "model": p.stem, "kind": "gfb", "materials": mats}
        )
    except Exception as e:
        print("error", p, e)
mapping = {}
for line in (
    (Path(__file__).resolve().parents[1] / "data/swsh_model_dex.tsv")
    .read_text()
    .splitlines()[1:]
):
    a, b, *_ = line.split("\t")
    mapping[int(a)] = int(b)
for r in records:
    match = re.search(r"pm(\d{4})", r["model"])
    r["dex"] = int(match[1]) if match else -1
    if "swsh" in r["path"].casefold():
        r["dex"] = mapping.get(r["dex"], r["dex"])
    r["priority"] = next(
        (
            v
            for k, v in [
                ("ZA-", 600),
                ("SV-", 500),
                ("LA-", 400),
                ("SwSh-", 300),
                ("LGPE-", 200),
            ]
            if k.casefold().rstrip("-") in r["path"].casefold()
        ),
        0,
    )
args.output.write_text(json.dumps(records, indent=2) + "\n")
print("records", len(records))
