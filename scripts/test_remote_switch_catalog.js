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
  document: { readyState: "loading", addEventListener() {} },
  location: { protocol: "https:" },
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
  fetch: async () => { throw Error("Automated test does not need network"); },
};
browser.dispatchEvent = event => events.push(event);
vm.runInNewContext(inventoryScript, context, { filename: "github-inventory.js" });
vm.runInNewContext(source, context, { filename: "remote-switch-catalog.js" });
const { prepare, inspect } = browser.POKEDEX3D_REMOTE_SWITCH;

assert.equal(sourceConfig.enabled, true);
assert.equal(sourceConfig.repositoryVisibility, "public");
assert.equal(sourceConfig.allowUnverifiedInventory, true);
const selected = prepare(sourceConfig, browser.POKEDEX3D_PUBLIC_INVENTORY);
assert.equal(selected.length, browser.POKEDEX3D_PUBLIC_INVENTORY.count);
assert.equal(selected[0].dex, 1);
assert.equal(selected[0].name, "Bulbasaur");
assert.equal(selected[0].preflightRequired, true);
assert.equal(selected[0].url,
  "https://raw.githubusercontent.com/Unborne-Fetus/Pokedex-3D-Models-Animations/main/0001/regular.glb");
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
assert.equal(events.length, 0, "Network/start must wait for the page to finish loading");
console.log("GitHub-only web model tests passed: inventory, safe URLs, embedded textures, and real idle validation.");
