# Pokedex 3D Max

Pokedex 3D Max is currently in a **Switch-model baseline phase**. The project has intentionally been reduced to the smallest useful scope so model conversion, animation playback, and textures can be made reliable before any larger features return.

## Current scope

`main` now contains only the core 3D viewer pipeline:

- Regular Pokémon models from the downloaded Nintendo Switch game asset archives
- Compatible animations from the same Switch game/form
- Embedded GLB animation playback
- Strict texture validation
- Windows native viewer
- Browser viewer
- Android viewer using the same canonical web runtime
- Search, camera controls, auto-rotate, and verified idle animation playback

The current baseline deliberately excludes:

- Mega Evolutions
- Gigantamax forms
- Shiny models
- Other non-regular model forms
- Battle simulator / Brisk battle engine
- PokeMiners model fallbacks
- Pokémon 3D API/CDN model fallbacks
- Generic offline model-pack fallbacks

The removed feature-heavy state is preserved on:

`archive/full-features-before-switch-baseline`

Nothing on that branch needs to be re-created if those systems are wanted later.

## Strict model rules

A model is allowed into the live catalog only when all of the following are true:

1. It is a regular-form Switch model.
2. The converted GLB contains mesh geometry.
3. A compatible Switch animation is embedded and a verified idle can be selected.
4. Every used mesh material has a valid base-color texture binding.
5. The model passes the importer/export validation gates.

Textureless or partially textured GLBs are rejected instead of being shown with white/broken pieces. Static/T-pose replacements are not silently substituted. If a Switch model fails, the viewer reports the failure rather than loading an older model source.

## Setup

From PowerShell:

```powershell
cd "C:\ROM Hacks\Pokedex-3D-Max"
git pull
.\setup-all.bat full
```

### Full

`setup-all.bat full`

- Checks/installs the required tools.
- Finds the original Switch model, animation, and texture archives.
- Reuses only already-valid regular Switch GLBs.
- Reconverts missing, texture-incomplete, or otherwise invalid models.
- Runs importer and desktop preflight checks.
- Builds the Windows MSI/EXE.

### Switch assets only

`setup-all.bat switch`

Use this while working specifically on models, animations, or textures. It skips the Windows app build and installer.

### Original Switch shader texture rebuild

`setup-all.bat textures`

The original Nintendo material uses palette colors and layer-mask shaders that a
plain glTF base-color image cannot represent. This opt-in mode first tests one
shader bake, then reconverts regular Switch models by baking their original color
output to textured GLBs. It keeps each previous valid GLB until the replacement
has passed conversion validation. The process is slower than `switch` mode and
requires the original archives or extracted sources. Once it succeeds, run
`setup-all.bat fast` to update the Windows EXE. Use `launch-index.bat` for the
browser viewer. The texture rebuild is an experimental fidelity improvement,
not a promise of pixel-identical Nintendo game rendering.

### Fast

`setup-all.bat fast`

Revalidates the existing strict Switch pack without doing a full reconversion. If the existing files do not satisfy the baseline rules, setup fails rather than falling back to another model library.

## Browser viewer

Double-click `launch-index.bat` to open the offline index. No EXE, installer,
or terminal command is required once the project files are up to date. The
viewer has a **Repair textures** button; click it, confirm, and leave the
launcher window open while the original shader materials are rebuilt. The
on-screen log displays progress and failures. This is optional and can take a
long time; imported Switch model files are retained until a replacement passes
validation.

Opening `index.html` directly without the launcher can display models already
present, but browser security prevents it from running Blender or repairing
files. The repair button therefore requires the local `launch-index.bat` server.

After the repair finishes successfully, refresh the browser index to load the
new textures. It does not build, install, or require the native Windows EXE.

The browser viewer reads only `web/models/switch-manifest.js`. It has no CDN, PokeMiners, generic-model, or battle-engine fallback path.

## Public GitHub-only website — no billing, no commands

Public model repository: [Pokedex-3D-Models-Animations](https://github.com/Unborne-Fetus/Pokedex-3D-Models-Animations).

The public model repository now contains a complete standalone `index.html`,
`web/` viewer, `.nojekyll` marker, and **756** uploaded regular Switch GLBs
under `0001/regular.glb`-style paths (about 664 MB total). The separate main
Pokédex development repository can remain private.

**One-time GitHub Pages setup:** In the public model repository's GitHub
website open **Settings → Pages → Deploy from a branch → main → / (root) →
Save**. Once GitHub deploys, the expected website address is
`https://unborne-fetus.github.io/Pokedex-3D-Models-Animations/`.
No GitHub Actions workflow, Node build, EXE, PowerShell, or payment method
is needed. GitHub Pages on public Free repositories is subject to size and
bandwidth limits.

The page reads `uploaded-model-inventory.json` and the numbered GLBs from
the same GitHub Pages origin, without private tokens or cross-origin
requests. Selecting a Pokémon downloads its GLB once and checks for
embedded base-color textures and a recognizable idle animation before
the 3D viewer renders it. This structural check **cannot** guarantee
the original game shaders display with correct colors or transparency.

The public site also retains **Open Switch model folder** and **Export model
catalog** options for local GLBs. These work in a standalone browser, without
uploading the selected files. **Repair textures** remains a separate local
Blender conversion feature and cannot run on a static web host.

Original imported sources and the 903-model local baseline aren't
automatically published: only the 756 files actually uploaded to the public
model repository are currently available. For public distribution of
copyrighted Pokémon game assets, confirm redistribution rights.

## Windows model location

The native Windows viewer reads the validated model pack from:

1. `POKEDEX_3D_MAX_MODELS`, when set
2. `%LOCALAPPDATA%\Pokedex3DMax\offline-models`
3. `./offline-models`
4. `%USERPROFILE%\Pokedex3DMax\offline-models`

Even if an older mixed catalog exists in one of those locations, the native viewer accepts only regular models inside its `switch/` tree.

## Development priority

Do not add major Pokédex features back to `main` until the Switch pipeline is dependable across the target species set.

The immediate priorities are:

- Correct Switch model mapping
- Correct same-game/same-form animation mapping
- No bind-pose/T-pose live entries
- Complete base-color texture coverage
- Correct texture/material assignment
- Reliable loading in Windows, browser, and Android viewers

Once those are stable, features can be reintroduced deliberately from the archive branch.

## Tech

- Kotlin / Jetpack Compose
- Compose Desktop
- Filament
- `<model-viewer>` for the canonical browser/Android viewer
- GLB / glTF
- Blender-based Switch asset conversion
- Python conversion/validation tooling

## Asset and trademark note

Pokedex 3D Max is an unofficial fan project. Pokémon names, character designs, game assets, and related intellectual property belong to their respective rights holders.
