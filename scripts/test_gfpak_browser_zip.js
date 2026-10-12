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
    POKEDEX3D_NAMES: {876:'Indeedee'},
    POKEDEX3D_MODEL_IDENTITY: {
      nationalDex: (id, game) => id === 942 && game === 'za' ? 876 : 0,
      verify: async (model, bytes) => {
        assert.equal(model.dex, 876);
        assert.equal(bytes.byteLength, 24);
      }
    },
    POKEDEX3D_LOCAL_SWITCH: { inspectGlb: async () => ['battle_idle'] },
  },
  TextDecoder, DataView, Uint8Array, Blob, File, Response, DecompressionStream,
  Error, Set, Map
};
vm.runInNewContext(fs.readFileSync('web/gfpak-zip-import.js', 'utf8'), sandbox);
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
}

(async()=>{
  await check(false);
  if (typeof DecompressionStream !== 'undefined') await check(true);
  const raw = {...meta, convertedModel:null};
  const data = zip([['gfpak-pokemon-export.json',Buffer.from(JSON.stringify(raw))]]);
  await assert.rejects(read(new File([data],'raw.zip')), /original assets only/);
  console.log('GFPAK browser ZIP preview tests passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
