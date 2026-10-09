'use strict';

/* Static-browser Switch GLB catalog. No server, installer, or upload required:
   files stay on the visitor's device, and glTF JSON is validated locally. */
(function () {
  const REGULAR_SWITCH_GLB = /(?:^|\/)switch\/(\d{4})\/regular\.glb$/i;
  const IDLE = /idle|wait|stand|breath|rest|fight[_ -]?a/i;
  const NOT_IDLE = /attack|damage|faint|death|down|bind|t[-_ ]?pose/i;
  const textDecoder = new TextDecoder('utf-8');

  async function inspectGlb(file) {
    if (file.size < 32) return null;
    const header = new DataView(await file.slice(0, 20).arrayBuffer());
    if (header.getUint32(0, true) !== 0x46546c67 ||
        header.getUint32(4, true) !== 2 ||
        header.getUint32(8, true) !== file.size ||
        header.getUint32(16, true) !== 0x4e4f534a) return null;
    const length = header.getUint32(12, true);
    if (!length || length > file.size - 20 || length > 24 * 1024 * 1024) return null;

    let doc;
    try {
      doc = JSON.parse(textDecoder.decode(await file.slice(20, 20 + length).arrayBuffer()));
    } catch (_) {
      return null;
    }
    if (!Array.isArray(doc.meshes) || !doc.meshes.length || !Array.isArray(doc.scenes) ||
        !doc.scenes.length || !Array.isArray(doc.materials) || !doc.materials.length) return null;
    const textures = Array.isArray(doc.textures) ? doc.textures : [];
    if (!doc.materials.every(material => {
      const index = material?.pbrMetallicRoughness?.baseColorTexture?.index;
      return Number.isInteger(index) && index >= 0 && index < textures.length;
    })) return null;
    const clips = (Array.isArray(doc.animations) ? doc.animations : [])
      .filter(anim => anim && Array.isArray(anim.channels) && anim.channels.length &&
                      Array.isArray(anim.samplers) && anim.samplers.length)
      .map((anim, index) => anim.name || 'animation_' + index);
    return clips.length ? clips : null;
  }

  async function fromFiles(files, onProgress) {
    const picked = Array.from(files || []);
    const modelFiles = picked.map(file => {
      const path = String(file.webkitRelativePath || file.name).replaceAll('\\', '/');
      const match = path.match(REGULAR_SWITCH_GLB);
      const dex = match ? Number(match[1]) : 0;
      return { file, dex };
    }).filter(item => item.dex >= 1 && item.dex <= 1025);
    const metaFile = picked.find(file => /(?:^|\/)switch-model-metadata\.json$/i.test(
      String(file.webkitRelativePath || file.name).replaceAll('\\', '/')
    )) || picked.find(file => /(?:^|\/)switch-manifest\.json$/i.test(
      String(file.webkitRelativePath || file.name).replaceAll('\\', '/')
    ));
    let metadata = new Map();
    if (metaFile) {
      try {
        const entries = JSON.parse(await metaFile.text());
        if (Array.isArray(entries)) {
          metadata = new Map(entries
            .filter(e => e && Number.isInteger(Number(e.dex)) && String(e.form) === 'regular')
            .map(e => [Number(e.dex), e]));
        }
      } catch (_) { /* The GLB itself still must pass all checks. */ }
    }

    const models = [];
    const seen = new Set();
    for (let index = 0; index < modelFiles.length; index++) {
      const { file, dex } = modelFiles[index];
      if (seen.has(dex)) continue;
      const clips = await inspectGlb(file);
      if (clips) {
        const saved = metadata.get(dex);
        const idle = clips.includes(saved?.idleAnimation)
          ? saved.idleAnimation
          : clips.find(name => IDLE.test(name) && !NOT_IDLE.test(name));
        if (idle) {
          seen.add(dex);
          models.push({
            dex,
            name: window.POKEDEX3D_NAMES?.[dex] || saved?.name || '#' + String(dex).padStart(4, '0'),
            form: 'regular',
            url: 'web/models/switch/' + String(dex).padStart(4, '0') + '/regular.glb',
            file,
            valid: true,
            ready: true,
            idleAnimation: idle,
            animations: clips,
            idleBreaks: (Array.isArray(saved?.idleBreaks) ? saved.idleBreaks : [])
              .filter(name => clips.includes(name) && name !== idle),
          });
        }
      }
      if (index % 25 === 0 || index === modelFiles.length - 1) {
        onProgress?.(index + 1, modelFiles.length, models.length);
        // Yield periodically to keep the browser responsive for large collections.
        await new Promise(resolve => setTimeout(resolve, 0));
      }
    }
    models.sort((a, b) => a.dex - b.dex);
    return { models, scanned: modelFiles.length };
  }

  function buildManifest(models) {
    const rows = [];
    const used = new Set();
    for (const model of models || []) {
      const dex = Number(model?.dex);
      if (!Number.isInteger(dex) || dex < 1 || dex > 1025 ||
          String(model.form) !== "regular" || !model.file || used.has(dex)) continue;
      const animations = Array.isArray(model.animations) ? model.animations : [];
      if (!animations.includes(model.idleAnimation)) continue;
      used.add(dex);
      rows.push({
        dex, name: String(model.name || ""), form: "regular",
        path: String(dex).padStart(4, "0") + "/regular.glb",
        bytes: model.file.size,
        animations,
        idleAnimation: model.idleAnimation,
        idleBreaks: Array.isArray(model.idleBreaks) ? model.idleBreaks : [],
        ready: true, valid: true
      });
    }
    rows.sort((a, b) => a.dex - b.dex);
    return {
      format: 1,
      source: "browser-validated-local-switch-models",
      models: rows.length,
      validation: "GLB header, mesh/material base-color binding, animation and idle metadata only; appearance and redistribution rights not verified",
      entries: rows
    };
  }

  window.POKEDEX3D_LOCAL_SWITCH = Object.freeze({ fromFiles, buildManifest });
})();
