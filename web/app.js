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
let activeModelCandidates = [];
let activeCandidateIndex = 0;
let modelLoadTimeout = null;
let animationDurations = new Map();

const IDLE_BREAK_OVERRIDES = {
  // Bulbasaur: use its actual Pokédex-style break, not a jump clip.
  1: ["model_skeleton|001fight_b"],
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

function modelAssetPath(url) {
  const raw = String(url || "");

  if (raw.startsWith(CDN_ROOT)) {
    return raw.slice(CDN_ROOT.length);
  }

  const rawMarker =
    "raw.githubusercontent.com/Pokemon-3D-api/assets/";
  if (raw.includes(rawMarker)) {
    return raw
      .split(rawMarker)[1]
      .replace(/^main\//, "")
      .replace(/^refs\/heads\/main\//, "")
      .replace(/^heads\/main\//, "");
  }

  const githubMarker = "github.com/Pokemon-3D-api/assets/";
  if (raw.includes(githubMarker)) {
    return raw
      .split(githubMarker)[1]
      .replace(/^blob\/main\//, "")
      .replace(/^raw\/main\//, "")
      .replace(/^refs\/heads\/main\//, "")
      .replace(/^heads\/main\//, "");
  }

  return null;
}

function getModelCandidates(model) {
  const original = String(model?.url || "");
  const fast = toFastAssetUrl(original);
  const path = modelAssetPath(fast) || modelAssetPath(original);

  const candidates = [fast];

  if (path) {
    candidates.push(
      "https://raw.githubusercontent.com/Pokemon-3D-api/assets/main/" + path
    );
  }

  if (original) candidates.push(original);

  return [...new Set(candidates.filter(Boolean))];
}

function clearModelLoadTimeout() {
  if (modelLoadTimeout) {
    clearTimeout(modelLoadTimeout);
    modelLoadTimeout = null;
  }
}

function startModelCandidate(index) {
  if (!activeModelCandidates.length) return;

  activeCandidateIndex = index;
  if (activeCandidateIndex >= activeModelCandidates.length) {
    clearModelLoadTimeout();
    messageEl.textContent = "Model failed to load from all available sources";
    messageEl.classList.remove("hidden");
    return;
  }

  const candidate = activeModelCandidates[activeCandidateIndex];
  messageEl.textContent =
    "Loading 3D model… source " +
    (activeCandidateIndex + 1) +
    "/" +
    activeModelCandidates.length;
  messageEl.classList.remove("hidden");

  viewer.removeAttribute("src");
  viewer.src = candidate;

  clearModelLoadTimeout();
  modelLoadTimeout = setTimeout(() => {
    console.warn("Model load timed out:", candidate);
    startModelCandidate(activeCandidateIndex + 1);
  }, 15000);
}

async function loadModel(model) {
  const primary = toFastAssetUrl(model.url);
  if (primary === currentUrl && viewer.loaded) return;

  clearIdleBreakTimers();
  clearModelLoadTimeout();

  currentUrl = primary;
  currentModel = model;
  ++modelLoadRequest;
  loadStartedAt = performance.now();
  animationDurations = new Map();

  activeModelCandidates = getModelCandidates(model);
  activeCandidateIndex = 0;

  viewer.alt =
    "3D model of " + model.name + ", " + prettyForm(model.form) + " form";

  startModelCandidate(0);
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
  frameLoadedModel();
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

function normalizeMaterials() {
  const materials = viewer.model?.materials || [];

  for (const material of materials) {
    try {
      // Preserve original PBR colors/textures/accessory materials.
      // Only make solid materials double-sided so backfaces do not vanish
      // at certain camera angles.
      if (material.getAlphaMode?.() !== "BLEND") {
        material.setDoubleSided?.(true);
      }
    } catch (error) {
      console.debug("Material normalization skipped:", error);
    }
  }
}

function frameLoadedModel() {
  try {
    const center = viewer.getBoundingBoxCenter();
    const dimensions = viewer.getDimensions();

    viewer.cameraTarget =
      center.x.toFixed(4) + "m " +
      center.y.toFixed(4) + "m " +
      center.z.toFixed(4) + "m";

    // Percentage radius uses model-viewer's own ideal framing distance,
    // avoiding tiny/off-center starts for unusually tall or wide models.
    viewer.cameraOrbit = "0deg 75deg 112%";
    viewer.fieldOfView = "30deg";
    viewer.minCameraOrbit = "auto 1deg 18%";
    viewer.maxCameraOrbit = "auto 179deg 900%";
    viewer.jumpCameraToGoal?.();

    console.debug("Framed model", {
      center,
      dimensions,
    });
  } catch (error) {
    console.debug("Automatic framing fallback:", error);
    viewer.cameraTarget = "auto auto auto";
    viewer.cameraOrbit = "0deg 75deg 112%";
    viewer.jumpCameraToGoal?.();
  }
}

function readAnimationDurations() {
  const durations = new Map();

  try {
    const gltf = viewer.originalGltfJson;
    const animations = gltf?.animations || [];
    const accessors = gltf?.accessors || [];

    for (let index = 0; index < animations.length; index++) {
      const animation = animations[index];
      const name =
        animation?.name ||
        viewer.availableAnimations?.[index] ||
        String(index);

      let duration = 0;

      for (const sampler of animation?.samplers || []) {
        const accessor = accessors[sampler?.input];
        const max = Number(accessor?.max?.[0]);
        if (Number.isFinite(max)) {
          duration = Math.max(duration, max);
        }
      }

      if (duration > 0) durations.set(name, duration);
    }
  } catch (error) {
    console.debug("Animation duration scan skipped:", error);
  }

  return durations;
}

function chooseBaseIdle(animations) {
  const priorities = [
    /(^|[|_])a?idle($|[|_])/i,
    /wait|stand|breath/i,
    /fight[_-]?b/i,
    /fight[_-]?d/i,
  ];

  for (const pattern of priorities) {
    const match = animations.find(name => pattern.test(name));
    if (match) return match;
  }

  const safe = animations.find(
    name => !/ko|death|faint|hit|damage|attack|run|walk|jump/i.test(name)
  );

  return safe || animations[0] || null;
}

function animationScore(name) {
  const value = name.toLowerCase();

  // Idle breaks must be conservative. Movement/KO/attack clips are not used
  // automatically because many species look broken with those outside battle.
  if (/break|fidget|look|wait/i.test(value)) return 120;
  if (/fight[_-]?d/i.test(value)) return 80;
  if (/fight[_-]?b/i.test(value)) return 70;
  if (/jump|run|walk|ko|death|faint|hit|damage|attack/i.test(value)) {
    return -100;
  }
  return -10;
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

  // "finished" is the primary completion signal. This timeout is only
  // a safety fallback for models that fail to emit it.
  const seconds =
    animationDurations.get(clip) ||
    Number(viewer.duration) ||
    2;

  if (breakEndTimer) clearTimeout(breakEndTimer);
  breakEndTimer = setTimeout(() => {
    breakEndTimer = null;
    if (!playingBreak) return;

    startBaseIdle();
    scheduleNextIdleBreak();
  }, Math.max(500, seconds * 1000 + 250));
}

function setupIdleBreakAnimations() {
  clearIdleBreakTimers();

  const animations = Array.from(viewer.availableAnimations || []);
  animationDurations = readAnimationDurations();

  idleAnimation = chooseBaseIdle(animations);

  const overrideNames =
    IDLE_BREAK_OVERRIDES[currentModel?.dex] || [];

  const overrides = overrideNames.filter(name => animations.includes(name));

  if (overrides.length) {
    breakAnimations = overrides;
  } else {
    breakAnimations = animations
      .filter(name => name !== idleAnimation)
      .filter(name => animationScore(name) > 0)
      .filter(name => {
        const duration = animationDurations.get(name);
        return !duration || (duration >= 0.35 && duration <= 4.5);
      })
      .sort((a, b) => animationScore(b) - animationScore(a));

    if (breakAnimations.length) {
      const best = animationScore(breakAnimations[0]);
      breakAnimations = breakAnimations.filter(
        name => animationScore(name) === best
      );
    }
  }

  startBaseIdle();

  const available = Boolean(idleAnimation && breakAnimations.length);
  toggleIdleBreaksBtn.disabled = !available;
  toggleIdleBreaksBtn.textContent = available
    ? "Idle breaks: " + (idleBreaksEnabled ? "On" : "Off")
    : "Idle breaks: Unavailable";

  if (available && idleBreaksEnabled) {
    scheduleNextIdleBreak();
  }
}

viewer.addEventListener("load", () => {
  clearModelLoadTimeout();

  const elapsed = Math.max(0, performance.now() - loadStartedAt);
  messageEl.textContent =
    "Loaded in " + (elapsed / 1000).toFixed(1) + "s";
  setTimeout(() => messageEl.classList.add("hidden"), 900);

  normalizeMaterials();
  frameLoadedModel();
  setupIdleBreakAnimations();
  prefetchNeighbors();
});

viewer.addEventListener("error", event => {
  console.error(
    "Model load error",
    activeModelCandidates[activeCandidateIndex],
    event
  );

  if (activeCandidateIndex + 1 < activeModelCandidates.length) {
    startModelCandidate(activeCandidateIndex + 1);
    return;
  }

  clearModelLoadTimeout();
  messageEl.textContent = "Model failed to load from all available sources";
  messageEl.classList.remove("hidden");
});

viewer.addEventListener("finished", () => {
  if (!playingBreak) return;

  if (breakEndTimer) {
    clearTimeout(breakEndTimer);
    breakEndTimer = null;
  }

  startBaseIdle();
  scheduleNextIdleBreak();
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
