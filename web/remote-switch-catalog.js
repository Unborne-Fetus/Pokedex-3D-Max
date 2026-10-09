"use strict";

/* Loads verified original Switch GLBs from an optional, public HTTPS asset host.
   The configured private repository cannot be used from an anonymous browser.
   No tokens, unauthenticated Github API probing, or fallback model libraries. */
(function () {
  const CONFIG = "web/models/remote-source.json";
  const PATH = /^(?:switch\/)?(\d{4})\/regular\.glb$/;
  function prepare(config, manifest) {
    if (!config || config.enabled !== true || !config.manifestUrl) return [];
    if (!manifest || manifest.format !== 1 || !Array.isArray(manifest.entries)) {
      throw Error("Expected a verified Switch asset manifest");
    }
    const manifestUrl = new URL(config.manifestUrl);
    if (manifestUrl.protocol !== "https:") throw Error("Remote manifest must use HTTPS");
    const base = config.assetBaseUrl ? new URL(config.assetBaseUrl) : new URL(".", manifestUrl);
    if (base.protocol !== "https:") throw Error("Remote Switch assets must use HTTPS");
    const basePath = base.pathname.endsWith("/") ? base.pathname : base.pathname + "/";
    const result = [];
    const seen = new Set();
    for (const entry of manifest.entries) {
      if (!entry || entry.ready !== true || entry.valid !== true) continue;
      if (String(entry.form || "") !== "regular") continue;
      const match = String(entry.path || "").match(PATH);
      if (!match || Number(entry.dex) !== Number(match[1])) continue;
      const dex = Number(entry.dex);
      if (dex < 1 || dex > 1025 || seen.has(dex)) continue;
      const idle = String(entry.idleAnimation || "");
      const names = Array.isArray(entry.animations) ? entry.animations : [];
      if (!idle || !names.includes(idle)) continue;
      const remote = new URL(entry.path, base);
      if (remote.protocol !== "https:" || remote.origin !== base.origin || !remote.pathname.startsWith(basePath)) {
        continue;
      }
      seen.add(dex);
      result.push({
        dex, form: "regular",
        name: window.POKEDEX3D_NAMES?.[dex] || entry.name || "#" + String(dex).padStart(4, "0"),
        url: remote.href, remoteSwitch: true, ready: true, valid: true,
        idleAnimation: idle,
        idleBreaks: (Array.isArray(entry.idleBreaks) ? entry.idleBreaks : [])
          .filter(name => name !== idle && names.includes(name)),
      });
    }
    return result.sort((a, b) => a.dex - b.dex);
  }

  async function load() {
    // An index.html opened directly from disk cannot fetch another file://
    // resource. Keep local-folder browsing quiet and fully independent.
    if (location.protocol === "file:") return;
    let config;
    try {
      const response = await fetch(CONFIG, { cache: "no-store" });
      if (!response.ok) return;
      config = await response.json();
      if (!config.enabled) return;
      const url = new URL(config.manifestUrl, location.href);
      if (url.protocol !== "https:") throw Error("Remote model manifest must use HTTPS");
      const manifestResponse = await fetch(url.href, { mode: "cors" });
      if (!manifestResponse.ok) throw Error("Remote model manifest cannot be accessed");
      const catalog = prepare(config, await manifestResponse.json());
      if (!catalog.length) throw Error("No verified original Switch assets in remote catalog");
      window.dispatchEvent(new CustomEvent("pokedex3d:remote-switch-catalog", {
        detail: { models: catalog },
      }));
    } catch (error) {
      window.dispatchEvent(new CustomEvent("pokedex3d:remote-switch-error", {
        detail: { message: String(error?.message || error) },
      }));
    }
  }

  window.POKEDEX3D_REMOTE_SWITCH = Object.freeze({ prepare });
  load();
})();
