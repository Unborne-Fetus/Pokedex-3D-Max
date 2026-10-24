"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../web/github-model-storage.js"), "utf8");
const repo = "https://api.github.com/repos/Unborne-Fetus/Pokedex-3D-Models-Animations";
const token = "github_pat_FAKE_TEST_ONLY";
const sha = character => character.repeat(40);
const base = { format: 1, source: "pokedex3d-temporary-github-imports" };
class FakeFile {
  constructor(bytes, name = "regular.glb") {
    this.bytes = Uint8Array.from(bytes);
    this.name = name;
    this.size = this.bytes.length;
  }
  async arrayBuffer() { return this.bytes.slice().buffer; }
}
const bytes = [103, 108, 84, 70, 1, 2, 3, 4];
const row = dex => ({
  dex, name: "#" + dex, path: "temporary-imports/" + String(dex).padStart(4, "0") + "/regular.glb",
  sha: sha("c"), bytes: 8, orientation: "0deg 0deg 0deg", idleAnimation: "idle",
  sourceGame: "sv", sourceModelId: dex, gfpakImport: true,
});
function mock() {
  const log = [];
  let head = sha("a");
  let manifest = { ...base, entries: [row(25)] };
  let pendingManifest = null;
  let serial = 0;
  const response = (status, data) => ({ ok: status >= 200 && status < 300,
    status, json: async () => data });
  const fetch = async (url, opts = {}) => {
    const method = opts.method || "GET";
    const payload = opts.body ? JSON.parse(opts.body) : null;
    log.push({ url, method, payload });
    if (url === "https://api.github.com/user") return response(200, { login: "Unborne-Fetus" });
    if (url === repo) return response(200, { permissions: { push: true } });
    if (method === "GET" && url === repo + "/git/ref/heads/main")
      return response(200, { object: { sha: head } });
    if (method === "GET" && url.startsWith(repo + "/git/commits/"))
      return response(200, { tree: { sha: sha("b") } });
    if (method === "GET" && url === repo + "/contents/temporary-imports/manifest.json?ref=main")
      return response(200, { content: Buffer.from(JSON.stringify(manifest)).toString("base64") });
    if (method === "POST" && url === repo + "/git/blobs") {
      if (payload.encoding === "utf-8" && payload.content.trimStart().startsWith("{")) {
        pendingManifest = JSON.parse(payload.content);
      }
      return response(201, { sha: sha(String((serial++ % 6) + 1)) });
    }
    if (method === "POST" && url === repo + "/git/trees")
      return response(201, { sha: sha("d") });
    if (method === "POST" && url === repo + "/git/commits")
      return response(201, { sha: sha("e") });
    if (method === "PATCH" && url === repo + "/git/refs/heads/main") {
      assert.equal(payload.force, false, "Never force-push an override");
      assert.ok(pendingManifest, "Never advance branch without a model catalog update");
      manifest = pendingManifest;
      pendingManifest = null;
      head = payload.sha;
      return response(200, { object: { sha: head } });
    }
    throw Error("Unexpected GitHub call " + method + " " + url);
  };
  const window = {
    POKEDEX3D_NAMES: {},
    POKEDEX3D_MODEL_IDENTITY: { verify: async () => true },
    POKEDEX3D_LOCAL_SWITCH: { inspectGlb: async () => ["idle", "run"] },
  };
  vm.runInNewContext(source, { window, fetch, File: FakeFile,
    Uint8Array, Uint8ClampedArray, TextDecoder, TextEncoder, URL,
    btoa: input => Buffer.from(input, "binary").toString("base64"),
    atob: input => Buffer.from(input, "base64").toString("binary"),
  }, { filename: "github-model-storage.js" });
  return { api: window.POKEDEX3D_GITHUB_STORAGE, log,
    get manifest() { return manifest; } };
}
const model = dex => ({
  dex, form: "regular", name: "#" + dex, file: new FakeFile(bytes),
  sourceGame: "sv", sourceModelId: dex, gfpakImport: true,
  orientation: "0deg 0deg 0deg", orientationVersion: 2, idleAnimation: "idle",
});
(async () => {
  const mockApi = mock();
  await assert.rejects(mockApi.api.publishModel(model(1)), /Connect GitHub/);
  await mockApi.api.connect(token);
  const before = mockApi.log.length;
  await assert.rejects(mockApi.api.publishModel(model(25)), /already published.*Override/);
  assert.equal(mockApi.log.filter(call => call.method === "PATCH").length, 0);
  assert.equal(mockApi.log.slice(before).filter(call =>
    call.url.endsWith("/git/blobs")).length, 0, "No duplicate should upload bytes");

  const result = await mockApi.api.publishModels([model(25), model(26)]);
  assert.equal(result.published.length, 1);
  assert.equal(result.skipped.length, 1);
  assert.equal(result.failed.length, 0);
  assert.deepEqual(mockApi.manifest.entries.map(entry => entry.dex), [25, 26]);

  const newModel = model(25);
  newModel.orientation = "0deg -90deg 0deg";
  newModel.idleAnimation = "run";
  const replaced = await mockApi.api.publishModel(newModel, { replaceExisting: true });
  assert.equal(replaced.dex, 25);
  assert.equal(mockApi.manifest.entries.length, 2);
  assert.equal(mockApi.manifest.entries.find(entry => entry.dex === 25).orientation,
    "0deg -90deg 0deg");
  assert.equal(mockApi.manifest.entries.find(entry => entry.dex === 25).idleAnimation, "run");

  const remote = { ...replaced, animations: ["idle", "run"], idleAnimation: "idle",
    orientation: "0deg 0deg 90deg" };
  const oldBlob = mockApi.manifest.entries.find(entry => entry.dex === 25).sha;
  const oldCalls = mockApi.log.length;
  const updated = await mockApi.api.saveModelSettings(remote);
  assert.equal(updated.idleAnimation, "idle");
  assert.equal(updated.orientation, "0deg 0deg 90deg");
  assert.equal(mockApi.manifest.entries.find(entry => entry.dex === 25).sha, oldBlob,
    "Settings must not replace the model GLB");
  assert.ok(!mockApi.log.slice(oldCalls).some(call =>
    call.url.endsWith("/git/blobs") && call.payload?.encoding === "base64"),
    "Settings save must not upload the model again");
  await assert.rejects(mockApi.api.saveModelSettings({
    ...remote, sourceBlobSha: sha("f"),
  }), /changed.*Refresh/);
  await assert.rejects(mockApi.api.saveModelSettings({
    ...remote, idleAnimation: "nonexistent",
  }), /playable default animation/);

  const invalid = model(27);
  invalid.idleAnimation = "nonexistent";
  await assert.rejects(mockApi.api.publishModel(invalid), /missing from the uploaded model/);
  assert.ok(mockApi.api.connected());
  mockApi.api.disconnect();
  await assert.rejects(mockApi.api.saveModelSettings(remote), /Connect GitHub/);
  console.log("GitHub bulk publish, overwrite, metadata-only and authorization tests passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
