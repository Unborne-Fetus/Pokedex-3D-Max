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
const exportModelManifestBtn = document.querySelector("#exportModelManifest");
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
let localModelsForExport = [];
let remoteAbort = null;
let loadSequence = 0;
let cameraFitTimer = null;

// Species-specific camera pivot corrections. Units are a fraction of
// horizontal model bounds; they only affect framing, never meshes or rigs.
const CAMERA_PIVOT_ADJUSTMENTS = Object.freeze({
  3: -0.30, // Venusaur: correct forward/back position without moving left or right.
});


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

function clearCameraFitTimer() {
  if (cameraFitTimer !== null) {
    clearTimeout(cameraFitTimer);
    cameraFitTimer = null;
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

// Fit every Switch Pokémon independently. A fixed orbit percentage makes
// differently proportioned or animated models appear tiny or badly cropped.
function computeCameraFrame(dimensions, center, viewportWidth, viewportHeight, model = {}) {
  const values = [dimensions?.x, dimensions?.y, dimensions?.z, center?.x, center?.y, center?.z]
    .map(Number);
  if (!values.every(Number.isFinite) || values.slice(0, 3).some(v => v <= 0)) return null;

  const [width, height, depth, cx, cy, cz] = values;
  const viewportAspect = Math.max(0.35,
    (Number(viewportWidth) || 1) / (Number(viewportHeight) || 1));
  const fov = 30;
  const tanHalfFov = Math.tan(fov * Math.PI / 360);

  // Reserve breathing room for horns, wings, feet, and animated poses.
  // The depth term prevents the closest points clipping the camera plane.
  const fill = 0.74;
  let distance = Math.max(
    height / (2 * tanHalfFov * fill),
    width / (2 * tanHalfFov * fill * viewportAspect),
  ) + depth * 0.5;

  // Verified catalog metadata can tune genuinely unusual individual models.
  const scale = Number(model?.cameraDistanceScale);
  if (Number.isFinite(scale) && scale >= 0.5 && scale <= 2) distance *= scale;
  if (!Number.isFinite(distance) || distance <= 0) return null;

  // Slightly lower the displayed Pokémon by lifting the camera target.
  // Offsets are relative to its actual size, not fixed world coordinates.
  const extra = Number(model?.cameraTargetYOffset);
  const yOffset = Number.isFinite(extra) && Math.abs(extra) <= 0.3 ? extra : 0;
  return {
    distance,
    target: [cx, cy, cz + Math.max(width, depth) * (CAMERA_PIVOT_ADJUSTMENTS[Number(model?.dex)] || 0)],
  };
}

function resetCamera() {
  const hasOverride = currentModel?.cameraAzimuth !== undefined
    && currentModel?.cameraAzimuth !== null
    && Number.isFinite(Number(currentModel.cameraAzimuth));
  const azimuth = hasOverride ? Number(currentModel.cameraAzimuth) : 0;
  const frame = computeCameraFrame(
    viewer.getDimensions?.(),
    viewer.getBoundingBoxCenter?.(),
    viewer.clientWidth,
    viewer.clientHeight,
    currentModel,
  );
  viewer.fieldOfView = "30deg";
  if (frame) {
    viewer.cameraTarget = frame.target.map(n => n.toFixed(4) + "m").join(" ");
    viewer.cameraOrbit = azimuth + "deg 90deg " + frame.distance.toFixed(4) + "m";
  } else {
    // Fallback only for corrupt or not-yet-reported model dimensions.
    viewer.cameraTarget = "auto auto auto";
    viewer.cameraOrbit = azimuth + "deg 90deg 60%";
  }
  viewer.resetTurntableRotation?.(0);
  viewer.jumpCameraToGoal?.();
}

// Updating bounds is asynchronous. Never apply an old model's camera settings
// to a newly selected Pokémon while a load or animation is in flight.
async function applyCameraFit(sequence = loadSequence) {
  if (!viewer.loaded || sequence !== loadSequence) return;
  try {
    await viewer.updateFraming?.();
  } catch (_) { /* Keep last known bounds on older model-viewer releases. */ }
  if (viewer.loaded && sequence === loadSequence) resetCamera();
}

// Do not override legacy body-material alpha modes in the browser. Some Switch
// meshes use alpha-cutout silhouette cards (fur, feathers, whiskers, etc.), so
// forcing every body_* material to OPAQUE creates the white triangular spikes
// seen in legacy exports. Rebuilt GLBs must carry the correct alpha policy from
// the source material instead.

function scheduleCameraFit() {
  clearCameraFitTimer();
  const sequence = loadSequence;
  // Use the visible idle pose; many Switch rest poses have wider geometry.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => { void applyCameraFit(sequence); });
  });
  cameraFitTimer = setTimeout(() => {
    cameraFitTimer = null;
    void applyCameraFit(sequence);
  }, 240);
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
  clearCameraFitTimer();
  playingBreak = false;
  idleAnimation = null;
  currentModel = model;
  ++loadSequence;
  if (remoteAbort) {
    remoteAbort.abort();
    remoteAbort = null;
  }
  const selectedSequence = loadSequence;

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
  viewer.alt = "3D Switch model of " + prettyName(model);
  loadTimer = setTimeout(() => {
    if (selectedSequence !== loadSequence) return;
    messageEl.textContent = "Switch model is taking longer than expected to load. Check your connection or try another Pokémon.";
    messageEl.classList.remove("hidden");
  }, fromRemoteManifest ? 30000 : 15000);

  if (fromLocalFolder) {
    activeObjectUrl = URL.createObjectURL(model.file);
    viewer.src = activeObjectUrl;
  } else if (fromRemoteManifest || model.source === "original-switch-local-merge") {
    // GitHub inventories and merged local catalogs omit idle metadata.
    // Download once, inspect the real GLB for embedded color and a valid
    // idle, then render that exact same downloaded data through a blob URL.
    const abort = new AbortController();
    remoteAbort = abort;
    (async () => {
      try {
        const reply = await fetch(catalogUrl, { mode: "cors", signal: abort.signal });
        if (!reply.ok) throw Error("GitHub returned HTTP " + reply.status);
        const data = await reply.arrayBuffer();
        if (abort.signal.aborted || selectedSequence !== loadSequence) return;
        const checked = fromRemoteManifest
          ? window.POKEDEX3D_REMOTE_SWITCH.inspect(data)
          : (() => {
              const view = new DataView(data);
              const doc = JSON.parse(new TextDecoder().decode(
                new Uint8Array(data, 20, view.getUint32(12, true))));
              const animations = (doc.animations || [])
                .filter(clip => clip.channels?.length && clip.samplers?.length)
                .map(clip => clip.name).filter(Boolean);
              const idleAnimation = chooseIdle(model, animations)
                || (animations.length === 1 && /^Animation(?:[. _-]\\d+)?$/i.test(animations[0])
                  ? animations[0] : null);
              return { animations, idleAnimation };
            })();
        if (abort.signal.aborted || selectedSequence !== loadSequence) return;
        model.idleAnimation = checked.idleAnimation;
        model.idleBreaks = (model.idleBreaks || [])
          .filter(name => checked.animations.includes(name) && name !== checked.idleAnimation);
        activeObjectUrl = URL.createObjectURL(new Blob([data], { type: "model/gltf-binary" }));
        viewer.src = activeObjectUrl;
      } catch (error) {
        if (abort.signal.aborted || selectedSequence !== loadSequence) return;
        clearLoadTimer();
        messageEl.textContent = "Could not load verified Switch GLB from GitHub: " +
          String(error.message || error) + ". Try a different Pokémon.";
        messageEl.classList.remove("hidden");
      } finally {
        if (remoteAbort === abort) remoteAbort = null;
      }
    })();
  } else {
    viewer.src = catalogUrl;
  }
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
  startIdle();
  scheduleCameraFit();
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
  if (localFolderActive || models.some(model => !model.remoteSwitch)) return;
  const incoming = Array.isArray(event.detail?.models) ? event.detail.models : [];
  if (!incoming.length) return;
  const selectedDex = models[selectedIndex]?.dex;
  const currentQuery = searchEl.value.trim().toLowerCase().replace(/^#/, "");
  models = incoming;
  window.POKEDEX3D_MODELS = models;
  filtered = currentQuery ? models.filter(model =>
    String(model.dex) === currentQuery || prettyName(model).toLowerCase().includes(currentQuery)
  ) : [...models];
  selectedIndex = Math.max(0, filtered.findIndex(model => model.dex === selectedDex));
  folderStatus.textContent = "Models stream from the public GitHub repository. Individual textures and idles are checked when opened.";
  statusEl.textContent = models.length.toLocaleString() + " uploaded Switch models on GitHub";
  renderList();
  if (filtered.length && (!currentModel || !models.some(model => model.dex === currentModel.dex))) {
    selectModel(selectedIndex);
  }
});
window.addEventListener("pokedex3d:remote-switch-error", event => {
  if (models.length || localFolderActive) return;
  folderStatus.textContent = "Hosted model catalog unavailable: " +
    String(event.detail?.message || "unknown error") + ". You can still open a local folder.";
});

// Static site mode: open already-converted models directly from the visitor's
// device. File selections never leave the browser; no Python or local server.
exportModelManifestBtn.addEventListener("click", () => {
  if (!localModelsForExport.length) return;
  const catalog = window.POKEDEX3D_LOCAL_SWITCH.buildManifest(localModelsForExport);
  if (!catalog.entries.length) return;
  const blob = new Blob([JSON.stringify(catalog, null, 2) + "\n"], { type: "application/json" });
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.download = "switch-manifest.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
  folderStatus.textContent = "Downloaded a catalog for " + catalog.models + " models. You can upload the JSON to your GitHub model repository; no Actions or billing required.";
});
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
    localModelsForExport = outcome.models;
    exportModelManifestBtn.disabled = false;
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

resetCameraBtn.addEventListener("click", () => { void applyCameraFit(); });

// Recalculate after a viewport resize, when available width/height changes.
let cameraResizeTimer = null;
window.addEventListener("resize", () => {
  if (cameraResizeTimer !== null) clearTimeout(cameraResizeTimer);
  const sequence = loadSequence;
  cameraResizeTimer = setTimeout(() => {
    cameraResizeTimer = null;
    void applyCameraFit(sequence);
  }, 140);
});

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
