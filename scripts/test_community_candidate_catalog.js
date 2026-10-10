"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
const community = fs.readFileSync(path.join(root, "web/community-candidate-catalog.js"), "utf8");
const app = fs.readFileSync(path.join(root, "web/app.js"), "utf8");
const index = fs.readFileSync(path.join(root, "index.html"), "utf8");
const context = {
  window: {POKEDEX3D_NAMES: {645:"Landorus", 916:"Oinkologne"}},
  TextDecoder, DataView, Uint8Array, ArrayBuffer, Set, Map, Number, Object,
};
vm.runInNewContext(community, context, {filename:"web/community-candidate-catalog.js"});
const {models, inspect, isCandidateURL} = context.window.POKEDEX3D_COMMUNITY_CANDIDATES;
const ids = [645,899,900,905,911,916,941,947,981,983,987,994,995,999,1000,1003,1004];
assert.deepEqual(Array.from(models.map(m=>m.dex)), ids);
assert.ok(models.every(m=>m.remoteSwitch && m.communityCandidate && m.preflightRequired));
assert.ok(models.every(m=>m.assetRevision && /^https:\/\/raw\.githubusercontent\.com\/pokemon-party\/3d-pokemon\/[a-f0-9]{40}\/models\/opt\/regular\//.test(m.url)));
assert.ok(models.every(m=>isCandidateURL(m.dex,m.url)));
assert.ok(!isCandidateURL(645, "http://malicious.example/645.glb"));
const gender = models.find(m=>m.dex===916);
assert.equal(gender.variants.length, 2);
assert.equal(gender.variantLabel, "Male");
assert.ok(gender.variants.some(v=>v.name==="916-F.glb"));

function makeGlb(name="defaultidle01", options={}) {
  const doc = {
    asset:{version:"2.0"}, scenes:[{nodes:[0]}],nodes:[{}],
    meshes:[{primitives:[{attributes:{POSITION:0}, material:0}]}],
    materials:[{pbrMetallicRoughness:{baseColorTexture:{index:0}}}],
    textures:[{extensions:{EXT_texture_webp:{source:0}}}],
    images:[{mimeType:"image/webp", bufferView:0}],
    bufferViews:[{buffer:0,byteOffset:0,byteLength:12}],
    accessors:[{count:2,type:"SCALAR"},{count:2,type:"VEC4"}],
    animations:[{name,channels:[{sampler:0,target:{node:0,path:"rotation"}}],
      samplers:[{input:0,output:1}]}],
  };
  if (options.missingTexture) doc.materials[0].pbrMetallicRoughness = {};
  if (options.missingAnimation) doc.animations = [];
  if (options.brokenSampler) doc.animations[0].samplers = [];
  const rawJson = Buffer.from(JSON.stringify(doc), "utf8");
  const json = Buffer.concat([rawJson, Buffer.alloc((4-rawJson.length%4)%4, 32)]);
  const bin = Buffer.from([82,73,70,70,4,0,0,0,87,69,66,80]);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67,0);
  header.writeUInt32LE(2,4);
  header.writeUInt32LE(20+json.length+8+bin.length,8);
  header.writeUInt32LE(json.length,12);
  header.writeUInt32LE(0x4e4f534a,16);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(bin.length,0);
  binHeader.writeUInt32LE(0x004e4942,4);
  const bytes=Buffer.concat([header,json,binHeader,bin]);
  return bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength);
}
assert.equal(inspect(makeGlb()).idleAnimation,"defaultidle01");
assert.equal(inspect(makeGlb("battlewait")).idleAnimation,"battlewait");
assert.throws(()=>inspect(makeGlb("attack01")), /idle/i);
assert.throws(()=>inspect(makeGlb("defaultidle01",{missingAnimation:true})),/idle/i);
assert.throws(()=>inspect(makeGlb("defaultidle01",{brokenSampler:true})),/idle/i);
assert.throws(()=>inspect(makeGlb("defaultidle01",{missingTexture:true})),/texture/i);
const bad=makeGlb();new DataView(bad).setUint32(8,2,true);
assert.throws(()=>inspect(bad), /GLB metadata/);

const start=app.indexOf("function normalizeSwitchModel(");
const end=app.indexOf("// The uploaded-file catalog",start);
assert.ok(start>=0 && end>start);
const sandbox={window:context.window,Map,Number,Object};
vm.runInNewContext(app.slice(start,end),sandbox);
const existing={dex:645,name:"Landorus",url:"web/models/switch/0645/regular.glb",form:"regular"};
const withGaps=[existing,{dex:916,missingModel:true}];
const merged=Array.from(sandbox.withMissingSpeciesEntries(withGaps));
assert.strictEqual(merged.find(x=>x.dex===645),existing,"Never override a Switch model");
assert.equal(merged.find(x=>x.dex===916).communityCandidate,true);
assert.equal(merged.filter(x=>x.communityCandidate).length,16);
const local=Array.from(sandbox.withMissingSpeciesEntries(withGaps,false));
assert.equal(local.filter(x=>x.communityCandidate).length,0,
  "Choosing a local Switch folder must stay local");

assert.ok(index.indexOf("web/community-candidate-catalog.js") <
          index.indexOf("web/app.js"),"Candidate metadata must precede web app");
assert.ok(index.includes('id="externalModelSource"'),"Source credit link must exist");
assert.ok(/fromCommunity\s*\?\s*window\.POKEDEX3D_COMMUNITY_CANDIDATES\.inspect\(data\)/.test(app),
  "Downloaded community candidates must pass runtime GLB validation");
assert.ok(/!fromCommunity && typeof window\.POKEDEX3D_REPAIR_SWITCH_MODEL/.test(app),
  "Never run Switch material repairs on third-party candidates");
console.log("17 candidate species, source whitelist, material/idle validation, Switch priority and local-only safeguards passed.");
