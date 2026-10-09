# Switch model catalog for the web index

The public `index.html` is a static website. Its default
`switch-manifest.js` / `switch-manifest.json` are empty until a
validated model collection is specifically made available.

## Browser-only use

Select **Open Switch model folder** in the website, then select the
`offline-models` or `web/models` folder already containing original
converted Switch GLBs in `switch/####/regular.glb` paths.

The browser reads and validates those GLBs locally; it does **not**
upload them or require Python, PowerShell, or `launch-index.bat`.
The optional `switch-model-metadata.json` or `switch-manifest.json`
supplies verified idle clip names.

## Site hosting

The repository intentionally ignores `web/models/switch/`; the original
downloaded game archives and generated GLBs are not automatically
committed or publicly deployed. Site operators can host suitably licensed
converted GLBs at the paths listed in a generated `switch-manifest.js`.
The existing `scripts/sync_switch_web.py` creates this manifest and
copies the active local Switch files, but GitHub Pages CI has no access
to the original files on a visitor's computer.

Before publishing any third-party character or game assets, confirm
that redistribution is authorized. Do not replace missing Switch models
with unverified fallback libraries. The visitor's folder picker works
without any public asset hosting.
