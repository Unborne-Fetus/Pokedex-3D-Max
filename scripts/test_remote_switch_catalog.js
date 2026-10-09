"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const assert = require("node:assert/strict");

const code = fs.readFileSync(path.join(__dirname, "../web/remote-switch-catalog.js"), "utf8");
function context(config) {
  const seen = [];
  const window = { POKEDEX3D_NAMES: { 1: "Bulbasaur" }, dispatchEvent: e => seen.push(e) };
  const loads = [];
  const ctx = {
    window, URL,
    location: { href: "https://example.com/Pokedex-3D-Max/index.html" },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    fetch: async url => { loads.push(String(url)); return {
      ok: true, json: async () => config,
    }; },
  };
  vm.runInNewContext(code, ctx, { filename: "web/remote-switch-catalog.js" });
  return { prepare: window.POKEDEX3D_REMOTE_SWITCH.prepare, loads, seen };
}
(async () => {
  const privateConfig = {
    repositoryVisibility: "private", enabled: false, manifestUrl: null,
  };
  const off = context(privateConfig);
  assert.equal(off.prepare(privateConfig, { format: 1, entries: [] }).length, 0);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(off.loads, ["web/models/remote-source.json"]);
  assert.equal(off.seen.length, 0);

  const config = {
    enabled: true,
    manifestUrl: "https://assets.example.org/switch-manifest.json",
  };
  const manifest = {
    format: 1,
    entries: [
      { dex: 1, form: "regular", path: "0001/regular.glb", ready: true, valid: true,
        idleAnimation: "idle", animations: ["idle", "wave"], idleBreaks: ["wave"] },
      { dex: 2, form: "regular", path: "0002/regular.glb", ready: false, valid: true,
        idleAnimation: "idle", animations: ["idle"] },
      { dex: 3, form: "regular", path: "../0003/regular.glb", ready: true, valid: true,
        idleAnimation: "idle", animations: ["idle"] },
      { dex: 4, form: "shiny", path: "0004/regular.glb", ready: true, valid: true,
        idleAnimation: "idle", animations: ["idle"] },
    ],
  };
  const tested = context(privateConfig).prepare(config, manifest);
  assert.equal(tested.length, 1);
  assert.equal(tested[0].name, "Bulbasaur");
  assert.equal(tested[0].url, "https://assets.example.org/0001/regular.glb");
  assert.equal(tested[0].idleAnimation, "idle");
  assert.equal(tested[0].idleBreaks.join(","), "wave");
  console.log("Remote model catalog checks passed: disabled private source, strict animated regular models, safe HTTPS paths.");
})().catch(error => { console.error(error); process.exitCode = 1; });
