window.__pokedex3dBooted = true;

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

const models = (Array.isArray(window.POKEDEX3D_SWITCH_MODELS)
  ? window.POKEDEX3D_SWITCH_MODELS
  : [])
  .filter(model => model?.valid !== false && model?.ready !== false)
  .filter(model => String(model?.form || "regular").toLowerCase() === "regular")
  .filter(model => String(model?.url || "").replaceAll("\\", "/").includes("/switch/"))
  .sort((a, b) => Number(a.dex) - Number(b.dex));

window.POKEDEX3D_MODELS = models;

let filtered = [...models];
let selectedIndex = 0;
let currentModel = null;
let autoRotate = false;
let idleBreaksEnabled = true;
let idleAnimation = null;
let playingBreak = false;
let breakTimer = null;
let loadTimer = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function prettyName(model) {
  const known = String(model?.name || "").trim();
  return known || ("#" + String(model?.dex || 0).padStart(4, "0"));
}

function clearBreakTimer() {
  if (breakTimer !== null) {
    clearTimeout(breakTimer);
    breakTimer = null;
  }
}

function clearLoadTimer() {
  if (loadTimer !== null) {
    clearTimeout(loadTimer);
    loadTimer = null;
  }
}

function animationScore(name) {
  const value = String(name || "").toLowerCase();
  let score = 0;
  if (/idle|wait|stand|breath|loop/.test(value)) score += 100;
  if (/fight[_ -]?a|battle[_ -]?a/.test(value)) score += 80;
  if (/default|base/.test(value)) score += 30;
  if (/attack|move|damage|hit|faint|die|death|sleep|eat|jump|run|walk|roar|cry/.test(value)) score -= 100;
  return score;
}

function availableAnimations() {
  return Array.from(viewer.availableAnimations || []).filter(Boolean);
}

function chooseIdle(model, animations) {
  if (model?.idleAnimation && animations.includes(model.idleAnimation)) {
    return model.idleAnimation;
  }
  const ranked = animations
    .map((name, index) => ({ name, index, score: animationScore(name) }))
    .sort((a, b) => b.score - a.score || a.index - b.index);
  return ranked.length && ranked[0].score >= 30 ? ranked[0].name : null;
}

function startIdle() {
  const animations = availableAnimations();
  idleAnimation = chooseIdle(currentModel, animations);
  playingBreak = false;

  if (!idleAnimation) {
    messageEl.textContent = "Switch model loaded, but no verified idle animation is available.";
    messageEl.classList.remove("hidden");
    return;
  }

  viewer.animationName = idleAnimation;
  viewer.currentTime = 0;
  viewer.play();
}

function verifiedBreaks() {
  if (!currentModel) return [];
  const available = new Set(availableAnimations());
  return (Array.isArray(currentModel.idleBreaks) ? currentModel.idleBreaks : [])
    .filter(name => name && name !== idleAnimation && available.has(name));
}

function scheduleIdleBreak() {
  clearBreakTimer();
  if (!idleBreaksEnabled || document.hidden || !idleAnimation) return;

  const breaks = verifiedBreaks();
  if (!breaks.length) return;

  breakTimer = setTimeout(() => {
    if (!idleBreaksEnabled || document.hidden || !viewer.loaded) {
      scheduleIdleBreak();
      return;
    }
    const clip = breaks[Math.floor(Math.random() * breaks.length)];
    playingBreak = true;
    viewer.animationName = clip;
    viewer.currentTime = 0;
    viewer.play({ repetitions: 1 });
  }, 9000 + Math.floor(Math.random() * 6000));
}

function resetCamera() {
  const target = currentModel?.cameraTarget;
  viewer.cameraTarget =
    Array.isArray(target) && target.length === 3
      ? target.map(value => Number(value).toFixed(4) + "m").join(" ")
      : "auto auto auto";
  // theta is measured down from +Y: 65deg positions the camera 25deg ABOVE
  // the Pokemon. A 20deg yaw gives a natural three-quarter front view.
  viewer.cameraOrbit = "20deg 65deg auto";
  viewer.fieldOfView = (Number(currentModel?.fieldOfView) || 30) + "deg";
  viewer.jumpCameraToGoal?.();
}

function populateFormSelect(model) {
  formSelect.replaceChildren();
  const option = document.createElement("option");
  option.value = model.url;
  option.textContent = "Regular";
  option.selected = true;
  formSelect.appendChild(option);
  formSelect.disabled = true;
}

