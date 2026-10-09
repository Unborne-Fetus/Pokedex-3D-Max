#!/usr/bin/env python3
"""Generate the local web index from Switch GLBs already copied into this repo.

This catalogs existing files only; it does not modify geometry, animations,
materials or embedded textures, or invent animation metadata.
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / "web" / "models" / "switch"
files = sorted(folder.glob("[0-9][0-9][0-9][0-9]/regular.glb"))
if not files:
    raise SystemExit("No Switch GLBs copied; refusing to publish an empty manifest.")

entries = []
for file in files:
    dex = int(file.parent.name)
    if 1 <= dex <= 1025 and file.stat().st_size > 32:
        entries.append({
            "dex": dex,
            "form": "regular",
            "url": f"web/models/switch/{dex:04d}/regular.glb",
            "source": "original-switch-local-merge",
            "valid": True,
            "ready": True,
        })
if len(entries) < 700:
    raise SystemExit(f"Only {len(entries)} GLBs found; refusing an incomplete merge.")

web = root / "web" / "models"
(web / "switch-manifest.js").write_text(
    "window.POKEDEX3D_SWITCH_MODELS = " + json.dumps(entries, separators=(",", ":")) + ";\n",
    encoding="utf-8",
)
(web / "switch-manifest.json").write_text(
    json.dumps(entries, indent=2) + "\n", encoding="utf-8"
)
print(f"Indexed {len(entries)} original Switch GLBs for this repo.")
