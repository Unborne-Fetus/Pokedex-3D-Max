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
      : kind === "wartortle"
        ? [[61, 48, 4.2, 6.0], [69, 65, 1.7, 2.2]]
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

  // Switch exports retained negative V coordinates on secondary atlases.
  // CLAMP_TO_EDGE turned those whole regions into the topmost texture row,
  // making blue wing membranes orange and shell palettes monochrome.
  // Keep their original UVs and textures: translate V into the atlas.
  function offsetTextureV(doc, name, amount = 1) {
    const tex = material(doc, name)?.pbrMetallicRoughness?.baseColorTexture;
    if (!tex) return;
    const extension = tex.extensions || (tex.extensions = {});
    const transform = extension.KHR_texture_transform ||
      (extension.KHR_texture_transform = {});
    const previous = transform.offset || [0, 0];
    transform.offset = [previous[0], amount];
    const extensionsUsed = doc.extensionsUsed || (doc.extensionsUsed = []);
    if (!extensionsUsed.includes("KHR_texture_transform"))
      extensionsUsed.push("KHR_texture_transform");
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
    if (![4, 6, 7, 8, 9].includes(dex)) return buffer;
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
        // The original atlas already has blue inner wings and pink mouth parts.
        // These were invisible because the body_b UVs were negative and clamped.
        offsetTextureV(doc, "body_b", 1);
        offsetTextureV(doc, "fire", 2);
      } else if (dex === 7) {
        // The original shell atlas contains the beige patterned plastron AND
        // brown carapace. No shell/tail palette should be exchanged.
        setTexture(doc, "body_b_01", 1); // tail, NOT the belly
        setTexture(doc, "body_b_00", 4); // shell
        offsetTextureV(doc, "body_b_01", 1);
        offsetTextureV(doc, "body_b_00", 1);
        changes.push([2, (ctx, w, h) => shineEye(ctx, w, h, "squirtle")]);
      } else if (dex === 8) {
        // Blue appendages have their own image; the beige patterned front
        // and dark-brown back are two different shell primitives.
        setTexture(doc, "body_b_02", 1);
        setTexture(doc, "body_b_00", 5);
        setTexture(doc, "body_b_01", 5);
        offsetTextureV(doc, "body_b_02", 1);
        offsetTextureV(doc, "body_b_00", 1);
        offsetTextureV(doc, "body_b_01", 1);
        const rearShell = material(doc, "body_b_00");
        const frontShell = material(doc, "body_b_01");
        if (rearShell?.pbrMetallicRoughness)
          rearShell.pbrMetallicRoughness.baseColorFactor = [0.52, 0.35, 0.24, 1];
        if (frontShell?.pbrMetallicRoughness)
          frontShell.pbrMetallicRoughness.baseColorFactor = [1, 1, 1, 1];
        changes.push([1, blueWartortleAppendages]);
        changes.push([2, (ctx, w, h) => shineEye(ctx, w, h, "wartortle")]);
      }
      if (dex === 9) {
        // The body_a atlas already contains the beige plastron. Its UVs
        // run from V=-1..0; CLAMP_TO_EDGE samples the blue top row and
        // paints the belly blue. Shift into the original atlas instead.
        // The separate shell/cannon UVs run from V=-2..-1.
        offsetTextureV(doc, "body_a", 1);
        offsetTextureV(doc, "body_b_00", 2);
        offsetTextureV(doc, "body_b_01", 2);
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
