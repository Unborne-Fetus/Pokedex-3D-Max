'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const sandbox = {window:{},Set,Map,Array,Error,Number,String};
vm.runInNewContext(fs.readFileSync('web/gfpak-batch-import.js', 'utf8'), sandbox);
const {run} = sandbox.window.POKEDEX3D_GFPAK_BATCH;

async function main() {
  const files = [
    {name:'pm0519.zip',dex:519},
    {name:'broken.zip',error:'Bad GFPAK manifest'},
    {name:'pm0653.zip',dex:653},
    {name:'duplicate.zip',dex:519},
    {name:'not-a-zip.txt'},
    {name:'storage-failure.zip',dex:25},
    {name:'skip.zip',dex:494},
    {name:'PM0876.ZIP',dex:876},
  ];
  const accepted = [], phases = [];
  let active = 0, maxActive = 0;
  const result = await run(files, {
    read: async (file, single) => {
      assert.equal(single,false);
      active++;
      maxActive = Math.max(maxActive,active);
      await Promise.resolve();
      active--;
      if (file.error) throw Error(file.error);
      return {dex:file.dex,name:'Dex '+file.dex};
    },
    accept: async model => {
      if (model.dex === 25) throw Error('Storage rejected this model');
      if (model.dex === 494) return {skipped:true,detail:'Cancelled Egg placeholder'};
      accepted.push(model.dex);
      return {detail:'Saved locally'};
    },
    progress: state => phases.push(state)
  });
  assert.equal(maxActive,1,'files are decoded sequentially, not in parallel');
  assert.deepEqual(accepted,[519,653,876]);
  assert.equal(result.imported,3);
  assert.equal(result.rejected,4);
  assert.equal(result.skipped,1);
  assert.deepEqual(result.results.map(x=>x.status),
    ['imported','rejected','imported','rejected','rejected','rejected','skipped','imported']);
  assert.match(result.results[3].detail,/Duplicate Pokémon #0519/);
  assert.match(result.results[1].detail,/Bad GFPAK manifest/);
  assert.equal(phases.length, files.length*2);
  assert.deepEqual(phases.map(x=>x.phase).filter((_,i)=>i%2===0),
    Array(files.length).fill('reading'));
  assert.equal(phases.at(-1).imported,3);

  const single = await run([{name:'egg.zip',dex:494}],{
    read: async (_, one) => {
      assert.equal(one,true);
      return {dex:494};
    },
    accept: async () => ({detail:'Saved Victini placeholder locally'})
  });
  assert.equal(single.imported,1);
  assert.equal(single.rejected,0);

  const none = await run([], {
    read:()=>{ throw Error('Should not read empty selections'); },
    accept:()=>{ throw Error('Should not accept empty selections'); }
  });
  assert.equal(none.imported,0);
  assert.equal(none.results.length,0);

  const html = fs.readFileSync('index.html','utf8');
  const app = fs.readFileSync('web/app.js','utf8');
  assert.match(html, /<input id="gfpakZipFile"[^>]*\bmultiple\b/);
  assert.match(html, /src="web\/gfpak-batch-import\.js/);
  assert.match(html, /id="gfpakBatchResults"/);
  assert.match(app, /POKEDEX3D_GFPAK_BATCH\.run\(files/);
  assert.match(app, /for \(const \[index, imported\] of eligible\.entries\(\)\)/);
  console.log('GFPAK multi-ZIP batch tests passed.');
}

main().catch(error=>{console.error(error);process.exitCode=1;});
