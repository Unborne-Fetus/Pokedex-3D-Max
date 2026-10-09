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
const repairTexturesBtn = document.querySelector("#repairTextures");
const repairPanel = document.querySelector("#repairPanel");
const repairTitle = document.querySelector("#repairTitle");
const repairSummary = document.querySelector("#repairSummary");
const repairLog = document.querySelector("#repairLog");
const closeRepairBtn = document.querySelector("#closeRepair");
const chooseLocalModelsBtn = document.querySelector("#chooseLocalModels");
const localModelsFolder = document.querySelector("#localModelsFolder");
const folderStatus = document.querySelector("#folderStatus");


let models = (Array.isArray(window.POKEDEX3D_SWITCH_MODELS)
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
let repairPollTimer = null;
let repairInProgress = false;
let activeObjectUrl = null;
let localFolderActive = false;


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

  const catalogUrl = String(model?.url || "");
  const fromLocalFolder = typeof File !== "undefined" && model?.file instanceof File;
  const fromRemoteManifest = model?.remoteSwitch === true
    && /^https:\/\/[^/]+\/(?:.*\/)?\d{4}\/regular\.glb$/.test(catalogUrl);
  if (!catalogUrl || (!catalogUrl.replaceAll("\\", "/").includes("/switch/") && !fromRemoteManifest)) {
    messageEl.textContent = "Blocked non-Switch model source.";
    messageEl.classList.remove("hidden");
    viewer.removeAttribute("src");
    return;
  }

  messageEl.textContent = "Loading original Switch model…";
  messageEl.classList.remove("hidden");
  viewer.removeAttribute("src");
  if (activeObjectUrl) {
    URL.revokeObjectURL(activeObjectUrl);
    activeObjectUrl = null;
  }
  if (fromLocalFolder) {
    activeObjectUrl = URL.createObjectURL(model.file);
    viewer.src = activeObjectUrl;
  } else {
    viewer.src = catalogUrl;
  }
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


// Original Switch shader texture repair: works in the local launch-index.bat
// server only. A plain file:// index cannot run local Python/Blender commands.
function openRepairPanel() {
  repairPanel.classList.remove("hidden");
}

function stopRepairPolling() {
  if (repairPollTimer !== null) {
    clearTimeout(repairPollTimer);
    repairPollTimer = null;
  }
}

function isLocalIndexServer() {
  return location.protocol === "http:" && location.hostname === "127.0.0.1";
}

async function pollRepairStatus(showPanel = true) {
  stopRepairPolling();
  if (!isLocalIndexServer()) {
    repairTexturesBtn.title = "Open launch-index.bat to repair original textures";
    return;
  }
  try {
    const reply = await fetch("/__pokedex3d/repair-status", { cache: "no-store" });
    if (!reply.ok) throw Error("The local launcher does not support texture repair yet");
    const info = await reply.json();
    repairInProgress = Boolean(info.running);
    repairTexturesBtn.disabled = repairInProgress || !info.available;
    repairTexturesBtn.textContent = repairInProgress ? "Repairing…" : "Repair textures";
    if (!info.available) {
      repairTexturesBtn.title = "Texture repair requires the updated launch-index.bat and project scripts on Windows";
    }
    if (showPanel || repairInProgress) {
      openRepairPanel();
      repairLog.textContent = info.logTail || (repairInProgress ? "Starting texture rebuild…" : "No repair has run yet.");
      if (repairInProgress) {
        repairTitle.textContent = "Repairing original Switch textures…";
        repairSummary.textContent = "This may take a while. Keep launch-index.bat open. Your original models are preserved until replacements pass validation.";
        repairPollTimer = setTimeout(() => pollRepairStatus(true), 1800);
      } else if (info.finished && info.exitCode === 0) {
        repairTitle.textContent = "Texture rebuild complete";
        repairSummary.textContent = "Refresh the page to load the repaired Switch models. No EXE build is required.";
      } else if (info.finished) {
        repairTitle.textContent = "Texture repair stopped";
        repairSummary.textContent = (info.error || "The rebuild did not complete. Existing model files were kept where possible.") + " Review the log below.";
      } else {
        repairTitle.textContent = "Original Switch texture repair";
        repairSummary.textContent = "This will rebuild original shader colors without downloading replacement models.";
      }
    }
  } catch (error) {
    repairInProgress = false;
    repairTexturesBtn.disabled = false;
    repairTexturesBtn.title = "An updated launch-index.bat is needed to use this feature";
    if (showPanel) {
      openRepairPanel();
      repairTitle.textContent = "Repair not available in this launcher";
      repairSummary.textContent = "Open the updated launch-index.bat with the full project files. No terminal or EXE is required.";
      repairLog.textContent = String(error.message || error);
    }
  }
}

repairTexturesBtn.addEventListener("click", async () => {
  if (!isLocalIndexServer()) {
    openRepairPanel();
    repairTitle.textContent = "Use launch-index.bat";
    repairSummary.textContent = "The raw index.html cannot modify local model files. Open launch-index.bat from the updated project folder.";
    repairLog.textContent = "Your existing Switch models have not been changed.";
    return;
  }
  if (repairInProgress) {
    await pollRepairStatus(true);
    return;
  }
  if (!window.confirm(
    "Rebuild original Switch shader colors and fix opaque-body transparency?\n\n" +
    "This may take a long time. Keep launch-index.bat open. Existing models stay until replacements validate.\n\nStart repair?"
  )) return;

  repairTexturesBtn.disabled = true;
  openRepairPanel();
  repairTitle.textContent = "Starting original Switch texture rebuild…";
  repairSummary.textContent = "Please keep launch-index.bat open while the repair runs.";
  repairLog.textContent = "Preparing…";
  try {
    const reply = await fetch("/__pokedex3d/repair-textures", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const info = await reply.json();
    if (!reply.ok) throw Error(info.error || "Failed to start texture repair");
    repairInProgress = true;
    await pollRepairStatus(true);
  } catch (error) {
    repairInProgress = false;
    repairTexturesBtn.disabled = false;
    repairTitle.textContent = "Could not start texture repair";
    repairSummary.textContent = String(error.message || error);
    repairLog.textContent = "Previously imported Switch models remain available.";
  }
});

closeRepairBtn.addEventListener("click", () => {
  repairPanel.classList.add("hidden");
  // A running repair continues in the local launcher when panel is closed.
});

if (isLocalIndexServer()) {
  pollRepairStatus(false);
}


// A separately hosted verified Switch catalog can fill an otherwise empty
// static page. The configured source is disabled while its GitHub repo remains
// private; visitors are never asked for personal GitHub credentials.
window.addEventListener("pokedex3d:remote-switch-catalog", event => {
  if (localFolderActive || models.length) return;
  const incoming = Array.isArray(event.detail?.models) ? event.detail.models : [];
  if (!incoming.length) return;
  models = incoming;
  filtered = [...models];
  selectedIndex = 0;
  searchEl.value = "";
  window.POKEDEX3D_MODELS = models;
  folderStatus.textContent = "Verified hosted Switch models loaded.";
  statusEl.textContent = models.length.toLocaleString() + " hosted Switch models ready";
  renderList();
  selectModel(0);
});
window.addEventListener("pokedex3d:remote-switch-error", event => {
  if (models.length || localFolderActive) return;
  folderStatus.textContent = "Hosted model catalog unavailable: " +
    String(event.detail?.message || "unknown error") + ". You can still open a local folder.";
});

// Static site mode: open already-converted models directly from the visitor's
// device. File selections never leave the browser; no Python or local server.
chooseLocalModelsBtn.addEventListener("click", () => localModelsFolder.click());
localModelsFolder.addEventListener("change", async () => {
  if (!localModelsFolder.files?.length) return;
  chooseLocalModelsBtn.disabled = true;
  folderStatus.textContent = "Checking original Switch models and animations…";
  try {
    const outcome = await window.POKEDEX3D_LOCAL_SWITCH.fromFiles(
      localModelsFolder.files,
      (done, total, good) => {
        folderStatus.textContent = "Checking " + done + "/" + total +
          " models · " + good + " verified";
      }
    );
    if (!outcome.models.length) {
      folderStatus.textContent =
        "No verified regular Switch GLBs found. Choose the offline-models or web/models folder containing switch/0001/regular.glb.";
      return;
    }
    if (activeObjectUrl) {
      viewer.removeAttribute("src");
      URL.revokeObjectURL(activeObjectUrl);
      activeObjectUrl = null;
    }
    localFolderActive = true;
    models = outcome.models;
    window.POKEDEX3D_MODELS = models;
    folderStatus.textContent = models.length + " verified Switch models loaded locally. None were uploaded.";
    statusEl.textContent = models.length.toLocaleString() + " local regular Switch models ready";
    searchEl.value = "";
    filtered = [...models];
    selectedIndex = 0;
    renderList();
    selectModel(0);
  } catch (error) {
    folderStatus.textContent = "Could not read that folder: " + String(error.message || error);
  } finally {
    chooseLocalModelsBtn.disabled = false;
    localModelsFolder.value = "";
  }
});

if (!isLocalIndexServer()) {
  // GitHub Pages / index.html is viewer-only; shader baking belongs to the
  // separate local build environment and must never be offered as a web action.
  repairTexturesBtn.classList.add("hidden");
}

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
  : "Choose a Switch model folder to start (no installation needed)";

renderList();
if (models.length) {
  selectModel(0);
} else {
  formSelect.replaceChildren();
  formSelect.disabled = true;
  messageEl.textContent = "Open a folder containing verified Switch GLBs, or use a site with published model assets.";
  messageEl.classList.remove("hidden");
}
