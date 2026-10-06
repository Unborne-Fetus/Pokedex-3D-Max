window.__pokedex3dBooted = true;
const API_URL = "https://pokemon-3d-api.onrender.com/v1/pokemon";
const CDN_ROOT = "https://cdn.jsdelivr.net/gh/Pokemon-3D-api/assets@main/";
const CATALOG_CACHE_KEY = "pokedex3dmax.catalog.v2";

const REGULAR_MODEL = id =>
  CDN_ROOT + "models/opt/regular/" + id + ".glb";

const viewer = document.querySelector("#viewer");
const statusEl = document.querySelector("#status");
const listEl = document.querySelector("#list");
const searchEl = document.querySelector("#search");
const dexEl = document.querySelector("#dexNumber");
const nameEl = document.querySelector("#pokemonName");
const formEl = document.querySelector("#formName");
const formSelect = document.querySelector("#formSelect");
const messageEl = document.querySelector("#viewerMessage");
const prevBtn = document.querySelector("#prevBtn");
const nextBtn = document.querySelector("#nextBtn");
const resetCameraBtn = document.querySelector("#resetCamera");
const toggleRotateBtn = document.querySelector("#toggleRotate");
const toggleIdleBreaksBtn = document.querySelector("#toggleIdleBreaks");

let models = makeInstantRegularCatalog();
let filtered = models;
let selectedIndex = 0;
let autoRotate = false;
let idleBreaksEnabled = true;
let currentUrl = "";
let currentModel = null;
let modelLoadRequest = 0;
let loadStartedAt = 0;
let idleBreakTimer = null;
let breakEndTimer = null;
let idleAnimation = null;
let breakAnimations = [];
let playingBreak = false;
const warmed = new Set();
const preparedModelUrls = new Map();

const IDLE_BREAK_OVERRIDES = {
  // Bulbasaur: use its actual Pokédex-style break, not a jump clip.
  1: ["model_skeleton|001fight_d"],
};

function makeInstantRegularCatalog() {
  return Array.from({ length: 1025 }, (_, i) => {
    const dex = i + 1;
    return {
      dex,
      name: "#" + String(dex).padStart(4, "0"),
      form: "regular",
      url: REGULAR_MODEL(dex),
    };
  });
}

