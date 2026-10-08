"""Reactivate regular animated Switch GLBs only when their textures are valid."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
from import_switch_game_assets import parse_glb_doc, choose_idle, glb_textures_complete
from sync_switch_web import ROOT, default_pack, sync_pack


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(text, encoding='utf-8')
    temp.replace(path)


def restore(target: Path, repo: Path = ROOT) -> int:
    target = target.resolve()
    roots = [target / 'switch', repo / 'web/models/switch',
             repo / '.cache/switch-game-assets/original-glbs']
    # Keep source/game/animation metadata for otherwise valid textured exports.
    metadata = {}
    for path in [target / 'switch-model-metadata.json', repo / 'web/models/switch-manifest.json']:
        if path.is_file():
            for entry in json.loads(path.read_text(encoding='utf-8')):
                metadata[(int(entry['dex']), str(entry['form']))] = entry
    names = {}
    for path in [repo / 'data/species_names.tsv', target / 'species_names.tsv', target / 'model_catalog.tsv']:
        if path.is_file():
            for line in path.read_text(encoding='utf-8').splitlines():
                cells = line.split('\t')
                if len(cells) >= 2 and cells[0].isdigit() and not cells[1].startswith('#'):
                    names[int(cells[0])] = cells[1]
    found = {}
    for rank, root in enumerate(roots):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*.glb')):
            if not path.parent.name.isdigit() or path.stem.lower() != 'regular':
                continue
            dex, form = int(path.parent.name), path.stem
            if not 1 <= dex <= 1025:
                continue
            entry = dict(metadata.get((dex, form), {}))
            # Trust the GLB itself, not stale metadata from an earlier failed conversion.
            # Older Switch exports can be correctly animated even when an old manifest
            # marked the same dex/form as animationRejected.
            try:
                doc = parse_glb_doc(path)
                if not isinstance(doc, dict) or not doc.get('meshes') or not doc.get('scenes'):
                    continue
                clips = [a.get('name') or f'animation_{i}' for i, a in enumerate(doc.get('animations', []))
                         if isinstance(a, dict) and a.get('channels') and a.get('samplers')]
                idle = entry.get('idleAnimation') if entry.get('idleAnimation') in clips else choose_idle(clips)
                # Some of the original Switch packs use clip names that our idle-name
                # heuristic does not recognize. If the GLB is genuinely animated,
                # keep it and use the first embedded clip as its default idle rather
                # than discarding the whole model pack.
                if not idle and clips:
                    idle = clips[0]
                if not idle:
                    continue
                if not glb_textures_complete(path):
                    continue
            except (OSError, ValueError, KeyError, TypeError) as error:
                print(f'Skipping damaged Switch GLB {path}: {error}')
                continue
            # Prefer the first valid textured regular Switch export.
            score = (rank,)
            key = (dex, form)
            if key not in found or score < found[key][0]:
                entry.update(dex=dex, name=names.get(dex, entry.get('name', f'#{dex:04d}')), form=form,
                             ready=True, valid=True, idleAnimation=idle, animations=clips,
                             idleBreaks=[n for n in entry.get('idleBreaks', []) if n in clips and n != idle],
                             source='Switch game assets', textureIssues=False)
                found[key] = (score, path, entry)
    if not found:
        print('No usable animated Switch exports remain. Original archives must be converted again; no old-model fallback was activated.')
        return 0
    # Copy originals before syncing the web pack, which may overwrite source paths.
    entries = []
    for key, (_, source, entry) in sorted(found.items()):
        relative = Path('switch') / f'{key[0]:04d}' / f'{key[1]}.glb'
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            temp = destination.with_suffix('.restore.tmp')
            shutil.copy2(source, temp)
            temp.replace(destination)
        # Preserve the export for future texture work and pack changes.
        backup = roots[-1] / f'{key[0]:04d}' / f'{key[1]}.glb'
        backup.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != backup.resolve():
            shutil.copy2(destination, backup)
        entry['path'] = relative.as_posix()
        entries.append(entry)
    # The restored catalog deliberately contains Switch files only.
    atomic_text(target / 'model_catalog.tsv', 'dex\tname\tform\tpath\n' + ''.join(
        f"{e['dex']}\t{e['name']}\t{e['form']}\t{e['path']}\n" for e in entries))
    atomic_text(target / 'switch-model-metadata.json', json.dumps(entries, indent=2) + '\n')
    policy = {'switchOnly': True, 'regularOnly': True, 'allowBrokenTextures': False}
    atomic_text(target / 'model_source_policy.json', json.dumps(policy) + '\n')
    sync_pack(target, repo)
    print(f"Restored {len(entries)} regular animated Switch models with embedded textures.")
    return len(entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=default_pack())
    args = parser.parse_args()
    raise SystemExit(0 if restore(args.target) else 2)
