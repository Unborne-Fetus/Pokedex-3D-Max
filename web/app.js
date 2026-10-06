window.__pokedex3dBooted = true;\nconst API_URL = "https://pokemon-3d-api.onrender.com/v1/pokemon";
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

let models = makeInstantRegularCatalog();
let filtered = models;
let selectedIndex = 0;
let autoRotate = false;
let currentUrl = "";
let loadStartedAt = 0;
const warmed = new Set();

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
        applyFilter(false);
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
    applyFilter(false);
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

function formRank(form) {
  const value = String(form || "").toLowerCase();
  if (value === "regular") return 0;
  if (value.includes("shiny")) return 2;
  return 1;
}

function applyFilter(loadFirst = true) {
  const q = searchEl.value.trim().toLowerCase().replace(/^#/, "");

  filtered = q
    ? models.filter(m =>
        String(m.dex) === q ||
        m.name.toLowerCase().includes(q) ||
        m.form.toLowerCase().includes(q)
      )
    : models;

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

async function loadModel(model) {
  const url = toFastAssetUrl(model.url);
  if (url === currentUrl && viewer.loaded) return;

  currentUrl = url;
  loadStartedAt = performance.now();

  messageEl.textContent = "Loading 3D model…";
  messageEl.classList.remove("hidden");

  viewer.removeAttribute("src");
  viewer.src = url;
  viewer.alt =
    "3D model of " + model.name + ", " + prettyForm(model.form) + " form";
  viewer.cameraOrbit = "auto auto auto";
  viewer.cameraTarget = "auto auto auto";
  viewer.fieldOfView = "30deg";
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
    option.textContent = prettyForm(form.form);
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
  viewer.fieldOfView = "30deg";
  viewer.jumpCameraToGoal?.();
});

toggleRotateBtn.addEventListener("click", () => {
  autoRotate = !autoRotate;
  viewer.autoRotate = autoRotate;
  toggleRotateBtn.textContent =
    "Auto-rotate: " + (autoRotate ? "On" : "Off");
});

viewer.addEventListener("load", () => {
  const elapsed = Math.max(0, performance.now() - loadStartedAt);
  messageEl.textContent =
    "Loaded in " + (elapsed / 1000).toFixed(1) + "s";
  setTimeout(() => messageEl.classList.add("hidden"), 900);

  viewer.cameraOrbit = "auto auto auto";
  viewer.cameraTarget = "auto auto auto";
  viewer.jumpCameraToGoal?.();

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
  selectModel(0);
  enhanceCatalogInBackground();
});
