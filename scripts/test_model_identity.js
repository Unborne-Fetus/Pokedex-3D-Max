"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const crypto = require("node:crypto");

const root = path.resolve(__dirname, "..");
const browser = {};
const context = { window: browser, TextDecoder, TextEncoder, Uint8Array, DataView,
  ArrayBuffer, crypto: crypto.webcrypto };
vm.runInNewContext(fs.readFileSync(path.join(root, "web/models/source-provenance.js"), "utf8"), context);
vm.runInNewContext(fs.readFileSync(path.join(root, "web/model-identity.js"), "utf8"), context);
const validator = browser.POKEDEX3D_MODEL_IDENTITY;
assert.equal(validator.nationalDex(1025, "sv"), 920);
assert.equal(validator.nationalDex(1010, "sv"), 906);
assert.equal(validator.nationalDex(801, "sv"), 747);
assert.equal(validator.nationalDex(1002, "la"), 900);
assert.equal(validator.nationalDex(942, "ZA-PokeDLC"), 876); // Indeedee, not Maschiff
assert.equal(validator.nationalDex(964, "ZA-PokeDLC"), 852); // Clobbopus, not Palafin
assert.equal(validator.nationalDex(965, "ZA-PokeDLC"), 853); // Grapploct, not Varoom
assert.equal(validator.nationalDex(920, "ZA-PokeDLC"), 823); // Corviknight, not Lokix
assert.equal(validator.nationalDex(1131, "za"), 1025); // Pecharunt

function fixture(internal) {
  const doc = {
    asset: { version: "2.0" },
    meshes: [{name: "pm" + String(internal).padStart(4, "0") + "_00_00"}],
    nodes: [{mesh:0}],
    scenes: [{nodes:[0]}],
  };
  const json = Buffer.from(JSON.stringify(doc), "utf8");
  const padded = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 32)]);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2,4);
  header.writeUInt32LE(padded.length + 20,8);
  header.writeUInt32LE(padded.length,12);
  header.writeUInt32LE(0x4e4f534a,16);
  const data = Buffer.concat([header,padded]);
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
}
const hash = bytes => crypto.createHash("sha1").update(
  Buffer.concat([Buffer.from("blob " + bytes.byteLength + "\0"),
                 Buffer.from(bytes)])).digest("hex");

(async () => {
  const lokix = fixture(1025), fuecoco = fixture(1013), caterpie = fixture(10);
  assert.equal((await validator.verify({dex:920,sourceGame:"SV-Poke",sourceModelId:1025}, lokix)).sourceModelId,1025);
  await assert.rejects(validator.verify({dex:1025,sourceGame:"SV-Poke",sourceModelId:1025},lokix),/Wrong Pokémon/);
  await assert.rejects(validator.verify({dex:801,sourceGame:"SV-Poke",sourceModelId:801},fixture(801)),/Wrong Pokémon/);
  for (const [wrong, right] of [[942, 876], [964, 852], [965, 853], [920, 823]]) {
    await assert.rejects(
      validator.verify({dex:wrong,sourceGame:"ZA-PokeDLC",sourceModelId:wrong},fixture(wrong)),
      /Wrong Pokémon/);
    assert.equal((await validator.verify(
      {dex:right,sourceGame:"ZA-PokeDLC",sourceModelId:wrong},fixture(wrong)
    )).sourceModelId,wrong);
    await assert.rejects(validator.verify({dex:wrong},fixture(wrong)),/Ambiguous/);
  }
  await assert.rejects(validator.verify({dex:909,sourceGame:"SV-Poke",sourceModelId:909},fuecoco),/disagrees|catalog/);
  assert.equal((await validator.verify({dex:909,sourceGame:"SV-Poke",sourceModelId:1013},fuecoco)).sourceModelId,1013);
  assert.equal((await validator.verify({dex:10,sourceGame:"swsh"},caterpie)).sourceModelId,10);
  await assert.rejects(validator.verify({dex:920,sourceGame:"SV-Poke",sourceBlobSha:"a".repeat(40)},lokix),/differs/);

  // Even an old catalog lacking internal-ID metadata is rejected when its
  // exact binary matches an independently known original asset fingerprint.
  browser.POKEDEX3D_SOURCE_PROVENANCE[hash(lokix)] = [1025, "SV-Poke"];
  await assert.rejects(validator.verify({dex:1025},lokix),/Wrong Pokémon/);
  assert.equal((await validator.verify({dex:920},lokix)).sourceGame,"sv");
  // A validated model must load without network on subsequent visits.
  const saved = new Map();
  let downloads = 0;
  context.Response = class {
    constructor(buffer) { this.buffer = buffer; }
    async arrayBuffer() { return this.buffer; }
  };
  context.caches = { open: async () => ({
    match: async key => saved.get(key),
    put: async (key, response) => { saved.set(key, response); },
    delete: async key => saved.delete(key),
  }) };
  context.fetch = async () => {
    downloads++;
    return { ok: true, status: 200, arrayBuffer: async () => lokix };
  };
  const model = { dex: 920, sourceBlobSha: hash(lokix), sourceGame: "SV-Poke",
    sourceModelId: 1025 };
  const url = "https://assets.test/switch/0920/regular.glb?rev=" + hash(lokix);
  await validator.loadVerified(model, url);
  await validator.loadVerified(model, url);
  assert.equal(downloads, 1, "Second validated model load must use offline cache");
  await assert.rejects(validator.loadVerified({ dex: 1025 }, url), /Wrong Pokémon/);
  assert.equal(downloads, 2, "A cached wrong Pokémon must not be displayed");
  console.log("Actual GLB source-ID checks and cache/fingerprint validation passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
