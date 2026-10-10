#!/usr/bin/env python3
"""Regression checks for actual Switch species identity, not catalog labels."""
import hashlib
import json
import tempfile
from pathlib import Path

from restore_switch_models import git_blob_hash, glb_internal_id, known_identity

with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "sample.glb"
    path.write_bytes(b"abc")
    expected = hashlib.sha1(b"blob 3\x00abc").hexdigest()
    assert git_blob_hash(path) == expected

def model(internal):
    return {"images": [{"name": f"pm{internal:04d}_00_00_body_alb"}]}

assert glb_internal_id(model(1025)) == 1025
assert known_identity(1025, model(1025), {"sourceGame": "sv"}, {}) == (920, 1025, "sv")
assert known_identity(801, model(801), {"sourceGame": "sv"}, {}) == (747, 801, "sv")
assert known_identity(906, model(1010), {"sourceGame": "sv",
                                         "sourceModelId": 1010}, {}) == (906, 1010, "sv")
assert known_identity(1025, model(1131), {"sourceGame": "sv"}, {}) == (1025, 1131, "sv")
assert known_identity(964, model(964), {"sourceGame": "ZA-PokeDLC"}, {}) == (852, 964, "za")
assert known_identity(965, model(965), {"sourceGame": "ZA-PokeDLC"}, {}) == (853, 965, "za")
assert known_identity(942, model(942), {"sourceGame": "ZA-PokeDLC"}, {}) == (876, 942, "za")
assert known_identity(920, model(920), {"sourceGame": "ZA-PokeDLC"}, {}) == (823, 920, "za")
assert known_identity(801, model(801), {}, {}) is None
assert known_identity(701, model(701), {}, {}) is None
assert glb_internal_id({"images": [{"name": "pm0801_a"}, {"name": "pm0802_b"}]}) is None

original = json.loads((Path(__file__).resolve().parents[1] /
    "data/verified_switch_glb_provenance.json").read_text(encoding="utf-8"))
assert original["format"] == 2
assert len(original["models"]) >= 1500
assert all(len(sha) == 40 and rec["sourceModelId"] > 0
           for sha, rec in original["models"].items())
print("Verified GLB source identity, conservative fallbacks, and Git blob fingerprints")