function toFastAssetUrl(url) {
  const raw = String(url || "");
  const marker = "Pokemon-3D-api/assets/";
  const githubMarker = "github.com/Pokemon-3D-api/assets/";

  if (raw.includes("raw.githubusercontent.com/Pokemon-3D-api/assets/")) {
    const path = raw
      .split("raw.githubusercontent.com/Pokemon-3D-api/assets/")[1]
      .replace(/^main\//, "")
      .replace(/^refs\/heads\/main\//, "")
      .replace(/^heads\/main\//, "");
    return CDN_ROOT + path;
  }

  if (raw.includes(githubMarker)) {
    const tail = raw.split(githubMarker)[1];
    const path = tail
      .replace(/^blob\/main\//, "")
      .replace(/^raw\/main\//, "")
      .replace(/^refs\/heads\/main\//, "")
      .replace(/^heads\/main\//, "");
    return CDN_ROOT + path;
  }

  if (raw.includes(marker)) {
    const tail = raw.split(marker)[1]
      .replace(/^main\//, "")
      .replace(/^refs\/heads\/main\//, "")
      .replace(/^heads\/main\//, "");
    return CDN_ROOT + tail;
  }

  return raw
    .replace("/refs/heads/main/heads/main/", "/refs/heads/main/")
    .replace("/main/heads/main/", "/main/");
}

function normalizeCatalog(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.pokemon)) return payload.pokemon;
  if (Array.isArray(payload?.data)) return payload.data;
  throw new Error("Unsupported catalog JSON format");
}

function catalogToModels(payload) {
  const pokemon = normalizeCatalog(payload);
  const out = [];

  for (const entry of pokemon) {
    const dex = Number(entry.id);
    const forms = Array.isArray(entry.forms) ? entry.forms : [];

    for (const form of forms) {
      const url = toFastAssetUrl(form.model);
      if (!url) continue;

      out.push({
        dex,
        name: form.name || ("#" + String(dex).padStart(4, "0")),
        form: form.formName || "regular",
        url,
      });
    }
  }

  return out
    .filter((m, i, arr) =>
      arr.findIndex(x => x.dex === m.dex && x.form === m.form && x.url === m.url) === i
    )
    .sort((a, b) =>
      a.dex - b.dex ||
      formRank(a.form) - formRank(b.form) ||
      a.form.localeCompare(b.form)
    );
}

async function enhanceCatalogInBackground() {
  const cached = localStorage.getItem(CATALOG_CACHE_KEY);
  if (cached) {
    try {
      const cachedModels = catalogToModels(JSON.parse(cached));
      if (cachedModels.length) {
        models = cachedModels;
        statusEl.textContent =
          models.length.toLocaleString() + " 3D models · cached catalog";
        refreshCurrentPokemonAfterCatalogUpdate();
      }
    } catch {
      localStorage.removeItem(CATALOG_CACHE_KEY);
    }
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);

  try {
    const response = await fetch(API_URL, {
      cache: "force-cache",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error("Catalog HTTP " + response.status);

    const payload = await response.json();
    const richer = catalogToModels(payload);
    if (!richer.length) throw new Error("Catalog contained no model entries");

    localStorage.setItem(CATALOG_CACHE_KEY, JSON.stringify(payload));
    models = richer;
    statusEl.textContent =
      models.length.toLocaleString() + " 3D models available";
    refreshCurrentPokemonAfterCatalogUpdate();
  } catch (error) {
    console.warn("Background catalog update skipped:", error);
    if (!cached) {
      statusEl.textContent =
        "1,025 regular models ready · forms will update when catalog responds";
    }
  } finally {
    clearTimeout(timeout);
  }
}

function isShiny(model) {
  const form = String(model?.form || "").toLowerCase();
  const name = String(model?.name || "").toLowerCase();
  return form.includes("shiny") || name.startsWith("shiny ");
}

function formRank(form) {
  const value = String(form || "").toLowerCase();
  if (value === "regular") return 0;
  if (value.includes("shiny")) return 2;
  return 1;
}

function refreshCurrentPokemonAfterCatalogUpdate() {
  const dex = currentModel?.dex || filtered[selectedIndex]?.dex || 1;
  const currentForm = currentModel?.form || "regular";

  applyFilter(false);

  const exact = models.find(
    model => model.dex === dex && model.form === currentForm
  );
  const regular =
    models.find(
      model =>
        model.dex === dex &&
        !isShiny(model) &&
        String(model.form).toLowerCase() === "regular"
    ) ||
    models.find(model => model.dex === dex && !isShiny(model));

  const target = exact || regular;
  if (!target) return;

  currentModel = target;
  dexEl.textContent = "#" + String(target.dex).padStart(4, "0");
  nameEl.textContent = target.name;
  formEl.textContent = prettyForm(target.form);
  populateFormSelect(target);

  const visibleIndex = filtered.findIndex(
    model => model.dex === target.dex && model.form === target.form
  );
  if (visibleIndex >= 0) {
    selectedIndex = visibleIndex;
    updateSelectedRow();
  }
}

function applyFilter(loadFirst = true) {
  const q = searchEl.value.trim().toLowerCase().replace(/^#/, "");

  const listModels = models.filter(m => !isShiny(m));

  filtered = q
    ? listModels.filter(m =>
        String(m.dex) === q ||
        m.name.toLowerCase().includes(q) ||
        m.form.toLowerCase().includes(q)
      )
    : listModels;

  renderList();

  if (loadFirst && filtered.length) {
    selectModel(0);
  }
}

function renderList() {
  listEl.replaceChildren();

  const fragment = document.createDocumentFragment();
  for (let i = 0; i < filtered.length; i++) {
    const model = filtered[i];
    const button = document.createElement("button");
    button.type = "button";
    button.className = "entry";
    button.dataset.index = i;
    button.innerHTML =
      '<span class="dex">#' + String(model.dex).padStart(4, "0") + '</span>' +
      '<span><span class="name">' + escapeHtml(model.name) + '</span><br />' +
      '<span class="form">' + escapeHtml(prettyForm(model.form)) + '</span></span>';
    button.addEventListener("click", () => selectModel(i));
    fragment.appendChild(button);
  }

  listEl.appendChild(fragment);
  updateSelectedRow();
}

function selectModel(index) {
  if (!filtered.length) return;

  selectedIndex = Math.max(0, Math.min(index, filtered.length - 1));
  const model = filtered[selectedIndex];

  dexEl.textContent = "#" + String(model.dex).padStart(4, "0");
  nameEl.textContent = model.name;
  formEl.textContent = prettyForm(model.form);

  populateFormSelect(model);
  loadModel(model);
  updateSelectedRow();
  prefetchNeighbors();
}

async function prepareModelForWeb(sourceUrl) {
  if (preparedModelUrls.has(sourceUrl)) {
    return preparedModelUrls.get(sourceUrl);
  }

  const response = await fetch(sourceUrl, {
    mode: "cors",
    cache: "force-cache",
  });
  if (!response.ok) {
    throw new Error("Model HTTP " + response.status);
  }

  const source = await response.arrayBuffer();
  const view = new DataView(source);

  // GLB v2 header.
  if (
    source.byteLength < 20 ||
    view.getUint32(0, true) !== 0x46546c67 ||
    view.getUint32(4, true) !== 2
  ) {
    return sourceUrl;
  }

  const jsonLength = view.getUint32(12, true);
  const jsonType = view.getUint32(16, true);
  if (jsonType !== 0x4e4f534a || 20 + jsonLength > source.byteLength) {
    return sourceUrl;
  }

  const decoder = new TextDecoder();
  const rawJson = decoder
    .decode(new Uint8Array(source, 20, jsonLength))
    .replace(/[\u0000\s]+$/g, "");
  const documentJson = JSON.parse(rawJson);

  // These models split face/eye/body surfaces into separate material primitives.
  // Rendering them unlit removes normal/lighting discontinuities at those borders.
  const used = new Set(documentJson.extensionsUsed || []);
  used.add("KHR_materials_unlit");
  documentJson.extensionsUsed = Array.from(used);

  for (const material of documentJson.materials || []) {
    material.extensions = material.extensions || {};
    material.extensions.KHR_materials_unlit = {};
    material.pbrMetallicRoughness = material.pbrMetallicRoughness || {};
    material.pbrMetallicRoughness.metallicFactor = 0;
    material.pbrMetallicRoughness.roughnessFactor = 1;

    // Eye textures are separate overlay meshes. If they stay OPAQUE, the
    // transparent padding around the actual eye becomes a visible polygon.
    if (/eye/i.test(String(material.name || ""))) {
      material.alphaMode = "BLEND";
      material.doubleSided = true;
    }
  }

  const encoder = new TextEncoder();
  const encodedJson = encoder.encode(JSON.stringify(documentJson));
  const paddedJsonLength = (encodedJson.length + 3) & ~3;
  const oldTailOffset = 20 + jsonLength;
  const tail = new Uint8Array(source, oldTailOffset);

  const rebuilt = new ArrayBuffer(20 + paddedJsonLength + tail.length);
  const rebuiltView = new DataView(rebuilt);
  const rebuiltBytes = new Uint8Array(rebuilt);

  rebuiltView.setUint32(0, 0x46546c67, true);
  rebuiltView.setUint32(4, 2, true);
  rebuiltView.setUint32(8, rebuilt.byteLength, true);
  rebuiltView.setUint32(12, paddedJsonLength, true);
  rebuiltView.setUint32(16, 0x4e4f534a, true);

  rebuiltBytes.set(encodedJson, 20);
  rebuiltBytes.fill(0x20, 20 + encodedJson.length, 20 + paddedJsonLength);
  rebuiltBytes.set(tail, 20 + paddedJsonLength);

  const blobUrl = URL.createObjectURL(
    new Blob([rebuilt], { type: "model/gltf-binary" })
  );
  preparedModelUrls.set(sourceUrl, blobUrl);
  return blobUrl;
}

async function loadModel(model) {
  const url = toFastAssetUrl(model.url);
  if (url === currentUrl && viewer.loaded) return;

  currentUrl = url;
  currentModel = model;
  const request = ++modelLoadRequest;
  loadStartedAt = performance.now();

  messageEl.textContent = "Preparing 3D model…";
  messageEl.classList.remove("hidden");

  try {
    const preparedUrl = await prepareModelForWeb(url);
    if (request !== modelLoadRequest) return;

    viewer.removeAttribute("src");
    viewer.src = preparedUrl;
  } catch (error) {
    console.warn("Web GLB preparation failed; using source model:", error);
    if (request !== modelLoadRequest) return;

    viewer.removeAttribute("src");
    viewer.src = url;
  }

  viewer.alt =
    "3D model of " + model.name + ", " + prettyForm(model.form) + " form";
  viewer.cameraOrbit = "auto auto auto";
  viewer.cameraTarget = "auto auto auto";
  viewer.fieldOfView = "28deg";
  viewer.jumpCameraToGoal?.();
}

function prefetchNeighbors() {
  for (const offset of [-2, -1, 1, 2]) {
    const model = filtered[selectedIndex + offset];
    if (model) warmModel(toFastAssetUrl(model.url));
  }
}

function warmModel(url) {
  if (!url || warmed.has(url)) return;
  warmed.add(url);

  const link = document.createElement("link");
  link.rel = "prefetch";
  link.as = "fetch";
  link.href = url;
  link.crossOrigin = "anonymous";
  document.head.appendChild(link);

  if ("caches" in window) {
    caches.open("pokedex3dmax-models-v1").then(async cache => {
      const hit = await cache.match(url);
      if (hit) return;
      try {
        const response = await fetch(url, {
          mode: "cors",
          cache: "force-cache",
        });
        if (response.ok) await cache.put(url, response.clone());
      } catch {
        // Prefetch is opportunistic.
      }
    });
  } else {
    fetch(url, { mode: "cors", cache: "force-cache" }).catch(() => {});
  }
}

function populateFormSelect(model) {
  const samePokemon = models.filter(m => m.dex === model.dex);
  formSelect.replaceChildren();

  for (const form of samePokemon) {
    const option = document.createElement("option");
    option.value = form.url;
    option.textContent = dropdownLabel(form);
    option.selected = form.url === model.url;
    option.dataset.dex = String(form.dex);
    formSelect.appendChild(option);
  }

  formSelect.disabled = samePokemon.length <= 1;
}

function updateSelectedRow() {
  listEl.querySelectorAll(".entry").forEach((el, i) => {
    el.classList.toggle("selected", i === selectedIndex);
  });
  listEl.querySelector(".entry.selected")?.scrollIntoView({ block: "nearest" });
}

function prettyForm(value) {
  return String(value || "regular")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());
}

function dropdownLabel(model) {
  const form = prettyForm(model.form);
  if (isShiny(model)) {
    const cleaned = form.replace(/\bShiny\b/gi, "").trim();
    return cleaned && cleaned.toLowerCase() !== "regular"
      ? "Shiny · " + cleaned
      : "Shiny";
  }
  return form;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

searchEl.addEventListener("input", () => {
  applyFilter(false);
  selectedIndex = 0;
  if (filtered.length) selectModel(0);
});

formSelect.addEventListener("change", () => {
  const url = formSelect.value;
  const target = models.find(m => m.url === url);
  if (!target) return;

  const visibleIndex = filtered.findIndex(m => m.url === url);
  if (visibleIndex >= 0) {
    selectModel(visibleIndex);
  } else {
    dexEl.textContent = "#" + String(target.dex).padStart(4, "0");
    nameEl.textContent = target.name;
    formEl.textContent = prettyForm(target.form);
    loadModel(target);
    populateFormSelect(target);
  }
});

prevBtn.addEventListener("click", () => selectModel(selectedIndex - 1));
nextBtn.addEventListener("click", () => selectModel(selectedIndex + 1));

resetCameraBtn.addEventListener("click", () => {
  viewer.cameraOrbit = "auto auto auto";
  viewer.cameraTarget = "auto auto auto";
  viewer.fieldOfView = "28deg";
  viewer.jumpCameraToGoal?.();
});

toggleRotateBtn.addEventListener("click", () => {
  autoRotate = !autoRotate;
  viewer.autoRotate = autoRotate;
  toggleRotateBtn.textContent =
    "Auto-rotate: " + (autoRotate ? "On" : "Off");
});

toggleIdleBreaksBtn.addEventListener("click", () => {
  idleBreaksEnabled = !idleBreaksEnabled;
  toggleIdleBreaksBtn.textContent =
    "Idle breaks: " + (idleBreaksEnabled ? "On" : "Off");

  if (!idleBreaksEnabled) {
    clearIdleBreakTimers();
    startBaseIdle();
  } else {
    scheduleNextIdleBreak();
  }
});

function configureTextureSampling() {
  const materials = viewer.model?.materials || [];

  for (const material of materials) {
    const textureInfos = [
      material.pbrMetallicRoughness?.baseColorTexture,
      material.pbrMetallicRoughness?.metallicRoughnessTexture,
      material.normalTexture,
      material.occlusionTexture,
      material.emissiveTexture,
    ];

    for (const info of textureInfos) {
      const sampler = info?.texture?.sampler;
      if (!sampler) continue;

      try {
        sampler.setWrapS("ClampToEdge");
        sampler.setWrapT("ClampToEdge");
        sampler.setMinFilter("Linear");
        sampler.setMagFilter("Linear");
      } catch (error) {
        console.debug("Sampler quality override unavailable:", error);
      }
    }
  }
}

function animationScore(name) {
  const value = name.toLowerCase();

  // Short jump clips make the best "idle break" for models such as Bulbasaur.
  if (/jump_s|jump-s|short.*jump/.test(value)) return 140;
  if (/jump_e|jump-e|jump_l|jump-l|jump/.test(value)) return 125;
  if (/wait|look|break/.test(value)) return 110;
  if (/fight_[bd]|fight-b|fight-d/.test(value)) return 70;
  if (/fight/.test(value)) return 40;
  if (/run|walk|ko|death|hit|damage|attack/.test(value)) return -100;
  return 10;
}

function clearIdleBreakTimers() {
  if (idleBreakTimer) {
    clearTimeout(idleBreakTimer);
    idleBreakTimer = null;
  }
  if (breakEndTimer) {
    clearTimeout(breakEndTimer);
    breakEndTimer = null;
  }
}

function startBaseIdle() {
  if (!idleAnimation) return;

  playingBreak = false;
  viewer.animationName = idleAnimation;
  viewer.currentTime = 0;
  viewer.play();
}

function scheduleNextIdleBreak() {
  if (idleBreakTimer) {
    clearTimeout(idleBreakTimer);
    idleBreakTimer = null;
  }

  if (
    !idleBreaksEnabled ||
    !viewer.loaded ||
    !idleAnimation ||
    !breakAnimations.length
  ) {
    return;
  }

  // The three-second gap begins only AFTER the previous break has ended.
  idleBreakTimer = setTimeout(playIdleBreak, 3000);
}

function playIdleBreak() {
  idleBreakTimer = null;

  if (
    !idleBreaksEnabled ||
    !viewer.loaded ||
    document.hidden ||
    playingBreak ||
    !breakAnimations.length
  ) {
    scheduleNextIdleBreak();
    return;
  }

  const clip = breakAnimations[
    Math.floor(Math.random() * breakAnimations.length)
  ];

  playingBreak = true;
  viewer.animationName = clip;
  viewer.currentTime = 0;
  viewer.play({ repetitions: 1 });

  // model-viewer exposes the active clip duration after animationName changes.
  requestAnimationFrame(() => {
    const seconds = Number(viewer.duration);
    const durationMs =
      Number.isFinite(seconds) && seconds > 0
        ? seconds * 1000
        : 1800;

    if (breakEndTimer) clearTimeout(breakEndTimer);
    breakEndTimer = setTimeout(() => {
      breakEndTimer = null;
      if (!playingBreak) return;

      startBaseIdle();
      scheduleNextIdleBreak();
    }, durationMs + 100);
  });
}

function setupIdleBreakAnimations() {
  clearIdleBreakTimers();

  const animations = Array.from(viewer.availableAnimations || []);
  idleAnimation =
    animations.find(name => /idle/i.test(name)) ||
    animations[0] ||
    null;

  const overrideNames =
    IDLE_BREAK_OVERRIDES[currentModel?.dex] || [];

  const overrides = overrideNames.filter(name =>
    animations.includes(name)
  );

  if (overrides.length) {
    breakAnimations = overrides;
  } else {
    breakAnimations = animations
      .filter(name => name !== idleAnimation)
      .filter(name => animationScore(name) > 0)
      .sort((a, b) => animationScore(b) - animationScore(a));

    if (breakAnimations.length) {
      const bestScore = animationScore(breakAnimations[0]);
      breakAnimations = breakAnimations.filter(
        name => animationScore(name) === bestScore
      );
    }
  }

  startBaseIdle();

  if (idleBreaksEnabled) {
    scheduleNextIdleBreak();
  }
}

viewer.addEventListener("load", () => {
  const elapsed = Math.max(0, performance.now() - loadStartedAt);
  messageEl.textContent =
    "Loaded in " + (elapsed / 1000).toFixed(1) + "s";
  setTimeout(() => messageEl.classList.add("hidden"), 900);

  viewer.cameraOrbit = "auto auto auto";
  viewer.cameraTarget = "auto auto auto";
  viewer.jumpCameraToGoal?.();

  configureTextureSampling();
  setupIdleBreakAnimations();
  prefetchNeighbors();
});

viewer.addEventListener("error", event => {
  console.error("Model load error", event);
  messageEl.textContent = "Model failed to load";
  messageEl.classList.remove("hidden");
});

viewer.addEventListener("progress", event => {
  const progress = Number(event.detail?.totalProgress || 0);
  const fill = viewer.querySelector(".progress-fill");
  if (fill) fill.style.width = Math.round(progress * 100) + "%";

  if (progress > 0 && progress < 1) {
    messageEl.textContent =
      "Loading 3D model… " + Math.round(progress * 100) + "%";
  }
});

// Render immediately. Do not wait for the remote catalog.
statusEl.textContent = "1,025 regular models ready";
renderList();

customElements.whenDefined("model-viewer").then(() => {
  const ModelViewerElement = customElements.get("model-viewer");
  if (ModelViewerElement) {
    ModelViewerElement.minimumRenderScale = 1;
    ModelViewerElement.modelCacheSize = 8;
  }

  selectModel(0);
  enhanceCatalogInBackground();
});
