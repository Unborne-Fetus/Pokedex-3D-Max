'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
for (const file of ['web/app.js', 'web/battle-sim.js', 'web/brisk-engine/browser-engine.js', 'web/brisk-engine/data.js', 'web/species-names.js']) {
  new vm.Script(read(file), {filename:file});
}
const html = read('index.html');
for (const [,src] of html.matchAll(/<script[^>]+src="([^"?]+)(?:\?[^" ]*)?"/g)) {
  if (/^https?:/.test(src) || /(?:desktop-models|pokeminers-manifest)\.js$/.test(src)) continue;
  assert.ok(fs.existsSync(path.join(root,src)), `Missing script: ${src}`);
}
assert.ok(!html.includes('</script>\\n'), 'Literal newline escape in HTML');
// Test Switch source priority independently of DOM/network/catalog cache.
const modelSource = read('web/app.js').split('const REGULAR_MODEL')[0];
const modelContext = vm.createContext({window:{
  POKEDEX3D_LOCAL_MODELS:[{dex:6,form:'xy',url:'old-mega.glb'}],
  POKEDEX3D_SWITCH_MODELS:[
    {dex:6,form:'regular',url:'web/models/switch/0006/regular.glb',source:'Switch game assets'},
    {dex:6,form:'form-51-00',url:'web/models/switch/0006/form-51-00.glb',source:'Switch game assets'},
  ]
}});
vm.runInContext(modelSource + ';function formRank(){return 0;}', modelContext);
const selected = vm.runInContext('applyLocalModelOverrides([{dex:6,form:"regular",url:"old.glb"},{dex:6,form:"xy",url:"old-mega.glb"}])', modelContext);
assert.equal(selected.length,2);
assert.ok(selected.every(m=>m.url.includes('/switch/')));
const candidates = read('web/app.js').match(/function getModelCandidates\(model\) \{[\s\S]*?\n\}/)[0];
vm.runInContext('const REGULAR_MODEL = id => "old/"+id; ' + candidates, modelContext);
assert.equal(vm.runInContext('getModelCandidates({dex:6,local:true,url:"web/models/switch/0006/regular.glb",fallbackUrl:"old.glb"}).length',modelContext),1);
modelContext.window.POKEDEX3D_MODEL_POLICY = {switchOnly:true};
const switchOnly = vm.runInContext('applyLocalModelOverrides([{dex:25,form:"regular",url:"old-pikachu.glb"}])',modelContext);
assert.equal(switchOnly.length,2);
assert.ok(switchOnly.every(m=>m.url.includes('/switch/')));
assert.ok(!read('desktopApp/build.gradle.kts').includes('include("index.html"'), 'Native EXE must not bundle the index');
assert.ok(!fs.existsSync(path.join(root,'desktopApp/src/main/java/com/unbornefetus/pokedex3dmax/desktop/SharedApp.java')), 'Browser launcher must be removed');
let seed=12345;
const seededMath=Object.create(Math);
seededMath.random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
const context = vm.createContext({window:{}, console, Math:seededMath, Date, setTimeout, clearTimeout});
vm.runInContext(read('web/brisk-engine/data.js'), context);
vm.runInContext(read('web/brisk-engine/browser-engine.js'), context);
(async () => {
  const engine = context.window.BriskBattleEngine;
  await engine.loadData('unused'); // Works without HTTP, including file://.
  assert.throws(() => engine.createBotBattle(['charizard','not-a-pokemon','pikachu'],'normal'), /Unknown/);
  for (const difficulty of ['easy','normal','hard']) {
    const room = engine.createBotBattle(['charizard','pikachu','lucario'], difficulty);
    let snapshot = engine.snapshot(room);
    assert.equal(snapshot.phase,'battle');
    assert.equal(snapshot.players[0].team.length,3);
    assert.equal(snapshot.players[1].team.length,3);
    assert.ok(snapshot.players.every(p=>p.team.every(m=>m.moves.length && m.maxHP>0)));
    snapshot = engine.submitSwitch(room,1);
    assert.ok(snapshot.log.some(line=>line.includes("Player switched to Pikachu!")));
    for (let turn=0; turn<500 && snapshot.phase==='battle'; turn++) {
      const player=snapshot.players[0], mon=player.team[player.active];
      let index=mon.moves.findIndex(m=>m.pp>0 && m.power>0);
      if(index<0)index=mon.moves.findIndex(m=>m.pp>0);
      snapshot=engine.submitMove(room,Math.max(index,0));
      assert.ok(snapshot.players.every(p=>p.team.every(m=>Number.isFinite(m.hp)&&m.hp>=0&&m.hp<=m.maxHP)), 'Invalid HP');
    }
    assert.equal(snapshot.phase,'finished', `Battle did not finish: ${difficulty}`);
    assert.ok([0,1].includes(snapshot.winner));
  }
  const data=JSON.parse(read('web/brisk-engine/brisk-dex-data.json'));
  assert.deepEqual(JSON.parse(JSON.stringify(context.window.BRISK_BATTLE_DATA)),data,'Inline and JSON battle data differ');
  console.log('Shared app checks passed: syntax, assets, offline data, teams, switching, full battles (3 difficulties).');
})().catch(error=>{console.error(error);process.exitCode=1;});
