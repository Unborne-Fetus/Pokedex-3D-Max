window.__pokedex3dBooted = true;
const API_URL = "https://pokemon-3d-api.onrender.com/v1/pokemon";
const CDN_ROOT = "https://cdn.jsdelivr.net/gh/Pokemon-3D-api/assets@main/";
const CATALOG_CACHE_KEY = "pokedex3dmax.catalog.v2";
const LOCAL_MODELS = [
  ...(Array.isArray(window.POKEDEX3D_POKEMINERS_MODELS)
    ? window.POKEDEX3D_POKEMINERS_MODELS
    : []),
  ...(Array.isArray(window.POKEDEX3D_LOCAL_MODELS)
    ? window.POKEDEX3D_LOCAL_MODELS
    : []),
  ...(Array.isArray(window.POKEDEX3D_PRO_MODELS)
    ? window.POKEDEX3D_PRO_MODELS
    : []),
  // Native Switch-game imports are highest priority once they are validated
  // and animation-ready. Staged bind-pose imports stay out of the live viewer.
  ...(Array.isArray(window.POKEDEX3D_SWITCH_MODELS)
    ? window.POKEDEX3D_SWITCH_MODELS
    : []),
].filter(model => model?.valid !== false && model?.ready !== false)
 .filter(model => !window.POKEDEX3D_MODEL_POLICY?.switchOnly || String(model.url).includes("/switch/"));

function localModelKey(model) {
  let form = String(model?.form || "regular").trim().toLowerCase().replace(/-00$/, "");
  if (Number(model?.dex) === 6) {
    if (["form-51", "51", "mega-x", "megax", "x", "xy"].includes(form)) form = "mega-x";
    if (["form-52", "52", "mega-y", "megay", "y"].includes(form)) form = "mega-y";
    if (["gmax", "gigantamax"].includes(form)) form = "gmax";
  }
  return String(model?.dex) + "|" + (form || "regular");
}

function applyLocalModelOverrides(list) {
  if (window.POKEDEX3D_MODEL_POLICY?.switchOnly) list = [];
  if (!LOCAL_MODELS.length) return list;
  list = [...new Map(list.map(model => [localModelKey(model), model])).values()];

  const overrides = new Map(
    LOCAL_MODELS.map(model => [localModelKey(model), model])
  );

  const merged = list.map(model => {
    const replacement = overrides.get(localModelKey(model));
    if (!replacement) return model;

    const replacementAnimations = Array.isArray(replacement.animations)
      ? replacement.animations
      : [];
    const replacementHasIdle =
      Boolean(replacement.idleAnimation) || replacementAnimations.length > 0;

    // Never replace an animated catalog model with an animation-less bind pose.
    if (
      replacement.source === "PokeMiners/pogo_assets" &&
      !replacementHasIdle
    ) {
      return model;
    }

    return {
      ...model,
      ...replacement,
      url: replacement.url,
      fallbackUrl: model.url,
      local: true,
    };
  });

  const existing = new Set(merged.map(localModelKey));
  for (const replacement of overrides.values()) {
    const key = localModelKey(replacement);
    if (!existing.has(key)) {
      const replacementAnimations = Array.isArray(replacement.animations)
        ? replacement.animations
        : [];
      const replacementHasIdle =
        Boolean(replacement.idleAnimation) || replacementAnimations.length > 0;

      if (
        replacement.source === "PokeMiners/pogo_assets" &&
        !replacementHasIdle
      ) {
        continue;
      }

      merged.push({
        ...replacement,
        local: true,
      });
    }
  }

  return merged.sort(
    (a, b) =>
      a.dex - b.dex ||
      formRank(a.form) - formRank(b.form) ||
      String(a.form).localeCompare(String(b.form))
  );
}

const REGULAR_MODEL = id =>
  CDN_ROOT + "models/opt/regular/" + id + ".glb";

const viewer = document.querySelector("#viewer");
const threeFallbackHost = document.querySelector("#threeFallback");
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
window.POKEDEX3D_MODELS = models;
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
let proceduralFallbackFrame = null;
let proceduralFallbackStartedAt = 0;
let fbxRuntimePromise = null;
let fbxFallbackState = null;
let fbxFallbackLoadToken = 0;
const pokeMinersTextureInventoryCache = new Map();

const IDLE_BREAK_OVERRIDES = {
  // Only verified clips belong here. Unknown species show "Unavailable"
  // instead of guessing a broken animation.
  1: ["model_skeleton|001fight_b"],
};

