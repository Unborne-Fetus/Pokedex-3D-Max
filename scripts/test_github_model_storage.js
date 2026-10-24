"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../web/github-model-storage.js"), "utf8"
);
const target = "https://api.github.com/repos/Unborne-Fetus/Pokedex-3D-Models-Animations";
const credential = "github_pat_TEST_NEVER_REAL";

function mockSession({ push = true, writeStatus = 201 } = {}) {
  const calls = [];
  const response = (status, data) => ({
    ok: status >= 200 && status < 300, status, json: async () => data,
  });
  const fetch = async (url, options = {}) => {
    const method = options.method || "GET";
    calls.push({ url, method, body: options.body || null });
    if (url === "https://api.github.com/user")
      return response(200, { login: "Unborne-Fetus" });
    if (url === target)
      return response(200, { permissions: { push } });
    if (url === target + "/git/blobs" && method === "POST")
      return writeStatus === 201
        ? response(201, { sha: "a".repeat(40) })
        : response(writeStatus, { message: "Resource not accessible by personal access token" });
    throw Error("Unexpected request: " + method + " " + url);
  };
  const window = {};
  vm.runInNewContext(source, { window, fetch }, { filename: "github-model-storage.js" });
  return { storage: window.POKEDEX3D_GITHUB_STORAGE, calls };
}

(async () => {
  const forbidden = mockSession({ writeStatus: 403 });
  let denied;
  try {
    await forbidden.storage.connect(credential);
  } catch (error) {
    denied = error;
  }
  assert.ok(denied, "Write-denied token must fail on connect");
  assert.match(denied.message, /HTTP 403/);
  assert.match(denied.message, /Contents: Read and write/);
  assert.match(denied.message, /Pokedex-3D-Models-Animations/);
  assert.doesNotMatch(denied.message, /github_pat_TEST_NEVER_REAL/);
  assert.equal(forbidden.storage.connected(), false);
  assert.deepEqual(forbidden.calls.map(call => call.method), ["GET", "GET", "POST"]);
  assert.equal(forbidden.calls[2].url, target + "/git/blobs");
  assert.deepEqual(forbidden.calls.filter(call =>
    /\/git\/(?:refs|trees|commits)/.test(call.url)), [],
    "The preflight may create an unreferenced blob, never a commit or ref");

  const allowed = mockSession();
  assert.equal(await allowed.storage.connect(credential), "Unborne-Fetus");
  assert.equal(allowed.storage.connected(), true);
  allowed.storage.disconnect();
  assert.equal(allowed.storage.connected(), false);

  const noPush = mockSession({ push: false });
  await assert.rejects(noPush.storage.connect(credential), /Contents: Read and write/);
  assert.equal(noPush.calls.length, 2, "Do not probe write when GitHub reports no push access");

  console.log("GitHub model storage permission checks passed");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
