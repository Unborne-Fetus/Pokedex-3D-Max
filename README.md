# Pokedex 3D Max

An Android-first, modern spiritual successor to the idea of a fully interactive 3D Pokédex.

## Current 3D model support

The app now integrates the community-maintained Pokémon 3D API model catalog and can load its optimized GLB assets directly at runtime.

Current catalog coverage includes 1,300+ models across:

- Regular Pokémon forms
- Shiny variants
- Mega Evolutions
- Gigantamax forms
- Regional forms
- Alternate and special forms

The model library is loaded dynamically rather than committing gigabytes of GLB files into this repository. The viewer uses SceneView + Google Filament and supports touch rotation, zooming, and automatic model animations when animation clips are present.

If the model catalog endpoint is unavailable, the app falls back to regular National Dex model paths so the Pokédex can still attempt to load standard models.

## Vision

Pokedex 3D Max is intended to grow into an all-in-one Pokémon reference app centered around an interactive 3D Pokémon viewer, with complete species/form data, moves, abilities, items, evolutions, cries, collection tracking, and modern Pokédex tools.

## Phase 1

- Android-native app
- Interactive 3D GLB viewer
- 1,300+ model catalog integration
- Touch rotate and zoom
- Automatic model animation
- Search by Pokémon, form, or National Dex number
- Form-aware data model
- Modern Material 3 UI

## Planned

- Complete Pokémon metadata database
- Cry playback
- Shiny/form switching controls
- Animation selector
- Evolution trees
- Move / Ability / Item Dex
- Location data
- Advanced filters
- Favorites and collection tracking
- Offline model caching / downloadable asset packs

## Tech

- Kotlin
- Jetpack Compose
- Material 3
- SceneView
- Google Filament
- GLB / glTF
- Android 8.0+ (API 26)

## Asset note

Pokémon names, designs, imagery, and related assets are property of their respective rights holders. Pokedex 3D Max is an unofficial fan project. The external Pokémon 3D model service is a separate community project and is not part of this repository.