function makeInstantRegularCatalog() {
  const fallback = Array.from({ length: 1025 }, (_, i) => {
    const dex = i + 1;
    return {
      dex,
      name: window.POKEDEX3D_NAMES?.[dex] || "#" + String(dex).padStart(4, "0"),
      form: "regular",
      url: REGULAR_MODEL(dex),
    };
  });

  return applyLocalModelOverrides(fallback);
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

  const deduped = out
    .filter((m, i, arr) =>
      arr.findIndex(x => x.dex === m.dex && x.form === m.form && x.url === m.url) === i
    )
    .sort((a, b) =>
      a.dex - b.dex ||
      formRank(a.form) - formRank(b.form) ||
      a.form.localeCompare(b.form)
    );

  return applyLocalModelOverrides(deduped);
}

async function enhanceCatalogInBackground() {
  if (window.POKEDEX3D_MODEL_POLICY?.switchOnly) {
    statusEl.textContent = models.length.toLocaleString() + " restored Switch models · textures unfinished";
    return;
  }
  let cached = null;
  try { cached = localStorage.getItem(CATALOG_CACHE_KEY); } catch {}
  if (cached) {
    try {
      const cachedModels = catalogToModels(JSON.parse(cached));
      if (cachedModels.length) {
        models = cachedModels;
        window.POKEDEX3D_MODELS = models;
        statusEl.textContent =
          models.length.toLocaleString() + " 3D models · cached catalog";
        refreshCurrentPokemonAfterCatalogUpdate();
      }
    } catch {
      try { localStorage.removeItem(CATALOG_CACHE_KEY); } catch {}
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

    try { localStorage.setItem(CATALOG_CACHE_KEY, JSON.stringify(payload)); } catch {}
    models = richer.filter(model => !isShiny(model));
    window.POKEDEX3D_MODELS = models;
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

  if (model?.local || original.startsWith("web/models/")) {
    // A selected Switch model stays selected on failure so import problems
    // cannot silently replace the newer asset with an old CDN model.
    if (model?.source === "Switch game assets" || original.includes("/switch/")) return [original];
    const fallback = String(model?.fallbackUrl || REGULAR_MODEL(model?.dex));
    return [...new Set([original, fallback].filter(Boolean))];
  }

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
  clearProceduralFallbackMotion();
  disposeFbxFallback();
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
  resetViewerCamera();
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

function resetViewerCamera() {
  if (fbxFallbackState?.controls) {
    fbxFallbackState.controls.reset();
    return;
  }

  const target = currentModel?.cameraTarget;
  if (Array.isArray(target) && target.length === 3 && target.every(Number.isFinite)) {
    viewer.cameraTarget = target.map(value => value.toFixed(4) + "m").join(" ");
  } else {
    viewer.cameraTarget = "auto auto auto";
  }

  viewer.cameraOrbit = "0deg 75deg auto";
  viewer.fieldOfView = (Number(currentModel?.fieldOfView) || 30) + "deg";
  viewer.jumpCameraToGoal?.();
}

function animationIdleScore(name) {
  const value = String(name || "").toLowerCase();
  let score = 0;

  if (/idle|wait|stand|breath|loop/.test(value)) score += 100;
  if (/fight[_ -]?a|battle[_ -]?a/.test(value)) score += 80;
  if (/default|base/.test(value)) score += 30;

  if (/attack|move|damage|hit|faint|die|death|sleep|eat|jump|run|walk|roar|cry|emote/.test(value)) score -= 100;
  if (/fight[_ -]?b|fight[_ -]?c|battle[_ -]?b|battle[_ -]?c/.test(value)) score -= 20;

  return score;
}

function chooseSafeIdle(animations) {
  if (!animations.length) return null;

  const ranked = [...animations]
    .map((name, index) => ({ name, index, score: animationIdleScore(name) }))
    .sort((a, b) => b.score - a.score || a.index - b.index);

  // Do not play an arbitrary clip just because it is the only one present.
  // Attack/damage/malformed clips were being mistaken for idles and could
  // stretch skinned meshes or leave Pokemon in obviously broken poses.
  return ranked[0].score >= 30 ? ranked[0].name : null;
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

async function pokeMinersTextureInventory(model) {
  const key = String(model?.dex || "");
  if (pokeMinersTextureInventoryCache.has(key)) {
    return pokeMinersTextureInventoryCache.get(key);
  }

  const dex = String(model.dex).padStart(4, "0");
  const folder = "pm" + dex + "_00_Rig";
  const api =
    "https://api.github.com/repos/PokeMiners/pogo_assets/contents/" +
    "3D%20Assets/Pokemon/" + folder + "?ref=master";

  const promise = fetch(api, { cache: "force-cache" })
    .then(response => {
      if (!response.ok) {
        throw new Error("Texture inventory HTTP " + response.status);
      }
      return response.json();
    })
    .then(items =>
      (Array.isArray(items) ? items : [])
        .filter(item => /\.(png|jpg|jpeg)$/i.test(String(item?.name || "")))
        .map(item => ({
          name: String(item.name),
          url:
            item.download_url ||
            ("https://cdn.jsdelivr.net/gh/PokeMiners/pogo_assets@master/" +
              "3D%20Assets/Pokemon/" + folder + "/" +
              encodeURIComponent(String(item.name))),
        }))
    )
    .catch(error => {
      console.warn("PokeMiners texture inventory unavailable:", error);
      return [];
    });

  pokeMinersTextureInventoryCache.set(key, promise);
  return promise;
}

function textureWords(value) {
  return new Set(
    String(value || "")
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter(word =>
        word.length >= 3 &&
        !["mat", "material", "mesh", "texture", "tex"].includes(word)
      )
  );
}

function textureMatchScore(entry, objectName, materialName) {
  const file = String(entry?.name || "").toLowerCase();
  const target = (String(objectName || "") + " " + String(materialName || "")).toLowerCase();
  let score = 0;

  const fileWords = textureWords(file);
  const targetWords = textureWords(target);
  for (const word of fileWords) {
    if (targetWords.has(word)) score += 18;
  }

  const tokens = [
    ["body", 90],
    ["eye", 140],
    ["face", 110],
    ["mouth", 120],
    ["wing", 100],
    ["fire", 140],
    ["flame", 140],
    ["leaf", 110],
    ["flower", 110],
    ["petal", 110],
    ["hair", 100],
    ["shell", 100],
    ["tail", 80],
  ];

  for (const [token, weight] of tokens) {
    if (target.includes(token) && file.includes(token)) score += weight;
    if (target.includes(token) && !file.includes(token)) score -= weight * 0.2;
  }

  // Most Pokemon use Body*, BodyAll*, BodyA*/BodyB* for their principal skin.
  if (/body/.test(file)) score += 12;
  if (/combo/.test(file) && !/fire|flame/.test(target)) score -= 25;

  return score;
}

async function loadThreeTexture(THREE, url) {
  const loader = new THREE.TextureLoader();
  loader.setCrossOrigin("anonymous");

  return await new Promise((resolve, reject) => {
    loader.load(
      url,
      texture => {
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.flipY = true;
        texture.wrapS = THREE.ClampToEdgeWrapping;
        texture.wrapT = THREE.ClampToEdgeWrapping;
        texture.needsUpdate = true;
        resolve(texture);
      },
      undefined,
      reject
    );
  });
}

async function bindPokeMinersTextures(THREE, rig, model) {
  const inventory = await pokeMinersTextureInventory(model);

  const bodyCandidates = inventory.filter(entry =>
    /body/i.test(entry.name) && !/shadow|mask|normal|spec/i.test(entry.name)
  );

  const textureCache = new Map();
  const getTexture = async entry => {
    if (!entry) return null;
    if (!textureCache.has(entry.url)) {
      textureCache.set(
        entry.url,
        loadThreeTexture(THREE, entry.url).catch(error => {
          console.warn("Texture failed:", entry.url, error);
          return null;
        })
      );
    }
    return textureCache.get(entry.url);
  };

  const assignments = [];

  rig.traverse(object => {
    if (!object.isMesh) return;

    const materials = Array.isArray(object.material)
      ? object.material
      : [object.material];

    materials.forEach((material, materialIndex) => {
      if (!material) return;

      // FBX materials can import as black when their external texture path
      // cannot be resolved. White is the neutral base for a color texture.
      material.color?.set?.(0xffffff);
      if ("emissive" in material) material.emissive?.set?.(0x000000);
      if ("roughness" in material) material.roughness = 0.75;
      if ("metalness" in material) material.metalness = 0;

      const ranked = [...inventory]
        .map(entry => ({
          entry,
          score: textureMatchScore(entry, object.name, material.name),
        }))
        .sort((a, b) => b.score - a.score);

      let chosen = ranked[0]?.score > 20 ? ranked[0].entry : null;

      if (!chosen && bodyCandidates.length === 1) {
        chosen = bodyCandidates[0];
      } else if (!chosen && bodyCandidates.length > 1) {
        // If the material gives us no useful clue, distribute BodyA/BodyB
        // textures across material slots rather than painting everything black.
        chosen = bodyCandidates[
          Math.min(materialIndex, bodyCandidates.length - 1)
        ];
      }

      if (!chosen) {
        material.needsUpdate = true;
        return;
      }

      assignments.push(
        getTexture(chosen).then(texture => {
          if (!texture) return;

          material.map = texture;
          material.color?.set?.(0xffffff);

          const low = chosen.name.toLowerCase();
          if (/eye|face|mouth|fire|flame|wing|leaf|petal/.test(low)) {
            material.transparent = true;
            material.alphaTest = 0.01;
            material.depthWrite = true;
          }

          material.needsUpdate = true;
        })
      );
    });
  });

  await Promise.allSettled(assignments);
}

function pokeMinersFbxUrl(model) {
  if (!model || String(model.form || "regular").toLowerCase() !== "regular") {
    return null;
  }

  const id = String(model.dex).padStart(4, "0");
  const base =
    "https://cdn.jsdelivr.net/gh/PokeMiners/pogo_assets@master/" +
    "3D%20Assets/Pokemon/pm" + id + "_00_Rig/";

  return base + "pm" + id + "_00_Rig.fbx";
}

async function getFbxRuntime() {
  if (!fbxRuntimePromise) {
    fbxRuntimePromise = Promise.all([
      import("https://esm.sh/three@0.180.0"),
      import("https://esm.sh/three@0.180.0/examples/jsm/loaders/FBXLoader.js"),
      import("https://esm.sh/three@0.180.0/examples/jsm/loaders/GLTFLoader.js"),
      import("https://esm.sh/three@0.180.0/examples/jsm/loaders/DRACOLoader.js"),
      import("https://esm.sh/three@0.180.0/examples/jsm/controls/OrbitControls.js"),
    ]).then(([THREE, fbxModule, gltfModule, dracoModule, controlsModule]) => ({
      THREE,
      FBXLoader: fbxModule.FBXLoader,
      GLTFLoader: gltfModule.GLTFLoader,
      DRACOLoader: dracoModule.DRACOLoader,
      OrbitControls: controlsModule.OrbitControls,
    }));
  }

  return fbxRuntimePromise;
}

function disposeMaterial(material) {
  if (!material) return;
  for (const value of Object.values(material)) {
    if (value && value.isTexture) value.dispose?.();
  }
  material.dispose?.();
}

function disposeFbxFallback() {
  ++fbxFallbackLoadToken;

  const state = fbxFallbackState;
  fbxFallbackState = null;

  if (state) {
    cancelAnimationFrame(state.frame || 0);
    state.resizeObserver?.disconnect?.();
    state.controls?.dispose?.();

    state.model?.traverse?.(object => {
      object.geometry?.dispose?.();
      if (Array.isArray(object.material)) {
        object.material.forEach(disposeMaterial);
      } else {
        disposeMaterial(object.material);
      }
    });

    state.draco?.dispose?.();
    state.renderer?.dispose?.();
    state.renderer?.domElement?.remove?.();
  }

  threeFallbackHost?.replaceChildren();
  threeFallbackHost?.classList.add("hidden");
  viewer.classList.remove("fallback-active");
}

function fbxBoneRole(name) {
  const value = String(name || "").toLowerCase();
  if (/head|face|skull/.test(value)) return "head";
  if (/neck/.test(value)) return "neck";
  if (/tail/.test(value)) return "tail";
  if (/wing|fin/.test(value)) return "wing";
  if (/ear|antenna|feel|horn|leaf|petal/.test(value)) return "appendage";
  if (/spine|chest|body|torso/.test(value)) return "torso";
  return null;
}

function chooseFbxProceduralBones(model) {
  const roles = new Map();
  const selected = [];
  const limits = {
    head: 1,
    neck: 1,
    torso: 2,
    tail: 2,
    wing: 2,
    appendage: 3,
  };

  const bones = [];
  model.traverse(object => {
    if (object.isBone) bones.push(object);
  });

  bones.sort((a, b) => {
    let da = 0;
    let db = 0;
    for (let p = a.parent; p; p = p.parent) da++;
    for (let p = b.parent; p; p = p.parent) db++;
    return da - db;
  });

  for (const bone of bones) {
    const role = fbxBoneRole(bone.name);
    if (!role) continue;

    const low = String(bone.name || "").toLowerCase();
    if (/end|tip|dummy|helper|\bik\b|ctrl/.test(low)) continue;

    const used = roles.get(role) || 0;
    if (used >= limits[role]) continue;

    selected.push({
      bone,
      role,
      base: bone.quaternion.clone(),
      index: selected.length,
    });
    roles.set(role, used + 1);
  }

  return selected;
}

function chooseEmbeddedFbxIdle(animations) {
  const names = animations.map(animation => animation.name || "");
  const chosen = chooseSafeIdle(names);
  return chosen
    ? animations.find(animation => animation.name === chosen) || null
    : null;
}

async function showRiggedGlbFallback(model) {
  if (!threeFallbackHost) return false;

  const source =
    activeModelCandidates[activeCandidateIndex] ||
    String(model?.url || "");

  if (!source) return false;

  const token = ++fbxFallbackLoadToken;
  messageEl.textContent = "Loading rigged GLB…";
  messageEl.classList.remove("hidden");

  try {
    const {
      THREE,
      GLTFLoader,
      DRACOLoader,
      OrbitControls,
    } = await getFbxRuntime();

    if (token !== fbxFallbackLoadToken) return false;

    disposeFbxFallback();
    const activeToken = ++fbxFallbackLoadToken;

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    threeFallbackHost.replaceChildren(renderer.domElement);
    threeFallbackHost.classList.remove("hidden");
    viewer.classList.add("fallback-active");

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 100);
    camera.position.set(0, 0.4, 4);

    scene.add(new THREE.HemisphereLight(0xffffff, 0x41516a, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(3, 5, 4);
    scene.add(key);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotate = autoRotate;
    controls.autoRotateSpeed = 1.5;

    const loader = new GLTFLoader();
    const draco = new DRACOLoader();
    draco.setDecoderPath(
      "https://www.gstatic.com/draco/versioned/decoders/1.5.7/"
    );
    loader.setDRACOLoader(draco);

    const gltf = await new Promise((resolve, reject) => {
      loader.load(source, resolve, undefined, reject);
    });

    if (activeToken !== fbxFallbackLoadToken) {
      draco.dispose?.();
      return false;
    }

    const rig = gltf.scene;
    const clips = Array.from(gltf.animations || []);

    scene.add(rig);

    rig.traverse(object => {
      if (!object.isMesh) return;
      object.castShadow = true;
      object.receiveShadow = true;

      const materials = Array.isArray(object.material)
        ? object.material
        : [object.material];

      for (const material of materials) {
        if (!material) continue;
        // Preserve the GLB material exactly. Only ensure maps use the expected
        // color space; unlike the FBX path, do not replace colors/textures.
        if (material.map) material.map.colorSpace = THREE.SRGBColorSpace;
        material.needsUpdate = true;
      }
    });

    const initialBox = new THREE.Box3().setFromObject(rig);
    const size = initialBox.getSize(new THREE.Vector3());
    const center = initialBox.getCenter(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z, 0.001);
    const scale = 2.25 / maxDimension;

    rig.scale.setScalar(scale);
    rig.position.x -= center.x * scale;
    rig.position.y -= center.y * scale;
    rig.position.z -= center.z * scale;

    const fittedBox = new THREE.Box3().setFromObject(rig);
    const fittedCenter = fittedBox.getCenter(new THREE.Vector3());
    const fittedSize = fittedBox.getSize(new THREE.Vector3());

    controls.target.copy(fittedCenter);
    camera.position.set(
      fittedCenter.x,
      fittedCenter.y + fittedSize.y * 0.06,
      fittedCenter.z + Math.max(fittedSize.z, fittedSize.y) * 1.8 + 1.4
    );
    camera.near = 0.01;
    camera.far = 100;
    camera.updateProjectionMatrix();
    controls.update();
    controls.saveState();

    const embeddedIdle = chooseEmbeddedFbxIdle(clips);
    const mixer = embeddedIdle ? new THREE.AnimationMixer(rig) : null;
    if (mixer && embeddedIdle) {
      mixer.clipAction(embeddedIdle).reset().play();
    }

    const proceduralBones = embeddedIdle ? [] : chooseFbxProceduralBones(rig);

    // If the optimized GLB has no bones at all, it cannot be skeletally
    // animated. Leave model-viewer visible instead of replacing a correct,
    // textured model with another rigid duplicate.
    if (!embeddedIdle && !proceduralBones.length) {
      scene.remove(rig);
      renderer.dispose();
      renderer.domElement.remove();
      draco.dispose?.();
      threeFallbackHost.replaceChildren();
      threeFallbackHost.classList.add("hidden");
      viewer.classList.remove("fallback-active");
      return false;
    }

    const baseY = rig.position.y;
    const clock = new THREE.Clock();
    const axisX = new THREE.Vector3(1, 0, 0);
    const axisY = new THREE.Vector3(0, 1, 0);
    const axisZ = new THREE.Vector3(0, 0, 1);
    const deltaQuaternion = new THREE.Quaternion();

    const roleMotion = {
      head: [axisX, THREE.MathUtils.degToRad(2.2)],
      neck: [axisX, THREE.MathUtils.degToRad(1.3)],
      torso: [axisY, THREE.MathUtils.degToRad(0.9)],
      tail: [axisZ, THREE.MathUtils.degToRad(4.0)],
      wing: [axisX, THREE.MathUtils.degToRad(2.5)],
      appendage: [axisY, THREE.MathUtils.degToRad(2.0)],
    };

    const state = {
      frame: 0,
      renderer,
      scene,
      camera,
      controls,
      model: rig,
      mixer,
      proceduralBones,
      resizeObserver: null,
      draco,
    };
    fbxFallbackState = state;

    const resize = () => {
      const width = Math.max(1, threeFallbackHost.clientWidth);
      const height = Math.max(1, threeFallbackHost.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    state.resizeObserver = new ResizeObserver(resize);
    state.resizeObserver.observe(threeFallbackHost);

    const render = () => {
      if (fbxFallbackState !== state) return;

      const delta = Math.min(clock.getDelta(), 0.05);
      const elapsed = clock.elapsedTime;

      if (mixer) {
        mixer.update(delta);
      } else {
        rig.position.y = baseY + Math.sin(elapsed * 2.0) * 0.008;

        for (const item of proceduralBones) {
          const motion = roleMotion[item.role];
          if (!motion) continue;

          const [axis, amplitude] = motion;
          const phase = item.index % 2 ? Math.PI : 0;
          const angle = Math.sin(elapsed * 1.45 + phase) * amplitude;

          deltaQuaternion.setFromAxisAngle(axis, angle);
          item.bone.quaternion.copy(item.base).multiply(deltaQuaternion);
        }
      }

      controls.autoRotate = autoRotate;
      controls.update();
      renderer.render(scene, camera);
      state.frame = requestAnimationFrame(render);
    };

    state.frame = requestAnimationFrame(render);

    messageEl.textContent = embeddedIdle
      ? "Loaded textured rigged GLB with embedded idle"
      : "Loaded textured rigged GLB with generated skeletal idle";

    setTimeout(() => {
      if (fbxFallbackState === state) messageEl.classList.add("hidden");
    }, 1000);

    toggleIdleBreaksBtn.disabled = true;
    toggleIdleBreaksBtn.textContent = "Idle breaks: Rigged idle";
    return true;
  } catch (error) {
    console.warn("Rigged GLB fallback failed:", error);
    if (token === fbxFallbackLoadToken) disposeFbxFallback();
    return false;
  }
}

async function showRiggedFbxFallback(model) {
  const url = pokeMinersFbxUrl(model);
  if (!url || !threeFallbackHost) return false;

  const token = ++fbxFallbackLoadToken;
  messageEl.textContent = "Loading rigged animated model…";
  messageEl.classList.remove("hidden");

  try {
    const { THREE, FBXLoader, OrbitControls } = await getFbxRuntime();
    if (token !== fbxFallbackLoadToken) return false;

    disposeFbxFallback();
    const activeToken = ++fbxFallbackLoadToken;

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    threeFallbackHost.replaceChildren(renderer.domElement);
    threeFallbackHost.classList.remove("hidden");
    viewer.classList.add("fallback-active");

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 100);
    camera.position.set(0, 0.4, 4);

    scene.add(new THREE.HemisphereLight(0xffffff, 0x41516a, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 3.0);
    key.position.set(3, 5, 4);
    key.castShadow = true;
    scene.add(key);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotate = autoRotate;
    controls.autoRotateSpeed = 1.5;

    const manager = new THREE.LoadingManager();
    const baseUrl = url.slice(0, url.lastIndexOf("/") + 1);
    manager.setURLModifier(resource => {
      const clean = String(resource || "").split("?")[0];
      const file = clean.split(/[\\/]/).pop();
      if (!file || !/\.(png|jpg|jpeg|webp)$/i.test(file)) return resource;
      return baseUrl + encodeURIComponent(decodeURIComponent(file));
    });

    const loader = new FBXLoader(manager);
    loader.setCrossOrigin("anonymous");

    const rig = await new Promise((resolve, reject) => {
      loader.load(url, resolve, undefined, reject);
    });

    await bindPokeMinersTextures(THREE, rig, model);

    if (activeToken !== fbxFallbackLoadToken) {
      rig.traverse?.(object => object.geometry?.dispose?.());
      return false;
    }

    rig.traverse(object => {
      if (object.isMesh) {
        object.castShadow = true;
        object.receiveShadow = true;

        const materials = Array.isArray(object.material)
          ? object.material
          : [object.material];
        for (const material of materials) {
          if (!material) continue;
          if ("transparent" in material && material.map) {
            material.transparent = true;
            material.alphaTest = Math.max(Number(material.alphaTest) || 0, 0.01);
          }
        }
      }
    });

    scene.add(rig);

    const initialBox = new THREE.Box3().setFromObject(rig);
    const size = initialBox.getSize(new THREE.Vector3());
    const center = initialBox.getCenter(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z, 0.001);
    const scale = 2.25 / maxDimension;

    rig.scale.setScalar(scale);
    rig.position.x -= center.x * scale;
    rig.position.y -= center.y * scale;
    rig.position.z -= center.z * scale;

    const fittedBox = new THREE.Box3().setFromObject(rig);
    const fittedCenter = fittedBox.getCenter(new THREE.Vector3());
    const fittedSize = fittedBox.getSize(new THREE.Vector3());

    controls.target.copy(fittedCenter);
    camera.position.set(
      fittedCenter.x,
      fittedCenter.y + fittedSize.y * 0.06,
      fittedCenter.z + Math.max(fittedSize.z, fittedSize.y) * 1.8 + 1.4
    );
    camera.near = 0.01;
    camera.far = 100;
    camera.updateProjectionMatrix();
    controls.update();
    controls.saveState();

    const embeddedIdle = chooseEmbeddedFbxIdle(Array.from(rig.animations || []));
    const mixer = embeddedIdle ? new THREE.AnimationMixer(rig) : null;
    if (mixer && embeddedIdle) {
      mixer.clipAction(embeddedIdle).reset().play();
    }

    const proceduralBones = embeddedIdle ? [] : chooseFbxProceduralBones(rig);
    const baseY = rig.position.y;
    const clock = new THREE.Clock();
    const axisX = new THREE.Vector3(1, 0, 0);
    const axisY = new THREE.Vector3(0, 1, 0);
    const axisZ = new THREE.Vector3(0, 0, 1);
    const deltaQuaternion = new THREE.Quaternion();

    const roleMotion = {
      head: [axisX, THREE.MathUtils.degToRad(2.2)],
      neck: [axisX, THREE.MathUtils.degToRad(1.3)],
      torso: [axisY, THREE.MathUtils.degToRad(0.9)],
      tail: [axisZ, THREE.MathUtils.degToRad(4.0)],
      wing: [axisX, THREE.MathUtils.degToRad(2.5)],
      appendage: [axisY, THREE.MathUtils.degToRad(2.0)],
    };

    const state = {
      frame: 0,
      renderer,
      scene,
      camera,
      controls,
      model: rig,
      mixer,
      proceduralBones,
      resizeObserver: null,
    };
    fbxFallbackState = state;

    const resize = () => {
      const width = Math.max(1, threeFallbackHost.clientWidth);
      const height = Math.max(1, threeFallbackHost.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    state.resizeObserver = new ResizeObserver(resize);
    state.resizeObserver.observe(threeFallbackHost);

    const render = () => {
      if (fbxFallbackState !== state) return;

      const delta = Math.min(clock.getDelta(), 0.05);
      const elapsed = clock.elapsedTime;

      if (mixer) {
        mixer.update(delta);
      } else {
        rig.position.y = baseY + Math.sin(elapsed * 2.0) * 0.008;

        for (const item of proceduralBones) {
          const motion = roleMotion[item.role];
          if (!motion) continue;

          const [axis, amplitude] = motion;
          const phase = item.index % 2 ? Math.PI : 0;
          const angle = Math.sin(elapsed * 1.45 + phase) * amplitude;

          deltaQuaternion.setFromAxisAngle(axis, angle);
          item.bone.quaternion.copy(item.base).multiply(deltaQuaternion);
        }
      }

      controls.autoRotate = autoRotate;
      controls.update();
      renderer.render(scene, camera);
      state.frame = requestAnimationFrame(render);
    };

    state.frame = requestAnimationFrame(render);

    messageEl.textContent = embeddedIdle
      ? "Loaded rigged model with embedded idle"
      : "Loaded rigged model with generated skeletal idle";
    setTimeout(() => {
      if (fbxFallbackState === state) messageEl.classList.add("hidden");
    }, 1000);

    toggleIdleBreaksBtn.disabled = true;
    toggleIdleBreaksBtn.textContent = "Idle breaks: Rigged idle";
    return true;
  } catch (error) {
    console.warn("Rigged PokeMiners fallback failed:", error);
    if (token === fbxFallbackLoadToken) {
      disposeFbxFallback();
    }
    return false;
  }
}

function clearProceduralFallbackMotion() {
  if (proceduralFallbackFrame !== null) {
    cancelAnimationFrame(proceduralFallbackFrame);
    proceduralFallbackFrame = null;
  }

  proceduralFallbackStartedAt = 0;
  viewer.orientation = "0deg 0deg 0deg";
}

function startProceduralFallbackMotion() {
  clearProceduralFallbackMotion();

  // Some upstream GLBs contain a rigged or posed Pokemon but zero animation
  // tracks. Keep those entries visibly alive instead of leaving a frozen bind
  // pose while the higher-quality PokeMiners animation backfill is generated.
  proceduralFallbackStartedAt = performance.now();

  const tick = now => {
    if (!viewer.loaded || idleAnimation) {
      clearProceduralFallbackMotion();
      return;
    }

    const seconds = (now - proceduralFallbackStartedAt) / 1000;
    const sway = Math.sin(seconds * 1.7) * 2.4;
    const lean = Math.sin(seconds * 0.85 + 0.8) * 0.8;

    // model-viewer applies orientation to the model itself, so this is genuine
    // visible model motion rather than moving the page or camera.
    viewer.orientation =
      lean.toFixed(2) + "deg " +
      sway.toFixed(2) + "deg 0deg";

    proceduralFallbackFrame = requestAnimationFrame(tick);
  };

  proceduralFallbackFrame = requestAnimationFrame(tick);
}

function startBaseIdle() {
  if (!idleAnimation) {
    startProceduralFallbackMotion();
    return;
  }

  clearProceduralFallbackMotion();
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
  clearProceduralFallbackMotion();

  const animations = Array.from(viewer.availableAnimations || []);
  animationDurations = readAnimationDurations();

  // Prefer verified importer metadata. Only use a heuristic clip when its
  // name strongly resembles an idle. Never fall back to an arbitrary clip.
  const manifestIdle = currentModel?.idleAnimation;
  idleAnimation =
    manifestIdle && animations.includes(manifestIdle)
      ? manifestIdle
      : chooseSafeIdle(animations);

  const manifestBreaks = Array.isArray(currentModel?.idleBreaks)
    ? currentModel.idleBreaks
    : [];

  const overrideNames =
    manifestBreaks.length
      ? manifestBreaks
      : (IDLE_BREAK_OVERRIDES[currentModel?.dex] || []);

  breakAnimations = overrideNames.filter(name =>
    animations.includes(name) && name !== idleAnimation
  );

  if (idleAnimation) {
    clearProceduralFallbackMotion();
    viewer.animationName = idleAnimation;
    viewer.currentTime = 0;
    viewer.play();
  } else {
    viewer.pause?.();
    startProceduralFallbackMotion();
  }

  const available = Boolean(idleAnimation && breakAnimations.length);
  toggleIdleBreaksBtn.disabled = !available;
  toggleIdleBreaksBtn.textContent = available
    ? "Idle breaks: " + (idleBreaksEnabled ? "On" : "Off")
    : "Idle breaks: Unavailable";

  if (available && idleBreaksEnabled) {
    scheduleNextIdleBreak();
  }
}

viewer.addEventListener("load", async () => {
  clearModelLoadTimeout();

  const availableAnimations = Array.from(viewer.availableAnimations || []);

  // A successfully decoded GLB can still be an unanimated bind pose. For
  // regular forms, prefer the public rigged PokeMiners FBX and animate its
  // skeleton directly in-browser. This avoids shipping hundreds of generated
  // GLBs just to give static Pokemon a natural idle.
  if (!chooseSafeIdle(availableAnimations) && !availableAnimations.includes(currentModel?.idleAnimation)) {
    const request = modelLoadRequest;
    const rigged = await showRiggedGlbFallback(currentModel);
    if (request !== modelLoadRequest || rigged) return;

    if (activeCandidateIndex + 1 < activeModelCandidates.length) {
      console.warn(
        "Loaded model has no animation clips; trying another source:",
        activeModelCandidates[activeCandidateIndex]
      );
      startModelCandidate(activeCandidateIndex + 1);
      return;
    }
  }

  disposeFbxFallback();

  formEl.textContent = prettyForm(currentModel.form) +
    (/\/(?:models|offline)\/switch\//.test(activeModelCandidates[activeCandidateIndex]) ? " · Switch assets" : "");
  const elapsed = Math.max(0, performance.now() - loadStartedAt);
  messageEl.textContent =
    "Loaded in " + (elapsed / 1000).toFixed(1) + "s";
  setTimeout(() => messageEl.classList.add("hidden"), 900);

  resetViewerCamera();
  setupIdleBreakAnimations();
  prefetchNeighbors();
});

viewer.addEventListener("error", event => {
  clearProceduralFallbackMotion();
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
    if (location.protocol !== "file:") {
      ModelViewerElement.dracoDecoderLocation = new URL("web/vendor/draco/", location.href).href;
    }
    ModelViewerElement.minimumRenderScale = 1;
    ModelViewerElement.modelCacheSize = 8;
  }

  selectModel(0);
  enhanceCatalogInBackground();
});
