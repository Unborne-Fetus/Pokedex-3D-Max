const API_URL = "https://pokemon-3d-api.onrender.com/v1/pokemon";
const REGULAR_FALLBACK = id =>
  `https://raw.githubusercontent.com/Pokemon-3D-api/assets/main/models/opt/regular/${id}.glb`;

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

let models = [];
let filtered = [];
let selectedIndex = 0;
let autoRotate = false;

function normalizeUrl(url) {
  return String(url || "")
    .replace("/refs/heads/main/heads/main/", "/refs/heads/main/")
    .replace("/main/heads/main/", "/main/");
}

function normalizeCatalog(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.pokemon)) return payload.pokemon;
  if (Array.isArray(payload?.data)) return payload.data;
  throw new Error("Unsupported catalog JSON format");
}

async function loadCatalog() {
  statusEl.textContent = "Loading 3D catalog…";

  try {
    const response = await fetch(API_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`Catalog HTTP ${response.status}`);

    const payload = await response.json();
    const pokemon = normalizeCatalog(payload);
    const out = [];

    for (const entry of pokemon) {
      const dex = Number(entry.id);
      const forms = Array.isArray(entry.forms) ? entry.forms : [];

      for (const form of forms) {
        const url = normalizeUrl(form.model);
        if (!url) continue;

        out.push({
          dex,
          name: form.name || `#${String(dex).padStart(4, "0")}`,
          form: form.formName || "regular",
          url,
        });
      }
    }

    if (!out.length) throw new Error("Catalog contained no model entries");

    models = out
      .filter((m, i, arr) =>
        arr.findIndex(x => x.dex === m.dex && x.form === m.form && x.url === m.url) === i
      )
      .sort((a, b) => a.dex - b.dex || formRank(a.form) - formRank(b.form) || a.form.localeCompare(b.form));

    statusEl.textContent = `${models.length.toLocaleString()} 3D models available`;
  } catch (error) {
    console.warn("Catalog failed, using regular-form fallback:", error);
    models = Array.from({ length: 1025 }, (_, i) => {
      const dex = i + 1;
      return {
        dex,
        name: `#${String(dex).padStart(4, "0")}`,
        form: "regular",
        url: REGULAR_FALLBACK(dex),
      };
    });
    statusEl.textContent = "Catalog unavailable · using 1,025 regular-form fallback paths";
  }

  applyFilter();
  selectModel(0);
}

function formRank(form) {
  const value = form.toLowerCase();
  if (value === "regular") return 0;
  if (value.includes("shiny")) return 2;
  return 1;
}

function applyFilter() {
  const q = searchEl.value.trim().toLowerCase().replace(/^#/, "");

  filtered = q
    ? models.filter(m =>
        String(m.dex) === q ||
        m.name.toLowerCase().includes(q) ||
        m.form.toLowerCase().includes(q)
      )
    : models;

  renderList();
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
    button.innerHTML = `
      <span class="dex">#${String(model.dex).padStart(4, "0")}</span>
      <span>
        <span class="name">${escapeHtml(model.name)}</span><br />
        <span class="form">${escapeHtml(prettyForm(model.form))}</span>
      </span>
    `;
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

  dexEl.textContent = `#${String(model.dex).padStart(4, "0")}`;
  nameEl.textContent = model.name;
  formEl.textContent = prettyForm(model.form);

  populateFormSelect(model);
  loadModel(model);
  updateSelectedRow();
}

function loadModel(model) {
  messageEl.textContent = "Loading model…";
  messageEl.classList.remove("hidden");

  viewer.removeAttribute("src");
  viewer.src = model.url;
  viewer.alt = `3D model of ${model.name}, ${prettyForm(model.form)} form`;

  // Let <model-viewer> frame the actual model bounds rather than reusing the prior camera.
  viewer.cameraOrbit = "auto auto auto";
  viewer.cameraTarget = "auto auto auto";
  viewer.fieldOfView = "30deg";
  viewer.jumpCameraToGoal?.();
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
  applyFilter();
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
    dexEl.textContent = `#${String(target.dex).padStart(4, "0")}`;
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
  toggleRotateBtn.textContent = `Auto-rotate: ${autoRotate ? "On" : "Off"}`;
});

viewer.addEventListener("load", () => {
  messageEl.classList.add("hidden");
  viewer.cameraOrbit = "auto auto auto";
  viewer.cameraTarget = "auto auto auto";
  viewer.jumpCameraToGoal?.();
});

viewer.addEventListener("error", event => {
  console.error("Model load error", event);
  messageEl.textContent = "Model failed to load";
  messageEl.classList.remove("hidden");
});

viewer.addEventListener("progress", event => {
  const progress = Number(event.detail?.totalProgress || 0);
  const fill = viewer.querySelector(".progress-fill");
  if (fill) fill.style.width = `${Math.round(progress * 100)}%`;
});

loadCatalog();
