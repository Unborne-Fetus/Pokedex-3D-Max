'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '../web/local-switch-catalog.js'), 'utf8');
const context = {
  window: { POKEDEX3D_NAMES: { 1: 'Bulbasaur', 2: 'Ivysaur' } },
  TextDecoder, setTimeout,
};
vm.runInNewContext(script, context, { filename: 'web/local-switch-catalog.js' });
const { fromFiles } = context.window.POKEDEX3D_LOCAL_SWITCH;

function file(relative, obj) {
  const json = Buffer.from(JSON.stringify(obj), 'utf8');
  const padded = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 32)]);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(20 + padded.length, 8);
  header.writeUInt32LE(padded.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  const blob = new Blob([header, padded]);
  blob.webkitRelativePath = relative;
  return blob;
}
function doc(idle = 'idle', withTextures = true) {
  return {
    asset: { version: '2.0' },
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, material: 0 }] }],
    scenes: [{ nodes: [0] }],
    materials: [{
      pbrMetallicRoughness: withTextures ? { baseColorTexture: { index: 0 } } : {},
    }],
    textures: [{}],
    animations: [{ name: idle, channels: [{}], samplers: [{}] }],
  };
}
(async () => {
  const files = [
    file('offline-models/switch/0001/regular.glb', doc()),
    file('offline-models/switch/0002/regular.glb', doc('attack_01')),
    file('offline-models/switch/0003/regular.glb', doc('idle', false)),
    file('offline-models/switch/0004/form-01.glb', doc()),
    file('offline-models/generic/0005/regular.glb', doc()),
  ];
  const output = await fromFiles(files);
  assert.equal(output.scanned, 3);
  assert.equal(output.models.length, 1);
  assert.equal(output.models[0].dex, 1);
  assert.equal(output.models[0].name, 'Bulbasaur');
  assert.equal(output.models[0].idleAnimation, 'idle');
  assert.equal(output.models[0].url, 'web/models/switch/0001/regular.glb');
  assert.ok(output.models[0].file === files[0], 'Original local File must remain in browser memory');
  const annotated = await fromFiles([
    file('offline-models/switch/0002/regular.glb', doc('action_00')),
    Object.assign(new Blob([JSON.stringify([
      { dex: 2, form: 'regular', idleAnimation: 'action_00', idleBreaks: [] },
    ])]), { webkitRelativePath: 'offline-models/switch-model-metadata.json' }),
  ]);
  assert.equal(annotated.models.length, 1);
  assert.equal(annotated.models[0].idleAnimation, 'action_00');
  console.log('Static Switch catalog tests passed: local-only, texture and animation verification, metadata idle, no legacy model fallback.');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
