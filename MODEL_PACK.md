# Remote Switch Model Pack

Pokedex 3D Max can now use a preconverted online Switch-model pack before it falls back to the original downloaded model/animation archives.

## Runtime order

1. The generic offline model pack is prepared first.
2. Setup checks the remote validated Switch model-pack manifest.
3. Only changed/missing model-pack ZIP shards are downloaded.
4. Every shard and GLB is SHA-256 verified.
5. Validated Switch GLBs override the generic fallback models.
6. If the remote manifest, shard, or checksum fails, setup automatically uses the downloaded source archives plus Blender.

The original downloaded Switch archives are never deleted by the remote-pack installer.

## Publish the pack

First run the local Switch importer successfully so that `web/models/switch/` and `web/models/switch-manifest.json` contain validated models.

Then run:

```bat
publish-model-pack.bat
```

The publisher:

- includes only manifest entries marked ready;
- divides the GLBs into 100-Dex ZIP shards;
- computes SHA-256 hashes for every shard and model;
- writes `model-pack-manifest.json`;
- creates or updates the GitHub Release tagged `model-pack-v6`;
- uploads the manifest and shards with `gh release upload --clobber`.

The default release repository is:

```text
Unborne-Fetus/Pokedex-3D-Max
```

## Use a separate asset repository

The publishing target can be changed without editing code:

```bat
set POKEDEX3D_MODEL_PACK_REPO=Unborne-Fetus/Pokedex-3D-Max-Models
publish-model-pack.bat
```

Clients can point at any compatible manifest by setting:

```bat
set POKEDEX3D_MODEL_PACK_MANIFEST=https://example.com/model-pack-manifest.json
setup-all.bat full
```

This also allows moving the pack to S3, Cloudflare R2, Backblaze B2, or another object store later.

## Local backup

Downloaded source archives remain under the existing cache/download locations and are still used by the local importer when the online pack cannot be used.

Do not publish converted or original game assets unless you have permission to distribute them.
