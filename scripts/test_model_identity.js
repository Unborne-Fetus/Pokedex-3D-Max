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
  await assert.rejects(validator.verify({dex:909,sourceGame:"SV-Poke",sourceModelId:909},fuecoco),/disagrees|catalog/);
  assert.equal((await validator.verify({dex:909,sourceGame:"SV-Poke",sourceModelId:1013},fuecoco)).sourceModelId,1013);
  assert.equal((await validator.verify({dex:10,sourceGame:"swsh"},caterpie)).sourceModelId,10);
  await assert.rejects(validator.verify({dex:920,sourceGame:"SV-Poke",sourceBlobSha:"a".repeat(40)},lokix),/differs/);

  // Even an old catalog lacking internal-ID metadata is rejected when its
  // exact binary matches an independently known original asset fingerprint.
  browser.POKEDEX3D_SOURCE_PROVENANCE[hash(lokix)] = [1025, "SV-Poke"];
  await assert.rejects(validator.verify({dex:1025},lokix),/Wrong Pokémon/);
  assert.equal((await validator.verify({dex:920},lokix)).sourceGame,"sv");
  console.log("Actual GLB source-ID checks and cache/fingerprint validation passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
