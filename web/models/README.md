# Website model inventory

The deployed GitHub Pages site is hosted from the **public**
[`Pokedex-3D-Models-Animations`](https://github.com/Unborne-Fetus/Pokedex-3D-Models-Animations)
repository, not from this private development repository.

The public repository includes `index.html`, `web/`, and 756 numbered
`0001/regular.glb`-style Switch models at its root. GitHub Pages can
serve the website and GLBs from the same origin once Pages is enabled from
**main / (root)**. No GitHub Actions workflow, command-line build, or
payment information is required.

`github-inventory.js` stores a small metadata snapshot of the uploaded
filenames; `remote-source.json` enables the corresponding public catalog.
A list of filenames is **not** proof of texture or animation quality:
the browser validates each GLB's embedded material images and idle clips
when that Pokémon is opened. These checks do not prove the visual
appearance matches the source game.

The local `index.html` can still load models through its folder picker.
Original downloaded Switch archives are not committed to this development
repository. Uploading publicly redistributable model assets requires
appropriate permission.

The currently deployed public website code is a copy of the files under
this development repository's `index.html` and `web/` (excluding local
GLBs). Later viewer updates must be synchronized into the public model
repository to reach its GitHub Pages site.
