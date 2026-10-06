# Clean model import folder

This directory contains models that have been intentionally imported and validated for Pokedex 3D Max.

Do not manually edit `manifest.js` or `manifest.json`. Use:

```bat
python scripts\import_model.py "PATH_TO_MODEL.glb" --dex 1 --name Bulbasaur --form regular
```

For FBX, DAE, OBJ, or glTF source files, install Blender and run the same command. The importer will call Blender in background mode and export a GLB without deliberately changing the rig, animations, materials, or textures.

Verified animation clips can be recorded during import:

```bat
python scripts\import_model.py "Bulbasaur.glb" --dex 1 --name Bulbasaur --idle "Idle" --idle-break "IdleBreak"
```

Only explicitly verified idle-break clips should be added. Unknown animations are not guessed.
