# Remaining regular Switch model recovery (2026-10-09)

The first three recovery batches began with 266 missing National-Dex species
against the 759-entry GitHub regular-model baseline. The user then reported
122 still missing locally. Their exact species list is recorded in
`data/reported-missing-models-2026-10-09.tsv`.

**This report does not mean 144 newly recovered models have been committed or
deployed.** Local model files and GitHub Pages are separate inventories.

## Run the diagnostics

Double-click `diagnose-remaining-models.bat` (or drag one or more original
Switch model/animation/texture archive files or extracted source folders onto
it). The tool reports source archive coverage without modifying current
models. Detailed results are written locally to:

- `.cache/remaining-model-diagnosis/report.tsv`
- `.cache/remaining-model-diagnosis/report.json`

These reports separate a missing regular source model from an available model
that lacks a same-game/same-form idle animation or possible texture sources.
A positive candidate match is **not** proof that the exported GLB is correct;
visual review is still required.

## Re-run the existing three recovery batches

The original three files remain stable and idempotent:

1. `recover-missing-models-001-100.bat`
2. `recover-missing-models-101-200.bat`
3. `recover-missing-models-201-end.bat`

The tool now recognizes locally extracted game-labelled directories (for
example `switch-assets/SV/`, `switch-assets/LA/`, `switch-assets/ZA/`
and `switch-assets/BDSP/`) in addition to original model archives.
For source archives without a game in the filename, put them under the
matching labelled directory, e.g. `switch-assets/SV/Models.zip`, so the
importer knows which game-ID map, rig and animation format to use.

Use source assets you are authorized to extract and process. Do not replace
unavailable models with generic stand-ins, another game's incompatible
animations, static T-poses, or deliberately incomplete textures.

## Areas most likely to need additional source coverage

- **Generation 9 (50 species):** check relevant Scarlet/Violet model,
  animation and texture assets, including expansion content, before treating
  these as a texture-conversion failure.
- **Generation 6 (21 species):** check Scarlet/Violet expansion and
  Legends: Z-A sources. These are not automatically solved by Sword/Shield
  packages alone.
- **Older species:** check the Switch game in which the specific species
  occurs, including BDSP and Legends: Arceus when appropriate.
- **Multi-form species:** Unown, Deoxys, Burmy/Wormadam, Cherrim,
  Shellos/Gastrodon, Rotom, Giratina, Shaymin, Arceus, Basculin,
  Darmanitan, Deerling/Sawsbuck and others may have base/alternate form
  data. Only the genuine regular/default form qualifies for this baseline;
  the diagnostic distinguishes only-other-form candidates.

## Interpretation of diagnostic statuses

- `already_valid_locally`: structural checks passed for existing regular GLB.
- `no_local_switch_sources`: no autodiscovered original model archives/folders.
- `regular_model_not_found_in_sources`: no canonical regular model file in scanned assets.
- `only_other_forms_found`: non-default form models found but no regular one.
- `matching_idle_animation_not_found`: source model exists, but no verified same-game/form idle candidate.
- `texture_source_not_confirmed`: compatible idle appears present, but no candidate texture images/BNTX were located from that game.
- `ready_to_attempt_conversion`: original model + matching idle and potential textures exist; conversion/visual checks still required.

After recovering locally, publish/upload only assets you have the rights to
redistribute. Do not change the Finished Pokémon progress count until models,
texture fidelity, model positioning, and idle animations are visually reviewed.
