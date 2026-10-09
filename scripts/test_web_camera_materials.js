"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const path = require("node:path");

const app = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8");
const start = app.indexOf("function computeCameraFrame(");
const end = app.indexOf("// Do not override legacy body-material", start);
assert.ok(start >= 0 && end > start, "Adaptive camera functions are missing");
const source = app.slice(start, end);
const center = {x: 0, y: 0, z: 0};

function fixture(dimensions, width = 1000, height = 500, model = {}) {
  const viewer = {
    loaded: true,
    clientWidth: width, clientHeight: height,
    getDimensions() { return dimensions; },
    getBoundingBoxCenter() { return center; },
    jumpCameraToGoal() { this.jumped = true; },
    resetTurntableRotation(value) { this.turntable = value; },
    async updateFraming() { this.reframed = true; },
  };
  const context = {viewer, currentModel: model, loadSequence: 5, Number, Math};
  vm.runInNewContext(source, context);
  return {viewer, context};
}

assert.match(html, /orientation="0deg 90deg 0deg"/,
  "Retain verified Switch front-facing axis");
assert.match(html, /camera-orbit="0deg 90deg 70%"/,
  "Initial placeholder angle remains face-on");

const regular = fixture({x: 0.8, y: 1.1, z: 0.6});
regular.context.resetCamera();
assert.match(regular.viewer.cameraOrbit, /^0deg 90deg [\d.]+m$/,
  "Each Pokémon must get a measured meter-based camera distance");
assert.equal(regular.viewer.fieldOfView, "30deg");
assert.equal(regular.viewer.turntable, 0);
assert.ok(regular.viewer.jumped);
assert.ok(regular.viewer.cameraTarget.includes("0.0385m"),
  "Camera target should shift a model slightly downward on screen");

function distance(v) {
  return Number(v.cameraOrbit.split(" ")[2].replace("m", ""));
}
const tall = fixture({x: 1, y: 5, z: 1});
tall.context.resetCamera();
assert.ok(distance(tall.viewer) > distance(regular.viewer) * 3,
  "Tall Pokémon must fit without cutting off their head or feet");

const wide = fixture({x: 3, y: 1, z: 1}, 1200, 600);
wide.context.resetCamera();
const narrowViewport = fixture({x: 3, y: 1, z: 1}, 320, 600);
narrowViewport.context.resetCamera();
assert.ok(distance(narrowViewport.viewer) > distance(wide.viewer),
  "Wide Pokémon must zoom out on narrow/mobile viewports");

const lower = fixture({x: 1, y: 1, z: 1}, 1200, 600,
  {cameraTargetYOffset: 0.12, cameraDistanceScale: 1.3});
lower.context.resetCamera();
const plain = fixture({x: 1, y: 1, z: 1}, 1200, 600);
plain.context.resetCamera();
assert.ok(distance(lower.viewer) > distance(plain.viewer),
  "Per-Pokémon override must adjust distance without altering others");
const lowerTargetY = Number(lower.viewer.cameraTarget.split(" ")[1].replace("m", ""));
const plainTargetY = Number(plain.viewer.cameraTarget.split(" ")[1].replace("m", ""));
assert.ok(lowerTargetY > plainTargetY,
  "Higher camera target must lower an unusually tall-on-screen Pokémon");

const unavailable = fixture({x: NaN, y: 1, z: 1});
unavailable.context.resetCamera();
assert.equal(unavailable.viewer.cameraOrbit, "0deg 90deg 60%",
  "A missing bounding box should use a safe fallback");

assert.ok(!app.includes("correctOpaqueBodyMaterials();"),
  "Do not destroy genuine Switch alpha cutouts");
assert.match(app, /startIdle\(\);\s*scheduleCameraFit\(\);/,
  "Wait for the idle pose before measuring the Pokémon");
assert.match(app, /await viewer\.updateFraming\?\.\(\)/,
  "Wait for asynchronous model-viewer framing to finish");
assert.match(app, /sequence === loadSequence/,
  "Ignore late framing callbacks from the previous Pokémon");
console.log("Adaptive per-Pokémon Switch camera regression checks passed.");
