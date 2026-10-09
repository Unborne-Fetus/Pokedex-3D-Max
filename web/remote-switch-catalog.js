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
      const dex = Number(entry.dex);
      if (dex < 1 || dex > 1025 || seen.has(dex)) continue;
      const clips = Array.isArray(entry.animations) ? entry.animations : [];
      const idle = String(entry.idleAnimation || "");
      if (!inventory && (!idle || !clips.includes(idle))) continue;
      const url = new URL(entry.path, base);
      if (url.protocol !== "https:" || url.origin !== base.origin
          || !url.pathname.startsWith(basePath)) continue;
      seen.add(dex);
      results.push({
        dex, form: "regular", name: window.POKEDEX3D_NAMES?.[dex]
          || entry.name || "#" + String(dex).padStart(4, "0"),
        url: url.href, remoteSwitch: true, ready: true, valid: true,
        // An inventory is NOT evidence of texture correctness or animations.
        preflightRequired: inventory,
        idleAnimation: inventory ? null : idle,
        idleBreaks: inventory ? [] : (Array.isArray(entry.idleBreaks) ? entry.idleBreaks : [])
          .filter(name => name !== idle && clips.includes(name)),
      });
    }
    return results.sort((a, b) => a.dex - b.dex);
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
    const animations = (Array.isArray(doc.animations) ? doc.animations : [])
      .filter(clip => Array.isArray(clip?.channels) && clip.channels.length &&
                      Array.isArray(clip?.samplers) && clip.samplers.length)
      .map((clip, index) => clip.name || "animation_" + index);
    const idleAnimation = animations.find(name => IDLE.test(name) && !REJECT.test(name));
    if (!idleAnimation) throw Error("Model has no identifiable idle animation");
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
      if (!snapshot || live.length !== snapshot.entries.length) publish(live);
    } catch (error) {
      if (!snapshot) {
        window.dispatchEvent(new CustomEvent("pokedex3d:remote-switch-error", {
          detail: { message: String(error.message || error) },
        }));
      }
    }
  }

  window.POKEDEX3D_REMOTE_SWITCH = Object.freeze({ prepare, inspect });
  load();
})();
