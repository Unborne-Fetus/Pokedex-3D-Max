from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("import_switch_game_assets.py")
SPEC = importlib.util.spec_from_file_location("switch_importer", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
switch_importer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(switch_importer)


class SwitchImporterLogicTests(unittest.TestCase):
    def make_asset(self, root: Path, name: str) -> Path:
        path = root / name
        path.write_bytes(b"test")
        return path

    def test_form_key_trims_only_trailing_zero_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = self.make_asset(root, "pm0479_16.gfbmdl")
            anim = self.make_asset(root, "pm0479_16_00.gfbanm")
            complex_form = self.make_asset(root, "pm0922_81_02.trmdl")

            self.assertEqual(switch_importer.infer_form_key(model), "16")
            self.assertEqual(switch_importer.infer_form_key(anim), "16")
            self.assertEqual(switch_importer.infer_form_key(complex_form), "81-02")

    def test_swsh_accepts_gfbanm_and_rejects_tranm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = self.make_asset(root, "pm0479_16.gfbmdl")
            good = self.make_asset(root, "pm0479_16_00_defaultwait01.gfbanm")
            wrong_format = self.make_asset(root, "pm0479_16_00_defaultwait01.tranm")

            jobs = switch_importer.scan_models(root, "swsh")
            animations = switch_importer.scan_animations(root, "swsh")
            switch_importer.attach_animations(jobs, animations)

            self.assertEqual(len(jobs), 1)
            selected = jobs[0]["animations"]
            self.assertEqual(len(selected), 1)
            self.assertEqual(Path(selected[0]["source"]).name, good.name)
            self.assertNotEqual(Path(selected[0]["source"]).name, wrong_format.name)

    def test_legends_arceus_uses_tranm_even_with_gfbmdl_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_asset(root, "pm0058_00.gfbmdl")
            tranm = self.make_asset(root, "pm0058_00_defaultwait01.tranm")
            self.make_asset(root, "pm0058_00_defaultwait01.gfbanm")

            jobs = switch_importer.scan_models(root, "la")
            animations = switch_importer.scan_animations(root, "la")
            switch_importer.attach_animations(jobs, animations)

            self.assertEqual(len(jobs), 1)
            selected = jobs[0]["animations"]
            self.assertEqual(len(selected), 1)
            self.assertEqual(Path(selected[0]["source"]).name, tranm.name)

    def test_never_crosses_source_games(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = self.make_asset(root, "pm0479_16.gfbmdl")
            anim = self.make_asset(root, "pm0479_16_00_defaultwait01.gfbanm")

            jobs = switch_importer.scan_models(root, "swsh")
            animations = switch_importer.scan_animations(root, "lgpe")
            switch_importer.attach_animations(jobs, animations)

            self.assertEqual(Path(jobs[0]["source"]).name, model.name)
            self.assertEqual(jobs[0]["animations"], [])
            self.assertEqual(Path(animations[0]["source"]).name, anim.name)

    def test_idle_selector_requires_idle_like_name(self) -> None:
        self.assertEqual(
            switch_importer.choose_idle(["pm0001_defaultwait01_loop"]),
            "pm0001_defaultwait01_loop",
        )
        self.assertIsNone(
            switch_importer.choose_idle(["pm0001_attack01", "pm0001_damage01"])
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