function updateSelectedRow() {
  listEl.querySelectorAll(".entry").forEach((node, index) => {
    node.classList.toggle("selected", index === selectedIndex);
  });
  listEl.querySelector(".entry.selected")?.scrollIntoView({ block: "nearest" });
}

function renderList() {
  listEl.replaceChildren();
  const fragment = document.createDocumentFragment();

  filtered.forEach((model, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "entry";
    button.innerHTML =
      '<span class="dex">#' + String(model.dex).padStart(4, "0") + '</span>' +
      '<span><span class="name">' + escapeHtml(prettyName(model)) + "</span></span>";
    button.addEventListener("click", () => selectModel(index));
    fragment.appendChild(button);
  });

  listEl.appendChild(fragment);
  updateSelectedRow();
}

function loadModel(model) {
  clearBreakTimer();
  clearLoadTimer();
  playingBreak = false;
  idleAnimation = null;
  currentModel = model;

  const url = String(model?.url || "");
  if (!url || !url.replaceAll("\\", "/").includes("/switch/")) {
    messageEl.textContent = "Blocked non-Switch model source.";
    messageEl.classList.remove("hidden");
    viewer.removeAttribute("src");
    return;
  }

  messageEl.textContent = "Loading original Switch model…";
  messageEl.classList.remove("hidden");
  viewer.removeAttribute("src");
  viewer.src = url;
  viewer.alt = "3D Switch model of " + prettyName(model);

  loadTimer = setTimeout(() => {
    messageEl.textContent = "Switch model failed to load. No fallback model was substituted.";
    messageEl.classList.remove("hidden");
  }, 15000);
}

function selectModel(index) {
  if (!filtered.length) return;
  selectedIndex = Math.max(0, Math.min(index, filtered.length - 1));
  const model = filtered[selectedIndex];

  dexEl.textContent = "#" + String(model.dex).padStart(4, "0");
  nameEl.textContent = prettyName(model);
  formEl.textContent = "Regular";
  populateFormSelect(model);
  loadModel(model);
  updateSelectedRow();
}

function applyFilter(loadFirst = true) {
  const query = searchEl.value.trim().toLowerCase().replace(/^#/, "");
  filtered = query
    ? models.filter(model =>
        String(model.dex) === query ||
        prettyName(model).toLowerCase().includes(query)
      )
    : [...models];

  selectedIndex = 0;
  renderList();
  if (loadFirst && filtered.length) selectModel(0);
}

viewer.addEventListener("load", () => {
  clearLoadTimer();
  resetCamera();
  startIdle();
  if (idleAnimation) {
    messageEl.classList.add("hidden");
    scheduleIdleBreak();
  }
});

viewer.addEventListener("error", () => {
  clearLoadTimer();
  clearBreakTimer();
  messageEl.textContent = "Switch model could not be rendered. No alternate model source was used.";
  messageEl.classList.remove("hidden");
});

viewer.addEventListener("finished", () => {
  if (!playingBreak) return;
  startIdle();
  scheduleIdleBreak();
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    clearBreakTimer();
  } else {
    scheduleIdleBreak();
  }
});

searchEl.addEventListener("input", () => applyFilter(true));

prevBtn.addEventListener("click", () => {
  if (!filtered.length) return;
  selectModel((selectedIndex - 1 + filtered.length) % filtered.length);
});

nextBtn.addEventListener("click", () => {
  if (!filtered.length) return;
  selectModel((selectedIndex + 1) % filtered.length);
});

resetCameraBtn.addEventListener("click", resetCamera);

toggleRotateBtn.addEventListener("click", () => {
  autoRotate = !autoRotate;
  viewer.autoRotate = autoRotate;
  toggleRotateBtn.textContent = "Auto-rotate: " + (autoRotate ? "On" : "Off");
});

toggleIdleBreaksBtn.addEventListener("click", () => {
  idleBreaksEnabled = !idleBreaksEnabled;
  toggleIdleBreaksBtn.textContent = "Idle breaks: " + (idleBreaksEnabled ? "On" : "Off");
  clearBreakTimer();
  if (!playingBreak) startIdle();
  if (idleBreaksEnabled) scheduleIdleBreak();
});

statusEl.textContent = models.length
  ? models.length.toLocaleString() + " regular animated Switch models ready"
  : "No validated Switch models installed — run setup-all.bat full";

renderList();
if (models.length) {
  selectModel(0);
} else {
  formSelect.replaceChildren();
  formSelect.disabled = true;
  messageEl.textContent = "No validated regular Switch models are installed.";
  messageEl.classList.remove("hidden");
}
