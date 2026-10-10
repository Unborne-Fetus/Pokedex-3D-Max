#!/usr/bin/env python3
"""Audit Pokémon-party optimized GLB files without changing Pokedex 3D Max assets.

Reads the user's 122 missing species and checks all available regular/sex-specific
GLB candidates for geometry, embedded base-color images, and animation channels.
Metadata checks do not establish visual correctness or redistribution rights.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data" / "reported-missing-models-2026-10-09.tsv"
OUTPUT = ROOT / ".cache" / "pokemon-party-glb-audit"
BASE_URL = "https://raw.githubusercontent.com/pokemon-party/3d-pokemon/main/models/opt/regular/"
API_URL = "https://api.github.com/repos/pokemon-party/3d-pokemon/contents/models/opt/regular?ref=main"
USER_AGENT = "Pokedex3DMax-CandidateAudit/1.0"
IDLE_PATTERN = re.compile(r"idle|wait|stand|breath|rest|fight[_ -]?a|defaultidle", re.I)
NON_IDLE = re.compile(r"attack|damage|faint|death|down|hit|move|run|walk|jump|bind|t[-_ ]?pose", re.I)


def request(url: str, *, timeout: int = 75) -> bytes:
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                      "Accept": "application/octet-stream"})
            with urllib.request.urlopen(req, timeout=timeout) as reply:
                return reply.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(attempt + 1)
    raise RuntimeError(f"Cannot fetch {url}: {last}")


def reported() -> dict[int, str]:
    pairs = {}
    for row in TARGETS.read_text(encoding="utf-8").splitlines():
        columns = row.split("\t", 1)
        if len(columns) == 2 and columns[0].isdigit():
            pairs[int(columns[0])] = columns[1]
    if len(pairs) != 122:
        raise ValueError(f"Expected 122 missing entries; got {len(pairs)}")
    return pairs


def source_catalog() -> dict[str, dict]:
    rows = json.loads(request(API_URL).decode("utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("Source GitHub directory did not return a file list")
    return {row["name"]: row for row in rows if row.get("type") == "file"
            and row.get("name", "").endswith(".glb")}


def glb_doc(raw: bytes) -> tuple[dict, bytes]:
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise ValueError("Missing GLB glTF magic")
    magic, version, total = struct.unpack_from("<III", raw, 0)
    if version != 2 or total != len(raw):
        raise ValueError(f"Invalid GLB version/length: {version}, {total}, {len(raw)}")
    length, chunk_type = struct.unpack_from("<II", raw, 12)
    if chunk_type != 0x4E4F534A or 20 + length > len(raw):
        raise ValueError("GLB lacks a valid JSON chunk")
    doc = json.loads(raw[20:20 + length].decode("utf-8").rstrip(" \t\r\n\0"))
    offset = 20 + length
    binary = b""
    if offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError("Truncated GLB binary chunk")
        size, kind = struct.unpack_from("<II", raw, offset)
        if kind != 0x004E4942 or offset + 8 + size != len(raw):
            raise ValueError("Invalid GLB binary chunk")
        binary = raw[offset + 8:]
    if not isinstance(doc, dict):
        raise ValueError("GLB JSON is not an object")
    return doc, binary


def embedded_image_ok(doc: dict, binary: bytes, image_index: int) -> bool:
    images = doc.get("images") or []
    if not 0 <= image_index < len(images):
        return False
    entry = images[image_index]
    view_index = entry.get("bufferView")
    if isinstance(view_index, int):
        views = doc.get("bufferViews") or []
        if not 0 <= view_index < len(views):
            return False
        view = views[view_index]
        start = int(view.get("byteOffset", 0))
        end = start + int(view.get("byteLength", 0))
        if not 0 <= start < end <= len(binary):
            return False
        header = binary[start:min(start + 16, end)]
        mime = entry.get("mimeType", "").lower()
        return bool(
            (mime == "image/png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
            or (mime == "image/jpeg" and header.startswith(b"\xff\xd8"))
            or (mime == "image/webp" and header[:4] == b"RIFF" and header[8:12] == b"WEBP")
            or (mime == "image/ktx2" and header.startswith(b"\xabKTX 20\xbb\r\n\x1a\n"))
        )
    uri = entry.get("uri", "")
    return bool(isinstance(uri, str) and uri.startswith("data:image/")
                and ";base64," in uri)


def texture_image_index(doc: dict, idx: int) -> int | None:
    textures = doc.get("textures") or []
    if not 0 <= idx < len(textures):
        return None
    texture = textures[idx]
    extensions = texture.get("extensions") or {}
    for ext in ("EXT_texture_webp", "KHR_texture_basisu"):
        mapping = extensions.get(ext) or {}
        if isinstance(mapping.get("source"), int):
            return mapping["source"]
    return texture.get("source") if isinstance(texture.get("source"), int) else None


def inspect(raw: bytes) -> dict:
    doc, binary = glb_doc(raw)
    scenes = doc.get("scenes") or []
    meshes = doc.get("meshes") or []
    materials = doc.get("materials") or []
    accessors = doc.get("accessors") or []
    used_materials = set()
    primitives = 0
    draco = 0
    for mesh in meshes:
        for primitive in mesh.get("primitives") or []:
            primitives += 1
            if "KHR_draco_mesh_compression" in (primitive.get("extensions") or {}):
                draco += 1
            if isinstance(primitive.get("material"), int):
                used_materials.add(primitive["material"])
    geometry = bool(scenes and primitives and (accessors or draco))
    textured = 0
    invalid_textures = 0
    for idx in used_materials:
        if not 0 <= idx < len(materials):
            invalid_textures += 1
            continue
        mat = materials[idx]
        surface = (mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
        if not isinstance(surface, dict) or not isinstance(surface.get("index"), int):
            continue
        image_idx = texture_image_index(doc, surface["index"])
        if image_idx is not None and embedded_image_ok(doc, binary, image_idx):
            textured += 1
        else:
            invalid_textures += 1
    if not used_materials:
        material_status = "no_materials"
    elif invalid_textures:
        material_status = "invalid_embedded_texture"
    elif textured == len(used_materials):
        material_status = "complete"
    elif textured:
        material_status = "partial"
    else:
        material_status = "no_basecolor_textures"

    clips = []
    invalid_clips = 0
    nodes = doc.get("nodes") or []
    for index, anim in enumerate(doc.get("animations") or []):
        channels = anim.get("channels") or []
        samplers = anim.get("samplers") or []
        valid = 0
        for channel in channels:
            sampler_idx = channel.get("sampler")
            target = channel.get("target") or {}
            if not isinstance(sampler_idx, int) or not 0 <= sampler_idx < len(samplers):
                continue
            sample = samplers[sampler_idx]
            if not all(isinstance(sample.get(k), int) and
                       0 <= sample[k] < len(accessors) for k in ("input", "output")):
                continue
            node_index = target.get("node")
            if node_index is not None and (not isinstance(node_index, int)
                                           or not 0 <= node_index < len(nodes)):
                continue
            if target.get("path") not in ("rotation", "translation", "scale", "weights"):
                continue
            valid += 1
        if valid:
            clips.append(str(anim.get("name") or f"unnamed_{index}"))
        else:
            invalid_clips += 1
    named_idle = [x for x in clips if IDLE_PATTERN.search(x) and not NON_IDLE.search(x)]
    if named_idle:
        animation_status = "named_idle"
    elif clips:
        animation_status = "animated_unverified_idle"
    else:
        animation_status = "no_valid_animations"

    return {
        "bytes": len(raw), "geometry": geometry, "meshes": len(meshes),
        "primitives": primitives, "dracoPrimitives": draco, "materialsUsed": len(used_materials),
        "materialsWithEmbeddedBaseColor": textured,
        "invalidBaseColorImages": invalid_textures,
        "textureStatus": material_status, "animations": len(clips),
        "invalidAnimations": invalid_clips,
        "animationNames": clips[:16], "idleCandidates": named_idle,
        "animationStatus": animation_status,
        "extensionsRequired": doc.get("extensionsRequired") or [],
        "visualReview": "not_performed",
        "redistributionRights": "not_verified",
    }


def check_candidate(file: dict) -> dict:
    entry = {"file": file["name"], "sourceBytes": file.get("size", 0),
             "sourceSha": file.get("sha")}
    try:
        entry.update(inspect(request(BASE_URL + file["name"])))
        entry["error"] = None
    except Exception as exc:
        entry["error"] = f"{type(exc).__name__}: {exc}"
        entry.update({"geometry": False, "textureStatus": "unverified",
                      "animationStatus": "unverified", "animations": 0,
                      "visualReview": "not_performed",
                      "redistributionRights": "not_verified"})
    return entry


def candidate_names(dex: int, catalog: dict[str, dict]) -> list[str]:
    direct = f"{dex}.glb"
    if direct in catalog:
        return [direct]
    return sorted(name for name in catalog if
                  re.fullmatch(rf"{dex}-[MF]\.glb", name, flags=re.I))


def audit() -> dict:
    requested = reported()
    catalog = source_catalog()
    selected = {dex: candidate_names(dex, catalog) for dex in requested}
    all_files = [catalog[name] for names in selected.values() for name in names]
    print(f"Source regular files: {len(catalog)}", flush=True)
    print(f"User missing species: {len(requested)}", flush=True)
    print(f"Species with one or more candidate variants: {sum(bool(v) for v in selected.values())}", flush=True)
    print(f"Candidate GLBs to inspect: {len(all_files)}", flush=True)
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for idx, row in enumerate(executor.map(check_candidate, all_files), 1):
            results[row["file"]] = row
            print(f"[{idx:03d}/{len(all_files)}] {row['file']}: "
                  f"{row.get('animationStatus')} / {row.get('textureStatus')}"
                  + (f" / {row['error']}" if row.get("error") else ""), flush=True)

    species = []
    for dex, name in requested.items():
        files = [results[file] for file in selected[dex]]
        ready = [f for f in files if f.get("geometry")
                 and f.get("textureStatus") == "complete"
                 and f.get("animationStatus") == "named_idle"]
        species.append({
            "dex": dex, "name": name, "candidateCount": len(files),
            "fileNames": selected[dex], "candidates": files,
            "passesStructuralSwitchGate": bool(ready),
            "note": "A structural pass is not visual verification, Nintendo Switch provenance, or permission to redistribute.",
        })
    statuses = Counter()
    for item in species:
        if not item["candidateCount"]:
            statuses["not_in_regular_folder"] += 1
        elif item["passesStructuralSwitchGate"]:
            statuses["structural_candidate_with_named_idle"] += 1
        elif any(f.get("error") for f in item["candidates"]):
            statuses["one_or_more_download_or_parse_failures"] += 1
        elif not any(f.get("geometry") for f in item["candidates"]):
            statuses["invalid_geometry"] += 1
        elif not any(f.get("textureStatus") == "complete" for f in item["candidates"]):
            statuses["texture_incomplete"] += 1
        else:
            statuses["no_recognizable_idle"] += 1
    return {
        "sourceRepository": "https://github.com/pokemon-party/3d-pokemon",
        "sourceDirectory": "models/opt/regular",
        "sourceRepositoryLicense": "MIT for repository software; GLB redistribution rights not established",
        "noFilesCopiedToPokedex": True,
        "totals": {"requestedSpecies": len(species),
                   "speciesWithCandidate": sum(item["candidateCount"] > 0 for item in species),
                   "candidateFilesInspected": len(all_files),
                   "byStatus": dict(sorted(statuses.items()))},
        "pokemon": species,
    }


def write_reports(report: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    headers = ["dex", "name", "file", "bytes", "geometry", "textureStatus",
               "materialsUsed", "materialsWithEmbeddedBaseColor", "animations",
               "animationStatus", "idleCandidates", "dracoPrimitives", "error"]
    lines = ["\t".join(headers)]
    for item in report["pokemon"]:
        for candidate in item["candidates"] or [{"file": "", "error": "no candidate"}]:
            fields = {**candidate, "dex": item["dex"], "name": item["name"]}
            fields["idleCandidates"] = ", ".join(candidate.get("idleCandidates", []))
            lines.append("\t".join(str(fields.get(h, "")).replace("\t", " ") for h in headers))
    (OUTPUT / "report.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = report["totals"]
    markdown = ["# Pokémon-party GLB candidate audit", "",
                f"Requested species: **{summary['requestedSpecies']}**",
                f"Source candidates: **{summary['speciesWithCandidate']} species** "
                f"/ **{summary['candidateFilesInspected']} files**", "",
                "| Status | Species |", "|---|---:|"]
    for status, count in summary["byStatus"].items():
        markdown.append(f"| {status} | {count} |")
    markdown.extend(["", "**No visual inspection or licensing clearance was performed.**",
                     "Source code under MIT does not grant Nintendo/Pokémon model redistribution permission.",
                     "", "## Per-species details", "",
                     "| Dex | Pokémon | Model(s) | Texture check | Animation check |", "|---:|---|---|---|---|"])
    for item in report["pokemon"]:
        files = item["candidates"]
        tex = ", ".join(f.get("textureStatus", "") for f in files) or "missing"
        anim = ", ".join(f.get("animationStatus", "") for f in files) or "missing"
        markdown.append(f"| {item['dex']} | {item['name']} | {', '.join(item['fileNames']) or 'none'} "
                        f"| {tex} | {anim} |")
    (OUTPUT / "summary.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write("\n".join(markdown) + "\n")
    print("\nFINAL SUMMARY: " + json.dumps(summary, sort_keys=True), flush=True)
    print("Full per-file report: " + str(OUTPUT / "report.tsv"), flush=True)


def self_test() -> None:
    assert IDLE_PATTERN.search("Armature|defaultidle01")
    assert not (IDLE_PATTERN.search("attack") and not NON_IDLE.search("attack"))
    assert candidate_names(668, {"668-M.glb": {}, "668-F.glb": {}}) == ["668-F.glb", "668-M.glb"]
    assert candidate_names(650, {"650.glb": {}}) == ["650.glb"]
    assert candidate_names(854, {}) == []
    header = struct.pack("<III", 0x46546C67, 2, 12 + 8 + 4) + struct.pack("<II", 4, 0x4E4F534A)
    doc, data = glb_doc(header + b"{}  ")
    assert doc == {} and data == b""
    print("Auditor self-test passed.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true")
    opts = p.parse_args()
    if opts.self_test:
        self_test()
    else:
        write_reports(audit())
