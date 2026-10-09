'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

for (const file of ['web/app.js', 'web/species-names.js', 'web/local-switch-catalog.js', 'web/remote-switch-catalog.js']) {
  new vm.Script(read(file), {filename:file});
}

const html = read('index.html');
const app = read('web/app.js');
const desktopBuild = read('desktopApp/build.gradle.kts');
const setup = read('scripts/setup_all.ps1');
const importer = read('scripts/import_switch_game_assets.py');
const restore = read('scripts/restore_switch_models.py');

for (const [,src] of html.matchAll(/<script[^>]+src="([^"?]+)(?:\?[^" ]*)?"/g)) {
  if (/^https?:/.test(src)) continue;
  assert.ok(fs.existsSync(path.join(root, src)), `Missing script: ${src}`);
}

assert.ok(!/battle[-_ ]?sim|brisk-engine|showBattle|battleView/i.test(html), 'Battle UI/engine must not be bundled');
assert.ok(!/pokeminers-manifest|pokedex3dpro-manifest|web\/models\/manifest\.js/i.test(html), 'Only the Switch manifest may feed models');
assert.ok(!/pokemon-3d-api|PokeMiners|fallbackUrl|raw\.githubusercontent|esm\.sh/i.test(app), 'Viewer must not contain legacy/remote model fallbacks');
assert.ok(/remote-switch-catalog\.js/.test(html), 'Independent web viewer must support opt-in hosted model catalog');
assert.ok(/POKEDEX3D_LOCAL_SWITCH/.test(app), 'Browser must support local Switch files without launcher');
assert.ok(/local-switch-catalog\.js/.test(html), 'Standalone browser catalog script must load');
assert.ok(/id="localModelsFolder"/.test(html), 'Static index must have a model folder picker');
assert.ok(/POKEDEX3D_SWITCH_MODELS/.test(app), 'Viewer must read the Switch manifest');
assert.ok(/form \|\| "regular"\)\.toLowerCase\(\) === "regular"/.test(app), 'Viewer must filter to regular forms');
assert.ok(/includes\("\/switch\/"\)/.test(app), 'Viewer must enforce Switch model paths');
assert.ok(!/graalvm|brisk-engine|battle/i.test(desktopBuild), 'Desktop package must not contain battle engine dependencies/resources');
assert.ok(!fs.existsSync(path.join(root,'desktopApp/src/main/kotlin/com/unbornefetus/pokedex3dmax/desktop/NativeBattle.kt')), 'Native battle engine must be removed');
assert.ok(!setup.includes('--allow-broken-textures'), 'Setup must reject broken texture exports');
assert.ok(!/download_models\.py|generic fallback model/i.test(setup), 'Setup must not contain generic model fallback paths');
assert.ok(/pipeline-v12\.ready\.json/.test(setup), 'Fast mode must require the strict v12 ready marker');
assert.ok(/CONVERSION_PIPELINE_VERSION = 12/.test(importer), 'Importer must use pipeline v12');
assert.ok(!/--allow-static/.test(importer), 'Static/T-pose activation must not be exposed');
assert.ok(/if form != "regular":\s*\n\s*continue/.test(importer), 'Importer must filter to regular forms');
assert.ok(/glb_textures_complete\(glb\)/.test(importer), 'Manifest generation must revalidate complete textures');
assert.ok(/textured == total/.test(importer), 'Every GLB material must have base-color coverage');
assert.ok(!/idle = clips\[0\]/.test(restore), 'Restore must not accept an arbitrary animation as idle');

console.log('Baseline checks passed: regular Switch-only viewer, embedded animations, strict texture gate, no legacy fallback or battle engine.');
