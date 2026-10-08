'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

for (const file of ['web/app.js', 'web/species-names.js']) {
  new vm.Script(read(file), {filename:file});
}

const html = read('index.html');
for (const [,src] of html.matchAll(/<script[^>]+src="([^"?]+)(?:\?[^" ]*)?"/g)) {
  if (/^https?:/.test(src) || /(?:desktop-models|pokeminers-manifest)\.js$/.test(src)) continue;
  assert.ok(fs.existsSync(path.join(root,src)), `Missing script: ${src}`);
}
assert.ok(!/battle[-_ ]?sim|brisk-engine|showBattle|battleView/i.test(html), 'Battle UI/engine must not be bundled');

const modelSource = read('web/app.js').split('const REGULAR_MODEL')[0];
const modelContext = vm.createContext({window:{
  POKEDEX3D_LOCAL_MODELS:[{dex:6,form:'regular',url:'old.glb'}],
  POKEDEX3D_PRO_MODELS:[{dex:6,form:'regular',url:'pro.glb'}],
  POKEDEX3D_SWITCH_MODELS:[
    {dex:6,form:'regular',url:'web/models/switch/0006/regular.glb',source:'Switch game assets',ready:true,valid:true},
    {dex:6,form:'form-51-00',url:'web/models/switch/0006/form-51-00.glb',source:'Switch game assets',ready:true,valid:true},
    {dex:25,form:'shiny',url:'web/models/switch/0025/shiny.glb',source:'Switch game assets',ready:true,valid:true},
  ]
}});
vm.runInContext(modelSource + ';function formRank(){return 0;}', modelContext);
const selected = vm.runInContext('applyLocalModelOverrides([{dex:6,form:"regular",url:"old.glb"}])', modelContext);
assert.equal(selected.length, 1);
assert.equal(selected[0].form, 'regular');
assert.ok(selected[0].url.includes('/switch/'));

const candidates = read('web/app.js').match(/function getModelCandidates\(model\) \{[\s\S]*?\n\}/)[0];
vm.runInContext('const CDN_ROOT=""; const REGULAR_MODEL=id=>"old/"+id; function toFastAssetUrl(x){return x;} function modelAssetPath(){return null;} ' + candidates, modelContext);
assert.deepEqual(
  JSON.parse(vm.runInContext('JSON.stringify(getModelCandidates({dex:6,local:true,source:"Switch game assets",url:"web/models/switch/0006/regular.glb"}))', modelContext)),
  ['web/models/switch/0006/regular.glb']
);

const desktopBuild = read('desktopApp/build.gradle.kts');
assert.ok(!/graalvm|brisk-engine|battle/i.test(desktopBuild), 'Desktop package must not contain battle engine dependencies/resources');
assert.ok(!fs.existsSync(path.join(root,'desktopApp/src/main/kotlin/com/unbornefetus/pokedex3dmax/desktop/NativeBattle.kt')), 'Native battle engine must be removed');

const setup = read('scripts/setup_all.ps1');
assert.ok(!setup.includes('--allow-broken-textures'), 'Setup must reject broken texture exports');

console.log('Baseline checks passed: regular Switch-only viewer, no battle engine, no legacy fallback, strict texture gate.');
