"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const path = require("node:path");

const app = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
const start = app.indexOf("function resetCamera()");
const end = app.indexOf("function populateFormSelect(", start);
assert.ok(start >= 0 && end > start, "Switch camera/material functions are missing");
const source = app.slice(start, end);

function frame(bounds, center, width, height, materials = [], model = {}) {
  const viewer = {
    clientWidth: width, clientHeight: height,
    getDimensions: () => bounds,
    getBoundingBoxCenter: () => center,
    model: { materials },
    jumpCameraToGoal() { this.jumped = true; },
  };
  const context = { viewer, currentModel: model, Number, Math };
  vm.runInNewContext(source, context);
  context.resetCamera();
  return { viewer, corrected: context.correctOpaqueBodyMaterials() };
}
const body = { name: "body_a", mode: "BLEND",
  getAlphaMode() { return this.mode; },
  setAlphaMode(value) { this.mode = value; },
};
const eye = { name: "l_eye", mode: "BLEND",
  getAlphaMode() { return this.mode; },
  setAlphaMode(value) { this.mode = value; },
};
const flame = { name: "fire", mode: "BLEND",
  getAlphaMode() { return this.mode; },
  setAlphaMode(value) { this.mode = value; },
};

const small = frame({ x: 0.6, y: 1.1, z: 0.8 },
                    { x: 0, y: 0, z: -0.5 }, 900, 600,
                    [body, eye, flame]);
assert.ok(small.viewer.cameraOrbit.startsWith("165deg 76deg"));
assert.equal(small.viewer.cameraTarget, "0.0000m 0.0000m -0.5000m");
assert.equal(small.viewer.fieldOfView, "32deg");
assert.equal(small.corrected, 1);
assert.equal(body.mode, "OPAQUE");
assert.equal(eye.mode, "BLEND");
assert.equal(flame.mode, "BLEND");

const giant = frame({ x: 5.0, y: 5.4, z: 1.8 },
                    { x: 1, y: -1.5, z: -2 }, 480, 600);
const near = Number(small.viewer.cameraOrbit.split(" ")[2].replace("m", ""));
const far = Number(giant.viewer.cameraOrbit.split(" ")[2].replace("m", ""));
assert.ok(far > near * 4, "Larger Pokemon must be framed farther away");
assert.equal(giant.viewer.cameraTarget, "1.0000m -1.5000m -2.0000m");

const broken = frame({ x: NaN, y: 1, z: 1 },
                     { x: 0, y: 0, z: 0 }, 900, 600);
assert.ok(broken.viewer.cameraOrbit.endsWith("130%"));
assert.ok(broken.viewer.jumped);

console.log("Switch web viewer camera/material regression checks passed.");
