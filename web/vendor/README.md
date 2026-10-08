Bundled renderer: @google/model-viewer 4.3.1 (Google LLC; included license file and BSD-3-Clause bundle notices).
Source: https://cdn.jsdelivr.net/npm/@google/model-viewer@4.3.1/dist/model-viewer.min.js
The final ES-module exports are removed and the bundle is wrapped in an IIFE so index.html can bootstrap from file:// too. License notices remain in the bundle.
Draco 1.5.7 decoders: https://www.gstatic.com/draco/versioned/decoders/1.5.7/ (Google, Apache-2.0).
The HTTP-served viewer uses these local decoders; direct file:// uses the default online decoder because browsers restrict local fetches.
