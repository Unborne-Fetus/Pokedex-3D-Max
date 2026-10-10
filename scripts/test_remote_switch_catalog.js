"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");

const source = fs.readFileSync(path.join(__dirname, "../web/remote-switch-catalog.js"), "utf8");
const inventoryScript = fs.readFileSync(path.join(__dirname, "../web/models/github-inventory.js"), "utf8");
const sourceConfig = JSON.parse(fs.readFileSync(
  path.join(__dirname, "../web/models/remote-source.json"), "utf8"
));

const browser = { POKEDEX3D_NAMES: { 1: "Bulbasaur" } };
const events = [];
const context = {
  window: browser, TextDecoder, URL, setTimeout,
  ArrayBuffer, DataView, Uint8Array, Float32Array,
  document: { readyState: "loading", addEventListener() {} },
  location: { protocol: "https:" },
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
  fetch: async () => { throw Error("Automated test does not need network"); },
};
browser.dispatchEvent = event => events.push(event);
vm.runInNewContext(inventoryScript, context, { filename: "github-inventory.js" });
vm.runInNewContext(source, context, { filename: "remote-switch-catalog.js" });
const { prepare, inspect, bundled } = browser.POKEDEX3D_REMOTE_SWITCH;

assert.equal(sourceConfig.enabled, true);
assert.equal(sourceConfig.repositoryVisibility, "public");
assert.equal(sourceConfig.allowUnverifiedInventory, true);
const selected = prepare(sourceConfig, browser.POKEDEX3D_PUBLIC_INVENTORY);
// The physical inventory has legacy folder slots. A few remap to the
// same real species, so the visible National Dex catalog is deduplicated.
assert.ok(selected.length <= browser.POKEDEX3D_PUBLIC_INVENTORY.count);
assert.equal(new Set(selected.map(model => model.dex)).size, selected.length);
assert.equal(selected.some(model => model.dex === 964), false,
  "The pm0964 Z-A GLB must not masquerade as Palafin (#964)");
assert.equal(selected.some(model => model.dex === 965), false,
  "The pm0965 Z-A GLB must not masquerade as Varoom (#965)");
assert.equal(selected.some(model => model.dex === 942), false,
  "The pm0942 Z-A GLB must not masquerade as Maschiff (#942)");
const grapploct = selected.find(model => model.dex === 853);
assert.equal(grapploct.sourceModelId, 965);
assert.equal(grapploct.sourceGame, "SwSh-PokeGen8");
const preloaded = bundled();
assert.equal(preloaded.length, selected.length, "The initial page catalog must already include uploaded GLBs");
for (let dex = 1; dex <= 9; dex++) {
  const model = preloaded.find(item => item.dex === dex);
  assert.ok(model && model.remoteSwitch && model.preflightRequired,
    "Original Switch GLB #" + String(dex).padStart(4, "0") + " must be in the startup catalog");
}

assert.equal(selected[0].dex, 1);
assert.equal(selected[0].name, "Bulbasaur");
assert.equal(selected[0].preflightRequired, true);
assert.equal(new URL(selected[0].url).pathname,
  "/Unborne-Fetus/Pokedex-3D-Models-Animations/main/0001/regular.glb");
assert.equal(new URL(selected[0].url).searchParams.get("rev"),
  browser.POKEDEX3D_PUBLIC_INVENTORY.entries[0].sha);
assert.equal(selected[0].sourceBlobSha,
  browser.POKEDEX3D_PUBLIC_INVENTORY.entries[0].sha);
assert.equal(selected[0].sourceModelId,
  browser.POKEDEX3D_PUBLIC_INVENTORY.entries[0].sourceModelId);
assert.equal(prepare({ ...sourceConfig, enabled: false }, browser.POKEDEX3D_PUBLIC_INVENTORY).length, 0);

const unsafe = {
  format: 1, source: "github-model-file-inventory", entries: [
    { dex: 3, path: "../0003/regular.glb" },
    { dex: 4, path: "https://evil.example/0004/regular.glb" },
    { dex: 5, path: "0005/shiny.glb" },
    { dex: 6, path: "0006/regular.glb" },
  ],
};
const safe = prepare(sourceConfig, unsafe);
assert.equal(safe.length, 1);
assert.equal(safe[0].dex, 6);

function testGlb(options = {}) {
  const doc = {
    asset: { version: "2.0" },
    meshes: [{}], scenes: [{}],
    materials: [{ pbrMetallicRoughness: { baseColorTexture: { index: 0 } } }],
    textures: [{ source: 0 }],
    images: options.noImage ? [] : [{ bufferView: 0 }],
    animations: [{ name: options.animation || "BattleIdle_01", channels: [{}], samplers: [{}] }],
  };
  const json = Buffer.from(JSON.stringify(doc));
  const padded = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 32)]);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(20 + padded.length, 8);
  header.writeUInt32LE(padded.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  const bytes = Buffer.concat([header, padded]);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}
assert.equal(inspect(testGlb()).idleAnimation, "BattleIdle_01");
assert.throws(() => inspect(testGlb({ animation: "attack_01" })), /idle/);
assert.throws(() => inspect(testGlb({ noImage: true })), /image/);

// Blender exports some genuine Switch idles with only the name "Animation".
// Accept a single generic clip only when several joints actually move.
function genericRigClip(moving) {
  const times = Buffer.alloc(8);
  times.writeFloatLE(0, 0);
  times.writeFloatLE(1.833333, 4);
  const tracks = [0, 1, 2].map(index => {
    const track = Buffer.alloc(24);
    track.writeFloatLE(0, 0);
    track.writeFloatLE(moving ? 0.02 + index * 0.01 : 0, 12);
    return track;
  });
  const bin = Buffer.concat([times, ...tracks]);
  const doc = {
    asset: { version: "2.0" },
    buffers: [{ byteLength: bin.length }],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: 8 },
      ...tracks.map((track, index) => ({
        buffer: 0, byteOffset: 8 + 24 * index, byteLength: 24,
      })),
    ],
    accessors: [
      { bufferView: 0, componentType: 5126, count: 2,
        type: "SCALAR", min: [0], max: [1.833333] },
      ...tracks.map((_, index) => ({
        bufferView: index + 1, componentType: 5126, count: 2, type: "VEC3",
      })),
    ],
    nodes: [{}, {}, {}],
    skins: [{ joints: [0, 1, 2] }],
    meshes: [{}], scenes: [{}],
    materials: [{ pbrMetallicRoughness: { baseColorTexture: { index: 0 } } }],
    textures: [{ source: 0 }], images: [{ bufferView: 0 }],
    animations: [{
      name: "Animation",
      samplers: tracks.map((_, index) => ({
        input: 0, output: index + 1, interpolation: "LINEAR",
      })),
      channels: tracks.map((_, index) => ({
        sampler: index, target: { node: index, path: "translation" },
      })),
    }],
  };
  const json = Buffer.from(JSON.stringify(doc));
  const padded = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 32)]);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(20 + padded.length + 8 + bin.length, 8);
  header.writeUInt32LE(padded.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(bin.length, 0);
  binHeader.writeUInt32LE(0x004e4942, 4);
  const bytes = Buffer.concat([header, padded, binHeader, bin]);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}
assert.equal(inspect(genericRigClip(true)).idleAnimation, "Animation");
assert.throws(() => inspect(genericRigClip(false)), /moving idle/);

assert.equal(events.length, 0, "Network/start must wait for the page to finish loading");
console.log("GitHub-only model tests passed: named idles, moving single Animation clips, static rejection, and textures.");
