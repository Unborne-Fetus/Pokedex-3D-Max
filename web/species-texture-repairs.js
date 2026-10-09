// Corrections to the four verified Switch GLBs that need manual palette fixes.
// This operates on copies of their embedded textures at load time; no changes
// to joint hierarchies, mesh geometry, or animation channels.
(() => {
  "use strict";
  const u32 = (view, at) => view.getUint32(at, true);
  const align4 = value => (value + 3) & ~3;

  async function drawTexture(glb, doc, binStart, imageIndex, painter) {
    const image = doc.images?.[imageIndex];
    const section = doc.bufferViews?.[image?.bufferView];
    if (!section || !image?.mimeType?.startsWith("image/")) return null;
    const imageBytes = glb.slice(
      binStart + (section.byteOffset || 0),
      binStart + (section.byteOffset || 0) + section.byteLength);
    const blob = new Blob([imageBytes], { type: image.mimeType });
    let source;
    if (typeof createImageBitmap === "function") {
      source = await createImageBitmap(blob);
    } else {
      const url = URL.createObjectURL(blob);
      try {
        source = await new Promise((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve(img);
          img.onerror = reject;
          img.src = url;
        });
      } finally { URL.revokeObjectURL(url); }
    }
    const canvas = document.createElement("canvas");
    canvas.width = source.width;
    canvas.height = source.height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw Error("Canvas context is unavailable");
    context.drawImage(source, 0, 0);
    source.close?.();
    await painter(context, canvas.width, canvas.height);
    const output = await new Promise((resolve, reject) =>
      canvas.toBlob(blob => blob ? resolve(blob) : reject(Error("Texture encode failed")), "image/png"));
    return new Uint8Array(await output.arrayBuffer());
  }

  // A small bright highlight in the original iris/pupil rather than replacing
  // the whole eye material with a flat color.
  function shineEye(ctx, width, height, kind) {
    const sx = width / 128, sy = height / 128;
    ctx.save();
    const spots = kind === "squirtle"
      ? [[62, 51, 5.3, 8.0], [69, 71, 2.3, 3.2]]
      : [[53, 41, 5.6, 8.2], [70, 69, 2.0, 2.8]];
    ctx.fillStyle = "#ffffff";
    for (const [x, y, rx, ry] of spots) {
      ctx.beginPath();
      ctx.ellipse(x * sx, y * sy, rx * sx, ry * sy, -0.25, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // The exported Wartortle appendage palette contains a neutral gray mask.
  // Its old replacement used the red-marked body atlas; recolor the neutral
  // mask light blue instead, retaining the existing blue details and ink.
  function blueWartortleAppendages(ctx, width, height) {
    const image = ctx.getImageData(0, 0, width, height);
    const p = image.data;
    for (let i = 0; i < p.length; i += 4) {
      const r = p[i], g = p[i + 1], b = p[i + 2];
      const max = Math.max(r, g, b), min = Math.min(r, g, b);
      if (r > 150 && max - min < 27) {
        const shade = (r + g + b) / (3 * 205);
        p[i] = Math.min(255, 170 * shade);
        p[i + 1] = Math.min(255, 208 * shade);
        p[i + 2] = Math.min(255, 232 * shade);
      }
    }
    ctx.putImageData(image, 0, 0);
  }

  // Charizard's inner-wing blue exists in the source atlas, but its edge
  // padding is orange. Expand the blue membrane a few texels to remove
  // orange seams without recoloring the orange outer wing/body.
  function repairCharizardAtlas(ctx, width, height) {
    const image = ctx.getImageData(0, 0, width, height);
    const source = new Uint8ClampedArray(image.data);
    const pixels = image.data;
    const sx = width / 1024, sy = height / 1024;
    const radius = Math.max(1, Math.round(11 * Math.min(sx, sy)));
    const xStart = Math.max(0, Math.floor(45 * sx));
    const xStop = Math.min(width, Math.ceil(977 * sx));
    const yStart = Math.max(0, Math.floor(342 * sy));
    const yStop = Math.min(height, Math.ceil(980 * sy));
    function blue(at) {
      return source[at + 2] > source[at] * 1.4 &&
        source[at + 2] > source[at + 1] * 1.10 &&
        source[at + 2] > 65 && source[at + 3] > 0;
    }
    for (let y = yStart; y < yStop; y++) {
      for (let x = xStart; x < xStop; x++) {
        if (x > width * 0.46 && x < width * 0.56) continue;
        const idx = (y * width + x) * 4;
        if (blue(idx)) continue;
        if (source[idx] < 140 || source[idx + 1] < 80 ||
            source[idx + 2] > 150) continue;
        let match = -1;
        for (let step = 1; step <= radius && match < 0; step++) {
          for (const [dx, dy] of [[step, 0], [-step, 0], [0, step], [0, -step]]) {
            const nx = x + dx, ny = y + dy;
            if (nx >= 0 && nx < width && ny >= 0 && ny < height) {
              const at = (ny * width + nx) * 4;
              if (blue(at)) { match = at; break; }
            }
          }
        }
        if (match >= 0) {
          pixels[idx] = source[match];
          pixels[idx + 1] = source[match + 1];
          pixels[idx + 2] = source[match + 2];
        }
      }
    }
    // Recolor the orange mouth interior beneath the pink tongue. Keep
    // the tongue itself pink and the blue membrane fully unchanged.
    for (let y = Math.floor(804 * sy); y < Math.min(height, Math.ceil(987 * sy)); y++) {
      for (let x = Math.floor(427 * sx); x < Math.min(width, Math.ceil(603 * sx)); x++) {
        const dx = (x / sx - 515) / 88;
        const dy = (y / sy - 894) / 97;
        if (dx * dx + dy * dy >= 1) continue;
        const i = (y * width + x) * 4;
        const r = source[i], g = source[i + 1], b = source[i + 2];
        // Exclude the existing rosy tongue colors and dark outlines.
        if (r > 140 && g > 95 && b < 115 && g > b * 1.15) {
          pixels[i] = Math.round(r * 0.57);
          pixels[i + 1] = Math.round(g * 0.20);
          pixels[i + 2] = Math.round(Math.max(39, b * 0.72));
        }
      }
    }
    ctx.putImageData(image, 0, 0);
  }

  function material(doc, name) {
    return doc.materials?.find(item => item.name === name);
  }
  function setTexture(doc, name, index) {
    const entry = material(doc, name);
    if (entry?.pbrMetallicRoughness?.baseColorTexture)
      entry.pbrMetallicRoughness.baseColorTexture.index = index;
  }

  async function apply(buffer, dex) {
    if (![4, 6, 7, 8].includes(dex)) return buffer;
    try {
      const bytes = new Uint8Array(buffer);
      const head = new DataView(buffer);
      if (u32(head, 0) !== 0x46546c67 || u32(head, 16) !== 0x4e4f534a)
        return buffer;
      const jsonLength = u32(head, 12);
      const binHeader = 20 + jsonLength;
      if (u32(head, binHeader + 4) !== 0x004e4942) return buffer;
      const oldBinLength = u32(head, binHeader);
      const binStart = binHeader + 8;
      const doc = JSON.parse(new TextDecoder().decode(bytes.subarray(20, binHeader)));
      const changes = [];
      if (dex === 4) {
        changes.push([1, (ctx, w, h) => shineEye(ctx, w, h, "charmander")]);
      } else if (dex === 6) {
        changes.push([1, repairCharizardAtlas]);
      } else if (dex === 7) {
        // body_b_01 is Squirtle's tail, not its belly. Undo the old swap.
        setTexture(doc, "body_b_01", 1);
        changes.push([2, (ctx, w, h) => shineEye(ctx, w, h, "squirtle")]);
      } else if (dex === 8) {
        // Preserve the correct blue appendage UV atlas; remove the red patch.
        setTexture(doc, "body_b_02", 1);
        setTexture(doc, "body_b_00", 5);
        changes.push([1, blueWartortleAppendages]);
        // Main back shell, separate from the detailed beige front.
        const back = material(doc, "body_b_01");
        if (back?.pbrMetallicRoughness)
          back.pbrMetallicRoughness.baseColorFactor = [0.77, 0.61, 0.44, 1];
      }
      let newBinSize = oldBinLength;
      const extra = [];
      for (const [imageIndex, painter] of changes) {
        const png = await drawTexture(bytes, doc, binStart, imageIndex, painter);
        if (!png) continue;
        const offset = align4(newBinSize);
        extra.push({ offset, png });
        const newView = doc.bufferViews.push({
          buffer: 0, byteOffset: offset, byteLength: png.byteLength,
        }) - 1;
        doc.images[imageIndex].bufferView = newView;
        doc.images[imageIndex].mimeType = "image/png";
        newBinSize = offset + png.byteLength;
      }
      const paddedBin = align4(newBinSize);
      doc.buffers[0].byteLength = paddedBin;
      const encoded = new TextEncoder().encode(JSON.stringify(doc));
      const paddedJSON = align4(encoded.length);
      const binPayload = new Uint8Array(paddedBin);
      binPayload.set(bytes.subarray(binStart, binStart + oldBinLength));
      for (const { offset, png } of extra) binPayload.set(png, offset);
      const output = new ArrayBuffer(12 + 8 + paddedJSON + 8 + paddedBin);
      const view = new DataView(output);
      view.setUint32(0, 0x46546c67, true);
      view.setUint32(4, 2, true);
      view.setUint32(8, output.byteLength, true);
      view.setUint32(12, paddedJSON, true);
      view.setUint32(16, 0x4e4f534a, true);
      const target = new Uint8Array(output);
      target.fill(0x20, 20, 20 + paddedJSON);
      target.set(encoded, 20);
      const next = 20 + paddedJSON;
      view.setUint32(next, paddedBin, true);
      view.setUint32(next + 4, 0x004e4942, true);
      target.set(binPayload, next + 8);
      return output;
    } catch (error) {
      console.warn("Species texture correction was skipped:", dex, error);
      return buffer; // A malformed correction must never prevent model loading.
    }
  }

  window.POKEDEX3D_REPAIR_SWITCH_MODEL = apply;
})();
