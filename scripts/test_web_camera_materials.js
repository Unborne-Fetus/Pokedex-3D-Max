"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const path = require("node:path");

const app = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8");
const start = app.indexOf("function resetCamera()");
const end = app.indexOf("function populateFormSelect(", start);
assert.ok(start >= 0 && end > start, "Switch camera functions are missing");
const source = app.slice(start, end);

function frame(model = {}) {
  const viewer = {
    resetTurntableRotation(value) { this.turntable = value; },
    jumpCameraToGoal() { this.jumped = true; },
  };
  const context = {
    viewer, currentModel: model, Number, Math,
    clearTimeout, setTimeout,
    requestAnimationFrame: fn => fn(),
    cameraFitTimer: null,
  };
  vm.runInNewContext(source, context);
  context.resetCamera();
  return viewer;
}

// Model-viewer consumes roll, pitch, yaw, in that order. A +90deg pitch
// converts the Switch exports' -Z-up / +Y-front coordinates to +Y-up / +Z-front.
assert.match(html, /orientation="0deg 90deg 0deg"/);
assert.match(html, /camera-orbit="0deg 90deg 60%"/);

const normal = frame();
assert.equal(normal.cameraOrbit, "0deg 90deg 60%");
assert.equal(normal.cameraTarget, "auto auto auto");
assert.equal(normal.fieldOfView, "30deg");
assert.equal(normal.turntable, 0);
assert.ok(normal.jumped);

// Legacy arbitrary angles and fixed-metre zoom made Pokemons face up/down
// and caused clipping on both narrow and wide viewports.
assert.equal(frame({cameraAzimuth:90}).cameraOrbit, "90deg 90deg 60%");
assert.equal(frame({cameraAzimuth:0}).cameraOrbit, "0deg 90deg 60%");
assert.equal(frame({cameraAzimuth:null}).cameraOrbit, "0deg 90deg 60%");
assert.equal(frame({cameraAzimuth:"invalid"}).cameraOrbit, "0deg 90deg 60%");
assert.ok(!source.includes("getDimensions()"), "Default camera must use adaptive framing");
assert.ok(!app.includes("correctOpaqueBodyMaterials();"),
  "Do not destroy genuine Switch alpha cutouts");
assert.match(app, /startIdle\(\);\s*scheduleCameraFit\(\);/,
  "The idle pose must start before camera fitting");

console.log("Switch web viewer upright/front-facing and framing regression checks passed.");
