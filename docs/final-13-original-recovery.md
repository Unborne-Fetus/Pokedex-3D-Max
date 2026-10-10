# Original Switch recovery: final 13 missing Pokémon

We have **13** user-reported regular species without validated original Switch
models after the previous batch attempts. The
[Pokémon Model Ripping Project](https://archive.vg-resource.com/thread-25872.html)
lists source-game model IDs, not National Pokédex numbers.

The importer now applies the original Scarlet/Violet ID mapping
(`data/sv_model_dex.tsv`, 127 documented entries), in addition to the existing
Sword/Shield model-ID map. For example, `pm1044` is Tadbulb (#938) and
`pm1096` is Iron Bundle (#991). **Never use a model's in-game internal ID as
the National Dex ID without checking the mapping.**

## One-click targeted import on Windows

1. Pull the latest project changes from GitHub.
2. Double-click `recover-final-13.bat`.
3. This launches `setup-all.bat final13`, searches for local source assets,
   and, if necessary, attempts to fetch **only the relevant SV and SwSh
   Gen-8 model/animation/texture packs** from the project's previously
   configured read-only MEGA folder. It never requests the full folder.
4. Only these 13 National Dex numbers are sent to the importer. Previously
   completed Pokémon are preserved.
5. Open `.cache/final-13-recovery/report.tsv` for the exact remaining
   blockers (absent source model, no matching idle, or conversion failure).

If you already have suitable original source ZIP/7z archives or extracted
source folders, place them under `switch-assets` with a game prefix such as
`SV-Poke...` or `SwSh-Poke...`. Alternatively, drag the local original
archives onto `recover-final-13.bat` to skip MEGA entirely. The
`--scan-only` argument to `scripts/recover_final_13.py` checks candidate
coverage without converting files.

**This does not download models from GitHub or rely on placeholders.** The
original-model archive must be reachable or already downloaded, and MEGAcmd,
Python, Blender, and relevant codecs must work. The MEGA download can fail due
to an outdated link, unavailable files, throttling, or network restrictions.
When that happens, the batch preserves previously installed models and
reports the problem instead of claiming success.

All files are processed locally; this workflow does not automatically push
copyrighted game assets to GitHub or declare any new Pokémon Finished. Only
process game assets you are authorized to use.

## Target source files

| National # | Pokémon | Game | Source internal model ID |
|---:|---|---|---|
| 854 | Sinistea | Sword/Shield | pm0972 |
| 864 | Cursola | Sword/Shield | pm0947 |
| 931 | Squawkabilly | Scarlet/Violet | pm1064 |
| 938 | Tadbulb | Scarlet/Violet | pm1044 |
| 939 | Bellibolt | Scarlet/Violet | pm1045 |
| 961 | Wugtrio | Scarlet/Violet | pm1034 |
| 963 | Finizen | Scarlet/Violet | pm1037 |
| 972 | Houndstone | Scarlet/Violet | pm1029 |
| 986 | Brute Bonnet | Scarlet/Violet | pm1083 |
| 988 | Slither Wing | Scarlet/Violet | pm1088 |
| 991 | Iron Bundle | Scarlet/Violet | pm1096 |
| 992 | Iron Hands | Scarlet/Violet | pm1093 |
| 993 | Iron Jugulis | Scarlet/Violet | pm1094 |

## Why these particular packs?

The original forum's 8th and 9th generation ID lists refer to its
game-specific asset filenames. They cannot be compared directly to the
National Dex; the SwSh and SV model-ID maps restore the relationship.

The importer selects a regular model and **same-game/same-form/same-file-format
idle animation**, checks texture completeness, and publishes a converted GLB
only after structural validation. Missing animation files, bad UVs or shaders,
or unrecognized form variants must be repaired from appropriate original
sources, not substituted with an unrelated Pokémon.

**Visual inspection is still required** for body colors, texture layers,
model scale and orientation, and actual idle motion. Structural validation
alone does not establish that the Pokémon looks correct.
