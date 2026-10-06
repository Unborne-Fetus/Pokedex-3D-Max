# Pokedex 3D Max

A modern, unofficial 3D Pokédex for Android and Windows.

## Current platform support

### Android
- Jetpack Compose
- SceneView + Google Filament
- Interactive GLB viewer
- Drag to rotate
- Pinch to zoom
- Automatic model animation where clips are present
- Online model catalog fallback
- Automatic preference for an installed offline model pack

### Windows
- Compose Desktop
- SceneView Compose + Filament desktop renderer
- Native Windows `.exe` and `.msi` builds
- Offline model-pack support
- Search by Pokémon, form, or National Dex number
- Mouse orbit / zoom through the SceneView desktop viewer

The Windows renderer requires JDK 22 at build time. The packaged Windows app includes its runtime, so end users do not need to install Java separately.

## 3D model library

Pokedex 3D Max integrates the community-maintained Pokémon 3D API asset library.

Current upstream coverage is 1,300+ optimized GLB models, including:

- Regular forms
- Shiny variants
- Mega Evolutions
- Gigantamax forms
- Regional forms
- Alternate and special forms

The upstream asset repository uses optimized Draco-compressed GLBs and WebP textures.

## Offline model pack

The full model library is intentionally **not committed directly into Git history** because it is roughly 1.4–1.5 GB and would make normal clones unnecessarily huge.

Instead, the repository contains:

`scripts/download_models.py`

This downloads every currently available model from the upstream catalog, mirrors the model structure locally, and generates:

- `model_catalog.tsv`
- `pack_info.json`
- `ASSET_SOURCE.txt`
- upstream license information
- all successfully downloaded GLB files

Run locally:

```bash
python scripts/download_models.py --target offline-models
```

GitHub Actions also contains **Offline Model Pack**, which produces a downloadable artifact named:

`Pokedex-3D-Max-Offline-Models`

That workflow is configured to run when the model-pack script/workflow itself changes and can also be run manually.

### Windows model-pack locations

The Windows app looks in this order:

1. Folder specified by `POKEDEX_3D_MAX_MODELS`
2. `./offline-models`
3. `%LOCALAPPDATA%\Pokedex3DMax\offline-models`
4. `%USERPROFILE%\Pokedex3DMax\offline-models`

### Android model-pack locations

Android automatically checks:

- internal app files: `files/offline-models`
- app-specific external files: `Android/data/com.unbornefetus.pokedex3dmax/files/offline-models`

When the pack is present, the app uses local `file://` GLBs and does not need Wi-Fi for those models. If no local pack is found, it falls back to the online catalog.

A friendlier in-app model-pack importer is planned so users will not need to manually place files.

## Builds

### Android

GitHub Actions workflow: **Android**

Output artifact:

`Pokedex-3D-Max-Android-debug`

### Windows

GitHub Actions workflow: **Windows**

Outputs:

- Windows `.exe`
- Windows `.msi`

Artifact:

`Pokedex-3D-Max-Windows`

## Project direction

Pokedex 3D Max is intended to become an all-in-one modern Pokédex centered around the 3D Pokémon viewer.

Planned major systems include:

- Complete Pokémon metadata
- Form and shiny switching
- Animation selection
- Cry playback
- Evolution trees
- Move Dex
- Ability Dex
- Item Dex
- Location data
- Advanced search/filtering
- Favorites and collection tracking
- Offline-first data
- Download/install model-pack UI
- Better lighting/background controls
- Size comparison
- Full Pokédex 3D Pro-style navigation and presentation

## Tech

- Kotlin 2.4.20
- Jetpack Compose
- Compose Multiplatform / Compose Desktop
- Material 3
- SceneView 4.52
- Google Filament
- GLB / glTF
- Android API 26+
- Windows desktop target

## Asset and trademark note

The upstream Pokémon 3D asset service is a separate community project and is not maintained by this repository. Its repository is distributed under its stated open-source license.

Pokémon names, character designs, and related intellectual property belong to their respective rights holders. Pokedex 3D Max is an unofficial fan project.


## PokeMiners bulk import

Pokedex 3D Max can generate a cleaner local model pack from the public
`PokeMiners/pogo_assets` repository.

Run:

```bat
import-pokeminers.bat
```

The importer uses a sparse Git checkout for `3D Assets/Pokemon`, discovers
`pm####_##_Rig` folders, converts each FBX to GLB with Blender, and generates
`web/models/pokeminers-manifest.js`.

Generated assets are kept out of Git history and automatically override the older
remote model source when present. Re-running the importer resumes from existing
converted files.

You can test a smaller range first:

```bat
python scripts\import_pokeminers.py --start-dex 1 --end-dex 20
```

or a fixed count:

```bat
python scripts\import_pokeminers.py --limit 10
```

Nonzero Pokemon GO form codes are preserved as `go-form-XX` until they are
mapped to human-readable form names.
