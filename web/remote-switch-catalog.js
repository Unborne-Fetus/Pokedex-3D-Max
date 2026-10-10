"use strict";

/* This is a STATIC public-GitHub asset index, not a proxy into a private repo.
   File inventory entries are unverified until their real GLB has been downloaded
   and inspected in the visitor's browser. Never include GitHub access tokens. */
(function () {
  const SOURCE = "https://raw.githubusercontent.com/Unborne-Fetus/Pokedex-3D-Models-Animations/main/";
  const MANIFEST = SOURCE + "uploaded-model-inventory.json";
  const CONFIG = "web/models/remote-source.json";
  const PATH = /^(?:switch\/)?(\d{4})\/regular\.glb$/;
  const IDLE = /default(?:idle|wait)|battle(?:idle|wait)|fight[_ -]?a|idle|wait|stand|breath|rest/i;
  const REJECT = /attack|damage|faint|death|down|hit|move|run|walk|jump|bind|t[-_ ]?pose/i;
  const decoder = new TextDecoder("utf-8");
  const defaults = {
    enabled: true,
    manifestUrl: MANIFEST,
    assetBaseUrl: SOURCE,
    allowUnverifiedInventory: true,
  };

  function prepare(config, manifest) {
    if (!config || config.enabled !== true || !config.manifestUrl) return [];
    if (!manifest || manifest.format !== 1 || !Array.isArray(manifest.entries)) {
      throw Error("Invalid original Switch model catalog");
    }
    const inventory = manifest.source === "github-model-file-inventory"
      || manifest.source === "private-Switch-model-repository-file-inventory";
    if (inventory && !config.allowUnverifiedInventory) return [];
    const manifestUrl = new URL(config.manifestUrl);
    if (manifestUrl.protocol !== "https:") throw Error("Catalog must use HTTPS");
    const base = config.assetBaseUrl ? new URL(config.assetBaseUrl) : new URL(".", manifestUrl);
    if (base.protocol !== "https:") throw Error("Model files must use HTTPS");
    const basePath = base.pathname.endsWith("/") ? base.pathname : base.pathname + "/";
    const seen = new Set();
    const results = [];
    for (const entry of manifest.entries) {
      if (!entry) continue;
      if (!inventory && (entry.ready !== true || entry.valid !== true)) continue;
      if (!inventory && String(entry.form || "") !== "regular") continue;
      const match = String(entry.path || "").match(PATH);
      if (!match || Number(entry.dex) !== Number(match[1])) continue;
      // The upload paths are historical storage slots, not evidence of
      // species identity. ZA, just like SV, retains SwSh's internal IDs:
      // /0964/ can therefore contain Clobbopus, not Palafin.
      const recordedDex = Number(entry.dex);
      const sourceId = Number(entry.sourceModelId);
      const sourceGame = String(entry.sourceGame || "");
      const recognized = /^(?:sv|swsh|la|za)(?:-|$)/i.test(sourceGame);
      const dex = recognized && Number.isInteger(sourceId) && sourceId > 0
        ? window.POKEDEX3D_MODEL_IDENTITY.nationalDex(sourceId, sourceGame)
        : recordedDex;
      if (!Number.isInteger(dex) || dex < 1 || dex > 1025 || seen.has(dex)) continue;
      const clips = Array.isArray(entry.animations) ? entry.animations : [];
      const idle = String(entry.idleAnimation || "");
      if (!inventory && (!idle || !clips.includes(idle))) continue;
      const url = new URL(entry.path, base);
      // GitHub raw/CDN caches otherwise continue serving a previously
      // misnumbered model after the files are corrected in the repository.
      const revision = String(entry.sha256 || entry.sha || entry.bytes || "");
      if (revision) url.searchParams.set("rev", revision);
      if (url.protocol !== "https:" || url.origin !== base.origin
          || !url.pathname.startsWith(basePath)) continue;
      seen.add(dex);
      results.push({
        dex, originalCatalogDex: recordedDex,
        form: "regular", name: window.POKEDEX3D_NAMES?.[dex]
          || "#" + String(dex).padStart(4, "0"),
        url: url.href, remoteSwitch: true, ready: true, valid: true,
        // An inventory is NOT evidence of texture correctness or animations.
        preflightRequired: inventory,
        // Use the uploaded file revision to restore only matching animation checks.
        assetRevision: revision,
        sourceBlobSha: String(entry.sourceBlobSha || entry.sha || ""),
        sourceGame: entry.sourceGame || null,
        sourceModelId: Number(entry.sourceModelId || 0) || null,
        idleAnimation: inventory ? null : idle,
        idleBreaks: inventory ? [] : (Array.isArray(entry.idleBreaks) ? entry.idleBreaks : [])
          .filter(name => name !== idle && clips.includes(name)),
      });
    }
    return results.sort((a, b) => a.dex - b.dex);
  }

  // Blender often exports a legitimate Switch idle as just "Animation".
  // A generic name is accepted ONLY for a sole skeletal clip that actually
  // moves multiple skinned joints over time. A collection of static keyframes
  // must not be mistaken for an animated model.
  function hasMovingSkinnedJoints(doc, data, jsonLength, clip) {
    const joints = new Set((Array.isArray(doc.skins) ? doc.skins : [])
      .flatMap(skin => Array.isArray(skin.joints) ? skin.joints : []));
    const accessors = Array.isArray(doc.accessors) ? doc.accessors : [];
    const buffers = Array.isArray(doc.bufferViews) ? doc.bufferViews : [];
    if (joints.size < 3 || !Array.isArray(clip.channels) ||
        !Array.isArray(clip.samplers)) return false;
    const chunkStart = 20 + jsonLength;
    const view = new DataView(data);
    if (chunkStart + 8 > data.byteLength ||
        view.getUint32(chunkStart + 4, true) !== 0x004e4942) return false;
    const binLength = view.getUint32(chunkStart, true);
    const binStart = chunkStart + 8;
    if (binStart + binLength > data.byteLength) return false;
    const movingJoints = new Set();
    let maxDuration = 0;

    for (const channel of clip.channels) {
      const target = channel?.target;
      if (!target || !joints.has(target.node) ||
          !["rotation", "translation", "scale"].includes(target.path)) continue;
      const sampler = clip.samplers[channel.sampler];
      const input = accessors[sampler?.input];
      const output = accessors[sampler?.output];
      const range = input?.max?.[0] - input?.min?.[0];
      if (Number.isFinite(range)) maxDuration = Math.max(maxDuration, range);
      const dimensions = { VEC3: 3, VEC4: 4 }[output?.type];
      if (!dimensions || output.componentType !== 5126 ||
          !Number.isInteger(output.count) || output.count < 2 ||
          output.count > 15000) continue;
      const buffer = buffers[output.bufferView];
      if (!buffer || buffer.buffer !== 0) continue;
      const stride = buffer.byteStride || dimensions * 4;
      const offset = (buffer.byteOffset || 0) + (output.byteOffset || 0);
      const last = offset + stride * (output.count - 1) + dimensions * 4;
      if (stride < dimensions * 4 || offset < 0 ||
          last > (buffer.byteOffset || 0) + buffer.byteLength ||
          last > binLength) continue;
      const start = binStart + offset;
      let moves = false;
      for (let key = 1; key < output.count && !moves; key++) {
        for (let component = 0; component < dimensions; component++) {
          const initial = view.getFloat32(start + component * 4, true);
          const later = view.getFloat32(start + key * stride + component * 4, true);
          if (Number.isFinite(initial) && Number.isFinite(later) &&
              Math.abs(later - initial) > 0.00001) {
            moves = true;
            break;
          }
        }
      }
      if (moves) {
        movingJoints.add(target.node);
        if (movingJoints.size >= 3 && maxDuration >= 0.25) return true;
      }
    }
    return movingJoints.size >= 3 && maxDuration >= 0.25;
  }

  function inspect(data) {
    if (!(data instanceof ArrayBuffer) || data.byteLength < 32) {
      throw Error("Downloaded model is empty or not a GLB");
    }
    const header = new DataView(data, 0, 20);
    if (header.getUint32(0, true) !== 0x46546c67
      || header.getUint32(4, true) !== 2
      || header.getUint32(8, true) !== data.byteLength
      || header.getUint32(16, true) !== 0x4e4f534a) {
      throw Error("Invalid GLB header");
    }
    const size = header.getUint32(12, true);
    if (size < 2 || size > data.byteLength - 20 || size > 24 * 1024 * 1024) {
      throw Error("Invalid GLB material/animation metadata");
    }
    let doc;
    try {
      doc = JSON.parse(decoder.decode(new Uint8Array(data, 20, size)));
    } catch (_) {
      throw Error("Corrupted GLB metadata");
    }
    if (!Array.isArray(doc.meshes) || !doc.meshes.length ||
        !Array.isArray(doc.scenes) || !doc.scenes.length ||
        !Array.isArray(doc.materials) || !doc.materials.length) {
      throw Error("Missing Switch model mesh or materials");
    }
    const textures = Array.isArray(doc.textures) ? doc.textures : [];
    const images = Array.isArray(doc.images) ? doc.images : [];
    for (const mat of doc.materials) {
      const tex = mat?.pbrMetallicRoughness?.baseColorTexture?.index;
      if (!Number.isInteger(tex) || tex < 0 || tex >= textures.length) {
        throw Error("Model has an untextured material");
      }
      const source = textures[tex]?.source;
      if (!Number.isInteger(source) || source < 0 || source >= images.length) {
        throw Error("Model base-color image is missing");
      }
      const image = images[source];
      if (!Number.isInteger(image?.bufferView) &&
          !String(image?.uri || "").startsWith("data:")) {
        throw Error("Model texture is not embedded");
      }
    }
    const validClips = (Array.isArray(doc.animations) ? doc.animations : [])
      .map((clip, index) => ({ clip, name: clip?.name || "animation_" + index }))
      .filter(({ clip }) => Array.isArray(clip?.channels) && clip.channels.length &&
                            Array.isArray(clip?.samplers) && clip.samplers.length);
    const animations = validClips.map(item => item.name);
    let idleAnimation = animations.find(name => IDLE.test(name) && !REJECT.test(name));
    if (!idleAnimation && validClips.length === 1 &&
        /^Animation(?:[. _-]\d+)?$/i.test(validClips[0].name) &&
        hasMovingSkinnedJoints(doc, data, size, validClips[0].clip)) {
      // The importer flattened the original idle name to "Animation", but
      // this GLB contains a real, non-static multi-joint skeletal animation.
      idleAnimation = validClips[0].name;
    }
    if (!idleAnimation) {
      throw Error("No supported moving idle clip was found in this GLB");
    }
    return { idleAnimation, animations };
  }

  function publish(models) {
    if (models.length) {
      window.dispatchEvent(new CustomEvent("pokedex3d:remote-switch-catalog", {
        detail: { models },
      }));
    }
  }

  async function load() {
    let config = defaults;
    if (location.protocol !== "file:") {
      try {
        const reply = await fetch(CONFIG, { cache: "no-store" });
        if (reply.ok) {
          const saved = await reply.json();
          if (saved?.enabled === true) config = { ...defaults, ...saved };
          else if (saved?.enabled === false) return;
        }
      } catch (_) { /* Embedded public inventory still works offline. */ }
    }
    if (!config.enabled) return;
    const snapshot = window.POKEDEX3D_PUBLIC_INVENTORY;
    if (snapshot) {
      try { publish(prepare(config, snapshot)); } catch (_) { /* Fetch live catalog below. */ }
    }
    // Use current public GitHub inventory when online; bundled snapshot works
    // if the API/CDN is unavailable. No GitHub Actions, API token, or billing.
    try {
      const response = await fetch(config.manifestUrl, { mode: "cors", cache: "no-store" });
      if (!response.ok) throw Error("GitHub model inventory is temporarily unavailable");
      const live = prepare(config, await response.json());
      if (!live.length) throw Error("Public repository inventory is empty");
      // An existing GLB may change without changing the total model count.
      const snapshotEntries = new Map(
        (snapshot?.entries || []).map(entry => [Number(entry.dex), entry]));
      const changed = !snapshot || live.length !== snapshot.entries.length ||
        live.some(model => {
          const original = snapshotEntries.get(model.dex);
          return !original || model.assetRevision !==
            String(original.sha256 || original.sha || original.bytes || "");
        });
      if (changed) publish(live);
    } catch (error) {
      if (!snapshot) {
        window.dispatchEvent(new CustomEvent("pokedex3d:remote-switch-error", {
          detail: { message: String(error.message || error) },
        }));
      }
    }
  }

  // Expose the bundled inventory synchronously. The app must not show
  // committed GLBs as missing while waiting for an asynchronous catalog event.
  function bundled() {
    const snapshot = window.POKEDEX3D_PUBLIC_INVENTORY;
    if (!snapshot) return [];
    try { return prepare(defaults, snapshot); }
    catch (_) { return []; }
  }

  window.POKEDEX3D_REMOTE_SWITCH = Object.freeze({ prepare, inspect, bundled });
  // Defer catalog notifications until the main viewer has registered handlers.
  if (typeof document !== "undefined" && document.readyState !== "complete") {
    document.addEventListener("DOMContentLoaded", load, { once: true });
  } else {
    setTimeout(load, 0);
  }
})();
