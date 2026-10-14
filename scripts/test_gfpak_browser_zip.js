const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const zlib = require('node:zlib');
const { File } = require('node:buffer');

function zip(members, deflated = false) {
  const locals = [], central = [];
  let offset = 0;
  for (const [name, payload] of members) {
    const file = Buffer.from(name, 'utf8');
    const data = Buffer.from(payload);
    const compressed = deflated ? zlib.deflateRawSync(data) : data;
    const method = deflated ? 8 : 0;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(method, 8);
    local.writeUInt32LE(compressed.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(file.length, 26);
    locals.push(local, file, compressed);
    const entry = Buffer.alloc(46);
    entry.writeUInt32LE(0x02014b50, 0);
    entry.writeUInt16LE(20, 4);
    entry.writeUInt16LE(20, 6);
    entry.writeUInt16LE(method, 10);
    entry.writeUInt32LE(compressed.length, 20);
    entry.writeUInt32LE(data.length, 24);
    entry.writeUInt16LE(file.length, 28);
    entry.writeUInt32LE(offset, 42);
    central.push(entry, file);
    offset += local.length + file.length + compressed.length;
  }
  const size = central.reduce((n, item) => n + item.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(members.length, 8);
  end.writeUInt16LE(members.length, 10);
  end.writeUInt32LE(size, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, ...central, end]);
}

const sandbox = {
  window: {
    POKEDEX3D_NAMES: {876:'Indeedee',877:'Morpeko',494:'Victini'},
    POKEDEX3D_MODEL_IDENTITY: {
      nationalDex: (id, game) => game === 'za' && id === 942 ? 876 :
        game === 'za' && id === 943 ? 877 : 0,
      verify: async (model, bytes) => {
        assert.ok([494,876,877].includes(model.dex));
        if (model.eggPlaceholder) assert.equal(model.sourceModelId, 0);
        assert.equal(bytes.byteLength, 24);
      }
    },
    POKEDEX3D_LOCAL_SWITCH: { inspectGlb: async () => ['battle_idle'] },
  },
  TextDecoder, TextEncoder, ArrayBuffer, DataView, Uint8Array, Blob, File, Response, DecompressionStream,
  Error, Set, Map
};
vm.runInNewContext(fs.readFileSync('web/gfpak-zip-import.js', 'utf8'), sandbox);
vm.runInNewContext(fs.readFileSync('web/gfpak-batch-import.js', 'utf8'), sandbox);
const read = sandbox.window.POKEDEX3D_GFPAK_ZIP.read;
const meta = {
  format:'gfpak-pokemon-export', version:1, sourceGame:'za',
  selectedModel:'pm0942_00_00.trmdl',
  convertedModel:'pokedex3d/regular.glb'
};
const glb = Buffer.alloc(24);
glb.writeUInt32LE(0x46546c67,0);
glb.writeUInt32LE(2,4);
glb.writeUInt32LE(24,8);

async function check(method) {
  const data = zip([
    ['gfpak-pokemon-export.json',Buffer.from(JSON.stringify(meta))],
    ['pokedex3d/regular.glb',glb]
  ], method);
  const file = new File([data], 'pm0942.zip');
  const result = await read(file);
  assert.equal(result.dex, 876);
  assert.equal(result.name, 'Indeedee');
  assert.equal(result.idleAnimation, 'battle_idle');
  assert.equal(result.sourceModelId, 942);
  assert.equal(result.orientation, '0deg 0deg 0deg');
  assert.equal(result.orientationVersion, 2);
}

(async()=>{
  const repair = sandbox.window.POKEDEX3D_GFPAK_ZIP.repairGlb;
  const document = {asset:{generator:'THREE.GLTFExporter r180'},
    accessors:[{componentType:5126,max:[255,255,255,255]}, {componentType:5126,max:[1,1,1,1]}],
    meshes:[{primitives:[{attributes:{POSITION:2,COLOR_0:0}}, {attributes:{POSITION:2,COLOR_0:1}}]}]};
  const json = Buffer.from(JSON.stringify(document));
  const padded = Math.ceil(json.length/4)*4;
  const sample = Buffer.alloc(20+padded+12,32);
  sample.writeUInt32LE(0x46546c67,0);sample.writeUInt32LE(2,4);
  sample.writeUInt32LE(sample.length,8);sample.writeUInt32LE(padded,12);
  sample.writeUInt32LE(0x4e4f534a,16);json.copy(sample,20);
  const tail = Buffer.from([4,0,0,0,66,73,78,0,1,2,3,4]);tail.copy(sample,20+padded);
  const input = sample.buffer.slice(sample.byteOffset,sample.byteOffset+sample.byteLength);
  const fixed = repair(input);
  const bytes = Buffer.from(fixed); const size = bytes.readUInt32LE(12);
  const doc = JSON.parse(bytes.subarray(20,20+size));
  assert.equal(doc.meshes[0].primitives[0].attributes.COLOR_0,undefined);
  assert.equal(doc.meshes[0].primitives[1].attributes.COLOR_0,1);
  assert.deepEqual(bytes.subarray(20+size),tail); // Images, rig and clips are unchanged.
  assert.equal(bytes.readUInt32LE(8),bytes.length);
  assert.equal(repair(fixed),fixed); // Safe to re-open a repaired saved import.
  const orientation = sandbox.window.POKEDEX3D_GFPAK_ZIP.orientation;
  assert.equal(orientation({}), '0deg 0deg 0deg');
  assert.equal(orientation({orientation:'0deg 90deg 0deg'}), '0deg 0deg 0deg');
  assert.equal(orientation({orientation:'0deg 90deg 0deg',orientationVersion:2}), '0deg 90deg 0deg');
  assert.equal(orientation({orientation:'90deg 90deg 0deg'}), '90deg 90deg 0deg');
  await check(false);
  if (typeof DecompressionStream !== 'undefined') await check(true);
  // Two complete GFPAK exports can be selected together; a malformed ZIP
  // between them does not prevent the later species from importing.
  const mk = (identity, filename) => new File([zip([
    ['gfpak-pokemon-export.json',Buffer.from(JSON.stringify({
      ...meta,selectedModel: 'pm' + identity + '_00_00.trmdl'
    }))],
    ['pokedex3d/regular.glb',glb]
  ])], filename);
  const batchFiles = [
    mk('0942','pm0942.zip'),
    new File([Buffer.from('not a zip')],'invalid.zip'),
    mk('0943','pm0943.zip')
  ];
  const saved = [];
  const batch = await sandbox.window.POKEDEX3D_GFPAK_BATCH.run(batchFiles,{
    read:file=>read(file),
    accept:async model=>{ saved.push(model);return {detail:'Saved locally'}; }
  });
  assert.equal(batch.imported,2);
  assert.equal(batch.rejected,1);
  assert.deepEqual(saved.map(model=>model.dex),[876,877]);
  assert.ok(saved.every(model=>model.file instanceof File && model.idleAnimation==='battle_idle'));
  const eggMeta = {...meta, sourceGame:'swsh', selectedModel:'pm0000_resource_0009.gfbmdl'};
  const eggZip = zip([
    ['gfpak-pokemon-export.json',Buffer.from(JSON.stringify(eggMeta))],
    ['pokedex3d/regular.glb',glb]
  ]);
  const eggFile = new File([eggZip], 'pm0000.zip');
  await assert.rejects(read(eggFile), /Egg/);
  await assert.rejects(read(eggFile, {targetDex:493}), /Egg/);
  const egg = await read(eggFile, {targetDex:494});
  assert.equal(egg.dex,494);
  assert.equal(egg.name,'Victini');
  assert.equal(egg.sourceModelId,0);
  assert.equal(egg.eggPlaceholder,true);
  assert.equal(egg.idleAnimation,'battle_idle');
  const raw = {...meta, convertedModel:null};
  const data = zip([['gfpak-pokemon-export.json',Buffer.from(JSON.stringify(raw))]]);
  await assert.rejects(read(new File([data],'raw.zip')), /original assets only/);
  console.log('GFPAK browser ZIP preview tests passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
