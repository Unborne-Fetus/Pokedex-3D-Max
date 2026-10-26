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
const animationSelect = document.querySelector("#animationSelect");
const materialFinishSelect = document.querySelector("#materialFinish");
const repairTexturesBtn = document.querySelector("#repairTextures");
const repairPanel = document.querySelector("#repairPanel");
const repairTitle = document.querySelector("#repairTitle");
const repairSummary = document.querySelector("#repairSummary");
const repairLog = document.querySelector("#repairLog");
const closeRepairBtn = document.querySelector("#closeRepair");
const chooseLocalModelsBtn = document.querySelector("#chooseLocalModels");
const exportModelManifestBtn = document.querySelector("#exportModelManifest");
const localModelsFolder = document.querySelector("#localModelsFolder");
const importGfpakBtn = document.querySelector("#importGfpakZip");
const gfpakZipFile = document.querySelector("#gfpakZipFile");
const gfpakBatchResults = document.querySelector("#gfpakBatchResults");
const gfpakBatchSummary = document.querySelector("#gfpakBatchSummary");
const gfpakBatchResultsList = document.querySelector("#gfpakBatchResultsList");
const folderStatus = document.querySelector("#folderStatus");
const githubStorage = window.POKEDEX3D_GITHUB_STORAGE;
const githubTokenInput = document.querySelector("#githubToken");
const githubConnectBtn = document.querySelector("#connectGitHub");
const githubDisconnectBtn = document.querySelector("#disconnectGitHub");
const githubPublishBtn = document.querySelector("#publishSelectedGitHub");
const githubPublishAllBtn = document.querySelector("#publishAllGitHub");
const githubOverrideExisting = document.querySelector("#githubOverrideExisting");
const githubDefaultAnimation = document.querySelector("#githubDefaultAnimation");
const githubStatus = document.querySelector("#githubStatus");
let githubBusy = false;
const modelCoverageCountEl = document.querySelector("#modelCoverageCount");
const modelCoverageDetailEl = document.querySelector("#modelCoverageDetail");
const modelCoverageProgressEl = document.querySelector("#modelCoverageProgress");
const modelCoverageFillEl = document.querySelector("#modelCoverageFill");
const animationCoverageCountEl = document.querySelector("#animationCoverageCount");
const animationCoverageDetailEl = document.querySelector("#animationCoverageDetail");
const animationCoverageProgressEl = document.querySelector("#animationCoverageProgress");
const animationCoverageFillEl = document.querySelector("#animationCoverageFill");
const finishedCoverageCountEl = document.querySelector("#finishedCoverageCount");
const finishedCoverageDetailEl = document.querySelector("#finishedCoverageDetail");
const finishedCoverageProgressEl = document.querySelector("#finishedCoverageProgress");
const finishedCoverageFillEl = document.querySelector("#finishedCoverageFill");


// Keep every numbered National Dex species visible even without a model.
// Externally hosted preview candidates only fill missing Switch entries and are
// never written into the regular Switch catalog or marked Finished.
function normalizeSwitchModel(model) {
  if (!model || model.missingModel || model.communityCandidate) return model;
  const internal = Number(model.sourceModelId ?? model.modelId);
  const game = String(model.sourceGame || "");
  // Correct misnumbered local imports as well as the public inventory.
  // Keep the physical URL unchanged: it points at the actual existing GLB.
  if (!Number.isInteger(internal) || internal <= 0 ||
      !/^(?:sv|swsh|la|za)(?:-|$)/i.test(game)) return model;
  const dex = window.POKEDEX3D_MODEL_IDENTITY.nationalDex(internal, game);
  if (!Number.isInteger(dex) || dex < 1 || dex > 1025) return null;
  if (dex === Number(model.dex)) return model;
  return { ...model, dex, name: window.POKEDEX3D_NAMES?.[dex] ||
    "#" + String(dex).padStart(4, "0"), originalCatalogDex: Number(model.dex) };
}

function withMissingSpeciesEntries(catalog, includeCommunity = true) {
  const entries = new Map();
  for (const original of catalog) {
    const model = normalizeSwitchModel(original);
    if (!model) continue;
    const dex = Number(model?.dex);
    if (!Number.isInteger(dex) || dex < 1 || dex > 1025) continue;
    if (!entries.has(dex) || (entries.get(dex).missingModel && !model.missingModel)) {
      entries.set(dex, model);
    }
  }
  if (includeCommunity) {
    for (const candidate of (window.POKEDEX3D_COMMUNITY_CANDIDATES?.models || [])) {
      const dex = Number(candidate.dex);
      if (!Number.isInteger(dex) || dex < 1 || dex > 1025) continue;
      const current = entries.get(dex);
      if (!current || current.missingModel) entries.set(dex, { ...candidate });
    }
  }
  for (const [number, name] of Object.entries(window.POKEDEX3D_NAMES || {})) {
    const dex = Number(number);
    if (!Number.isInteger(dex) || dex < 1 || dex > 1025 || entries.has(dex)) continue;
    entries.set(dex, { dex, name, form: "regular", missingModel: true, remoteSwitch: true });
  }
  return [...entries.values()].sort((a, b) => Number(a.dex) - Number(b.dex));
}

// The uploaded-file catalog does not contain trustworthy animation totals.
// Confirm idle-clip availability only after each model actually loads.
const NATIONAL_DEX_TOTAL = 1025;
const finishedReview = window.POKEDEX3D_FINISHED || { finishedDex: [], lastReviewedDex: 0 };
const finishedDex = new Set((finishedReview.finishedDex || [])
  .map(Number).filter(dex => Number.isInteger(dex) && dex >= 1 && dex <= NATIONAL_DEX_TOTAL));
const inspectedIdleDex = new Set();
const confirmedIdleDex = new Set();
const ANIMATION_CACHE_KEY = "pokedex3d-confirmed-idle-v1";

// Remember inspected assets on this device, but never assume a different
// revision of a model has the same animation support.
function modelCacheIdentity(model) {
  if (!model || model.missingModel) return null;
  const dex = Number(model.dex);
  if (!Number.isInteger(dex) || dex < 1 || dex > NATIONAL_DEX_TOTAL) return null;
  const file = model.file;
  // A content fingerprint is stable across page URLs, CDN cache-busters and
  // index re-deployments. Only discard a saved animation check when the model
  // bytes actually change, not when the URL or GitHub Pages build changes.
  const fingerprint = String(model.sourceBlobSha || model.sha || model.sha256 || "").toLowerCase();
  const identity = file && typeof file.size === "number"
    ? ["local", file.webkitRelativePath || file.name, file.size, file.lastModified]
    : /^[a-f0-9]{40}(?:[a-f0-9]{24})?$/.test(fingerprint)
      ? ["verified-asset", fingerprint]
      : ["catalog", String(model.url || ""), String(model.assetRevision || model.bytes || "")];
  return JSON.stringify([dex, ...identity]);
}

function readSavedIdleChecks() {
  try {
    const record = JSON.parse(window.localStorage.getItem(ANIMATION_CACHE_KEY) || "null");
    return record?.version === 1 && record.results && typeof record.results === "object"
      && !Array.isArray(record.results) ? record.results : {};
  } catch (_) {
    // File-based browsers and privacy modes may block persistent storage.
    return {};
  }
}

let savedIdleChecks = readSavedIdleChecks();

function restoreAnimationCoverage() {
  inspectedIdleDex.clear();
  confirmedIdleDex.clear();
  for (const model of models) {
    const key = modelCacheIdentity(model);
    if (!key) continue;
    const result = savedIdleChecks[key];
    if (result !== 0 && result !== 1) continue;
    const dex = Number(model.dex);
    inspectedIdleDex.add(dex);
    if (result === 1) confirmedIdleDex.add(dex);
  }
}

function saveIdleCheck(model, hasIdle) {
  const key = modelCacheIdentity(model);
  if (!key) return;
  savedIdleChecks[key] = hasIdle ? 1 : 0;
  try {
    window.localStorage.setItem(ANIMATION_CACHE_KEY,
      JSON.stringify({ version: 1, results: savedIdleChecks }));
  } catch (_) {
    // Continue to track progress for this session even without storage access.
  }
}

function coverageStatistics(catalog, inspected = inspectedIdleDex, confirmed = confirmedIdleDex) {
  const available = new Set(catalog
    .filter(model => !model.missingModel && Number.isInteger(Number(model.dex)))
    .map(model => Number(model.dex))
    .filter(dex => dex >= 1 && dex <= NATIONAL_DEX_TOTAL));
  return {
    models: available.size,
    previews: catalog.filter(model => model.communityCandidate && !model.missingModel).length,
    inspected: [...inspected].filter(dex => available.has(dex)).length,
    animated: [...confirmed].filter(dex => available.has(dex)).length,
    finished: [...finishedDex].filter(dex => available.has(dex)).length,
  };
}

function renderCoverage() {
  const stats = coverageStatistics(models);
  const updateMeter = (count, countEl, detailEl, progressEl, fillEl, detail) => {
    const percent = count / NATIONAL_DEX_TOTAL * 100;
    countEl.textContent = count.toLocaleString() + " / " + NATIONAL_DEX_TOTAL.toLocaleString();
    detailEl.textContent = percent.toFixed(1) + "% · " + detail;
    fillEl.style.width = percent.toFixed(3) + "%";
    progressEl.setAttribute("aria-valuenow", String(count));
    progressEl.setAttribute("aria-valuetext",
      count + " of " + NATIONAL_DEX_TOTAL + ". " + detail);
  };
  updateMeter(stats.models, modelCoverageCountEl, modelCoverageDetailEl,
    modelCoverageProgressEl, modelCoverageFillEl,
    stats.previews.toLocaleString() + " community previews (not visually reviewed); " +
    (NATIONAL_DEX_TOTAL - stats.models).toLocaleString() + " still missing");
  updateMeter(stats.animated, animationCoverageCountEl, animationCoverageDetailEl,
    animationCoverageProgressEl, animationCoverageFillEl,
    stats.inspected.toLocaleString() + " inspected; others not yet verified");
  const next = Math.min(NATIONAL_DEX_TOTAL, Number(finishedReview.lastReviewedDex || 0) + 1);
  updateMeter(stats.finished, finishedCoverageCountEl, finishedCoverageDetailEl,
    finishedCoverageProgressEl, finishedCoverageFillEl,
    "through #" + String(finishedReview.lastReviewedDex || 0).padStart(4, "0") +
    (next <= NATIONAL_DEX_TOTAL && next > Number(finishedReview.lastReviewedDex || 0)
      ? " · next #" + String(next).padStart(4, "0") : " · all reviewed"));
}

function noteAnimationInspection(model, hasIdle) {
  if (!model || model.missingModel) return;
  const dex = Number(model.dex);
  if (!Number.isInteger(dex) || dex < 1 || dex > NATIONAL_DEX_TOTAL) return;
  inspectedIdleDex.add(dex);
  if (hasIdle) confirmedIdleDex.add(dex);
  else confirmedIdleDex.delete(dex);
  saveIdleCheck(model, hasIdle);
  renderCoverage();
}

window.addEventListener("storage", event => {
  if (event.key !== ANIMATION_CACHE_KEY) return;
  savedIdleChecks = readSavedIdleChecks();
  restoreAnimationCoverage();
  renderCoverage();
});

function catalogCoverageText(catalog) {
  const realSwitch = catalog.filter(model => !model.missingModel && !model.communityCandidate).length;
  const previews = catalog.filter(model => model.communityCandidate && !model.missingModel).length;
  return catalog.length.toLocaleString() + " Pokémon · " +
    realSwitch.toLocaleString() + " Switch models · " +
    previews.toLocaleString() + " external previews · " +
    (catalog.length - realSwitch - previews).toLocaleString() + " missing";
}

// Both the on-disk Switch manifest and the uploaded GitHub inventory are
// available before this script runs. Seed the catalog immediately so that
// #0001–#0009 (and other uploaded Pokémon) never appear falsely missing.
const installedSwitchModels = (Array.isArray(window.POKEDEX3D_SWITCH_MODELS)
  ? window.POKEDEX3D_SWITCH_MODELS
  : [])
  .filter(model => model?.valid !== false && model?.ready !== false)
  .filter(model => String(model?.form || "regular").toLowerCase() === "regular")
  .filter(model => String(model?.url || "").replaceAll("\\", "/").includes("/switch/"));
const bundledSwitchModels = window.POKEDEX3D_REMOTE_SWITCH?.bundled?.() || [];
let models = withMissingSpeciesEntries([], false); // Manual rebuild: no preloaded Switch models.

window.POKEDEX3D_MODELS = models;


const gfpakOrientationSelect = document.createElement("select");
gfpakOrientationSelect.id = "gfpakOrientation";
gfpakOrientationSelect.setAttribute("aria-label", "GFPAK model rotation");
for (const [value, label] of [
  ["0deg 0deg 0deg", "Original"],
  ["0deg 90deg 0deg", "Y +90°"], ["0deg -90deg 0deg", "Y -90°"],
  ["0deg 180deg 0deg", "Y 180°"],
  ["90deg 0deg 0deg", "X +90°"], ["-90deg 0deg 0deg", "X -90°"],
  ["0deg 0deg 90deg", "Z +90°"], ["0deg 0deg -90deg", "Z -90°"],
  ["0deg 0deg 180deg", "Z 180°"],
  ["90deg 90deg 0deg", "Legacy rotation 1"],
  ["-90deg 90deg 0deg", "Legacy rotation 2"],
  ["180deg 90deg 0deg", "Legacy rotation 3"]
]) {
  const option = document.createElement("option");
  option.value = value; option.textContent = label;
  gfpakOrientationSelect.appendChild(option);
}
const gfpakOrientationLabel = document.createElement("label");
gfpakOrientationLabel.className = "animation-picker";
gfpakOrientationLabel.hidden = true;
gfpakOrientationLabel.textContent = "Default model orientation ";
gfpakOrientationLabel.appendChild(gfpakOrientationSelect);
animationSelect.closest("label")?.insertAdjacentElement("afterend", gfpakOrientationLabel);

function gfpakDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("pokedex3d-gfpak-imports", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("models", { keyPath: "dex" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function gfpakStorage(mode, value) {
  const db = await gfpakDB();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("models", mode === "save" ? "readwrite" : "readonly");
      const request = mode === "save"
        ? tx.objectStore("models").put({
            dex: value.dex, name: value.name, sourceGame: value.sourceGame,
            sourceModelId: value.sourceModelId, file: value.file,
            orientation: value.orientation, orientationVersion: value.orientationVersion,
            idleAnimation: value.idleAnimation, sourceBlobSha: value.sourceBlobSha || null,
            githubPublished: value.githubPublished === true,
            eggPlaceholder: value.eggPlaceholder === true
          })
        : tx.objectStore("models").getAll();
      let result;
      request.onsuccess = () => { result = request.result; };
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}
gfpakOrientationSelect.addEventListener("change", async () => {
  if (!currentModel || (!currentModel.gfpakImport && !githubStorage.connected())) return;
  currentModel.orientation = gfpakOrientationSelect.value;
  currentModel.orientationVersion = 2;
  viewer.orientation = currentModel.orientation;
  if (currentModel.file instanceof File) {
    try { await gfpakStorage("save", currentModel); }
    catch (error) { folderStatus.textContent = "Rotation works but could not save: " + error; }
  }
});

const LAST_VIEWED_KEY = "pokedex3d-last-viewed-dex";
function lastViewedDex() {
  try {
    const dex = Number(localStorage.getItem(LAST_VIEWED_KEY));
    return Number.isInteger(dex) && dex >= 1 && dex <= 1025 ? dex : null;
  } catch (_) { return null; }
}
function rememberViewedDex(dex) {
  try { localStorage.setItem(LAST_VIEWED_KEY, String(dex)); } catch (_) {}
}
let filtered = [...models];
let selectedIndex = 0;
let currentModel = null;
let autoRotate = false;
let loadTimer = null;
let repairPollTimer = null;
let repairInProgress = false;
let activeObjectUrl = null;
let localFolderActive = false;
let localModelsForExport = [];
let remoteAbort = null;
let loadSequence = 0;
let cameraFitTimer = null;
let activeAnimationSequence = null;
let materialBaseline = [];

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
  const known = String(window.POKEDEX3D_NAMES?.[model?.dex] || model?.name || "").trim();
  return known || ("#" + String(model?.dex || 0).padStart(4, "0"));
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

// A single animation player is shared by local GFPAK ZIPs and published GLBs.
// Only expose clips the 3D viewer actually decoded, not names in old metadata.
function resetAnimationSelect(label = "Loading…") {
  animationSelect.replaceChildren();
  const option = document.createElement("option");
  option.value = "";
  option.textContent = label;
  animationSelect.appendChild(option);
  animationSelect.disabled = true;
}

// Triplets in imported Switch archives are separate GLB clips. Treat complete
// Start/Loop/End triplets as one action, keeping each raw clip independently
// selectable for troubleshooting. Never guess missing phase names.
function animationPhase(name) {
  const normalized = String(name).replace(/^pm\d{4}(?:_\d{2}){2}_\d{5}_/i, "");
  const match = normalized.match(/^(.+?)[_\s-]+(start|loop|end)$/i);
  return match ? { key: match[1].toLowerCase(), phase: match[2].toLowerCase() } : null;
}

let animationSequences = new Map();
function discoverAnimationSequences(animations) {
  const groups = new Map();
  for (const clip of animations) {
    const part = animationPhase(clip);
    if (!part) continue;
    if (!groups.has(part.key)) groups.set(part.key, {});
    groups.get(part.key)[part.phase] = clip;
  }
  return new Map([...groups].filter(([, phases]) =>
    phases.start && phases.loop && phases.end));
}

function playClip(name, repetitions = Infinity) {
  if (!name || !availableAnimations().includes(name)) return false;
  viewer.animationName = name;
  viewer.currentTime = 0;
  viewer.play({ repetitions });
  messageEl.classList.add("hidden");
  return true;
}

function playAnimation(name) {
  if (typeof name !== "string" || !name) return;
  activeAnimationSequence = null; // Cancel a previous action if user switches.
  if (name.startsWith("sequence:")) {
    const clips = animationSequences.get(name.slice(9));
    if (!clips) return;
    activeAnimationSequence = {
      clips, phase: 0, expected: clips.start, modelSequence: loadSequence,
    };
    if (!playClip(clips.start, 1)) activeAnimationSequence = null;
    return;
  }
  playClip(name);
}

viewer.addEventListener("finished", () => {
  const sequence = activeAnimationSequence;
  if (!sequence || sequence.modelSequence !== loadSequence ||
      viewer.animationName !== sequence.expected) return;
  sequence.phase++;
  if (sequence.phase === 1) {
    // A finite number of loop iterations guarantees the End animation runs.
    sequence.expected = sequence.clips.loop;
    if (!playClip(sequence.expected, 2)) activeAnimationSequence = null;
  } else if (sequence.phase === 2) {
    sequence.expected = sequence.clips.end;
    if (!playClip(sequence.expected, 1)) activeAnimationSequence = null;
  } else {
    activeAnimationSequence = null;
    const idle = chooseIdle(currentModel, availableAnimations());
    if (idle) {
      animationSelect.value = idle;
      playClip(idle);
    }
  }
});

// View-only surface correction: do not mutate the GLB or overwrite its
// textures. Snapshot each newly loaded scene so Original restores precisely.
function applyMaterialFinish() {
  const natural = materialFinishSelect?.value !== "original";
  for (const record of materialBaseline) {
    const pbr = record.material.pbrMetallicRoughness;
    if (!pbr) continue;
    try {
      pbr.setMetallicFactor(natural ? Math.min(record.metal, 0.22) : record.metal);
      pbr.setRoughnessFactor(natural ? Math.max(record.rough, 0.78) : record.rough);
      if (typeof record.material.setSpecularFactor === "function" &&
          Number.isFinite(record.specular)) {
        record.material.setSpecularFactor(natural ?
          Math.min(record.specular, 0.65) : record.specular);
      }
      if (typeof record.material.setClearcoatFactor === "function" &&
          Number.isFinite(record.clearcoat)) {
        record.material.setClearcoatFactor(natural ?
          Math.min(record.clearcoat, 0.15) : record.clearcoat);
      }
    } catch (_) { /* Do not break a model with unsupported materials. */ }
  }
}
materialFinishSelect?.addEventListener("change", applyMaterialFinish);
function captureMaterialFinish() {
  materialBaseline = Array.from(viewer.model?.materials || []).map(material => ({
    material,
    metal: material.pbrMetallicRoughness?.metallicFactor ?? 0,
    rough: material.pbrMetallicRoughness?.roughnessFactor ?? 1,
    specular: material.specularFactor,
    clearcoat: material.clearcoatFactor,
  }));
  applyMaterialFinish();
}

// Render friendly labels without changing the exact animation identifiers used by model-viewer.
function animationDisplayName(raw) {
  let name = String(raw || "");
  // GFPAK exports often prefix each clip with pm0212_01_00_20000_.
  name = name.replace(/^pm\d{4}(?:_\d{2}){2}_\d{5}_/i, "");
  name = name.replace(/(?:^|[_-])r(090|180|270)(?=$|[_-])/gi, (_, angle) =>
    "_right_" + (Number(angle) / 90));
  name = name.replace(/(?:^|[_-])l(090|180|270)(?=$|[_-])/gi, (_, angle) =>
    "_left_" + (Number(angle) / 90));
  const phrases = [
    [/^defaultwait/i, "Idle"], [/^wait/i, "Idle"],
    [/^turn_right_1/i, "Turn Right"], [/^turn_left_1/i, "Turn Left"],
    [/^turn_right_2/i, "Turn Around Right"], [/^turn_left_2/i, "Turn Around Left"],
    [/^turn_right_3/i, "Turn Right 270°"], [/^turn_left_3/i, "Turn Left 270°"],
    [/^strife_right_2/i, "Strafe Right"], [/^strife_left_2/i, "Strafe Left"],
    [/^strife/i, "Strafe"], [/^run/i, "Run"], [/^walk/i, "Walk"],
    [/^stepout/i, "Step Out"], [/^jumpdown/i, "Jump Down"],
    [/^jumpup/i, "Jump Up"], [/^jump/i, "Jump"], [/^land/i, "Land"],
    [/^sleep/i, "Sleep"], [/^eat/i, "Eat"], [/^fall/i, "Fall"],
    [/^faint/i, "Faint"], [/^damage/i, "Take Damage"], [/^attack/i, "Attack"],
  ];
  for (const [pattern, label] of phrases) {
    if (pattern.test(name)) { name = name.replace(pattern, label + "_"); break; }
  }
  name = name.replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b(start|loop|end)\b/gi, word =>
      ({start:"Start",loop:"Loop",end:"End"})[word.toLowerCase()])
    .replace(/([A-Za-z])0+(\d+)/g, "$1 $2")
    .replace(/\s+/g, " ").trim();
  if (!name) return String(raw);
  return name.replace(/\b[a-z]/g, letter => letter.toUpperCase());
}

function setupAnimationSelect() {
  const animations = [...new Set(availableAnimations())];
  if (!animations.length) {
    resetAnimationSelect("No animations");
    messageEl.textContent = "This 3D model does not contain any playable animations.";
    messageEl.classList.remove("hidden");
    return false;
  }
  const idle = chooseIdle(currentModel, animations);
  const initial = idle || animations[0];
  animationSequences = discoverAnimationSequences(animations);
  animationSelect.replaceChildren();
  for (const [key, clips] of animationSequences) {
    const option = document.createElement("option");
    option.value = "sequence:" + key;
    option.textContent = animationDisplayName(clips.start).replace(/\s+Start$/i, "") +
      " • Start → Loop → End";
    animationSelect.appendChild(option);
  }
  for (const name of animations) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = animationDisplayName(name);
    animationSelect.appendChild(option);
  }
  animationSelect.value = initial;
  animationSelect.disabled = false;
  playAnimation(initial);
  if (currentModel) currentModel.animations = animations;
  refreshGitHubModelOptions();
  return Boolean(idle);
}

animationSelect.addEventListener("change", () => playAnimation(animationSelect.value));

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
  const fill = model?.gfpakImport ? 0.62 : 0.74;
  let distance = Math.max(
    height / (2 * tanHalfFov * fill),
    width / (2 * tanHalfFov * fill * viewportAspect),
  ) + depth * 0.5;

  // Verified catalog metadata can tune genuinely unusual individual models.
  const scale = Number(model?.cameraDistanceScale);
  if (Number.isFinite(scale) && scale >= 0.5 && scale <= 2) distance *= scale;
  // LA imports #0465 have unusually generous source bounds; #0493 has long
  // appendages that approach the camera in motion. Avoid tiny/cropped poses.
  const speciesFrameScale = { 465: 0.84, 493: 1.22 }[Number(model?.dex)];
  if (speciesFrameScale) distance *= speciesFrameScale;
  if (!Number.isFinite(distance) || distance <= 0) return null;

  // Slightly lower the displayed Pokémon by lifting the camera target.
  // Offsets are relative to its actual size, not fixed world coordinates.
  const extra = Number(model?.cameraTargetYOffset);
  const yOffset = Number.isFinite(extra) && Math.abs(extra) <= 0.3 ? extra : 0;
  // Imported GFPAK rigs often use a displaced root/pivot. Raise the camera
  // target so their visible geometry is centered rather than cropped above.
  const importOffset = model?.gfpakImport ? 0.24 : 0;
  return {
    distance,
    target: [cx, cy + height * (0.035 + yOffset + importOffset), cz + Math.max(width, depth) * (CAMERA_PIVOT_ADJUSTMENTS[Number(model?.dex)] || 0)],
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
  const variants = model.communityCandidate ? model.variants || [] : [];
  if (variants.length) {
    for (const variant of variants) {
      const option = document.createElement("option");
      option.value = variant.url;
      option.textContent = variant.label + " · External preview";
      option.selected = variant.url === model.url;
      formSelect.appendChild(option);
    }
    formSelect.disabled = variants.length < 2;
  } else {
    const option = document.createElement("option");
    option.value = model.url || "";
    option.textContent = model.missingModel ? "Switch model unavailable" : "Regular";
    option.selected = true;
    formSelect.appendChild(option);
    formSelect.disabled = true;
  }
}

formSelect.addEventListener("change", () => {
  if (!currentModel?.communityCandidate) return;
  const chosen = (currentModel.variants || []).find(v => v.url === formSelect.value);
  if (!chosen) return;
  currentModel.url = chosen.url;
  currentModel.assetRevision = chosen.revision;
  currentModel.sourcePage = chosen.sourcePage;
  currentModel.variantLabel = chosen.label;
  formEl.textContent = "External community preview · " + chosen.label + " · Not finished";
  updateCandidateSourceLink(currentModel);
  loadModel(currentModel);
});

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
    if (model.missingModel) button.title = "Original Switch model unavailable in this catalog";
    button.innerHTML =
      '<span class="dex">#' + String(model.dex).padStart(4, "0") + '</span>' +
      '<span><span class="name">' + escapeHtml(prettyName(model)) + "</span>" +
      (model.missingModel ? '<span class="form"> · Model missing</span>' :
        model.communityCandidate ? '<span class="form"> · External preview</span>' : '') +
      (!model.missingModel && finishedDex.has(Number(model.dex)) ? '<span class="form"> · ✓ Finished</span>' : '') + "</span>";
    button.addEventListener("click", () => selectModel(index));
    fragment.appendChild(button);
  });

  listEl.appendChild(fragment);
  updateSelectedRow();
}

function loadModel(model) {
  clearLoadTimer();
  clearCameraFitTimer();
  resetAnimationSelect();
  activeAnimationSequence = null;
  animationSequences = new Map();
  materialBaseline = [];
  currentModel = model;
  githubDefaultAnimation.replaceChildren();
  refreshGitHubModelOptions();
  refreshGitHubPublishButton();
  ++loadSequence;
  if (remoteAbort) {
    remoteAbort.abort();
    remoteAbort = null;
  }
  const selectedSequence = loadSequence;

  if (model.missingModel) {
    viewer.removeAttribute("src");
    if (activeObjectUrl) {
      URL.revokeObjectURL(activeObjectUrl);
      activeObjectUrl = null;
    }
    messageEl.textContent = prettyName(model) + " (#" +
      String(model.dex).padStart(4, "0") +
      ") is in the Pokédex, but its original animated Switch GLB is not available in this catalog. No substitute model is shown.";
    messageEl.classList.remove("hidden");
    return;
  }

  const catalogUrl = String(model?.url || "");
  const fromLocalFolder = typeof File !== "undefined" && model?.file instanceof File;
  const fromRemoteManifest = model?.remoteSwitch === true
    && /^https:\/\/[^/]+\/(?:.*\/)?\d{4}\/regular\.glb(?:\?[^#]*)?$/.test(catalogUrl);
  const fromCommunity = model?.communityCandidate === true &&
    window.POKEDEX3D_COMMUNITY_CANDIDATES?.isCandidateURL(model.dex, catalogUrl) === true;
  if (!catalogUrl || (!catalogUrl.replaceAll("\\", "/").includes("/switch/") &&
      !fromRemoteManifest && !fromCommunity)) {
    messageEl.textContent = "Blocked unapproved model source.";
    messageEl.classList.remove("hidden");
    viewer.removeAttribute("src");
    return;
  }

  messageEl.textContent = fromCommunity ?
    "Loading external community preview (not a verified Switch original)…" :
    "Loading original Switch model…";
  messageEl.classList.remove("hidden");
  viewer.removeAttribute("src");
  if (activeObjectUrl) {
    URL.revokeObjectURL(activeObjectUrl);
    activeObjectUrl = null;
  }
  viewer.alt = (fromCommunity ? "Community preview 3D model of " : "3D Switch model of ") +
    prettyName(model);
  loadTimer = setTimeout(() => {
    if (selectedSequence !== loadSequence) return;
    messageEl.textContent = (fromCommunity ? "External community preview" : "Switch model") +
      " is taking longer than expected to load. Check your connection or try another Pokémon.";
    messageEl.classList.remove("hidden");
  }, (fromRemoteManifest || fromCommunity) ? 30000 : 15000);

  if (fromLocalFolder) {
    // A selected local file is untrusted until its embedded species ID is checked.
    (async () => {
      try {
        let bytes = await model.file.arrayBuffer();
        if (model.gfpakImport) {
          const repaired = window.POKEDEX3D_GFPAK_ZIP.repairGlb(bytes);
          if (repaired !== bytes) model.file = new File([repaired], 'regular.glb', {type:'model/gltf-binary'});
          bytes = repaired;
        }
        await window.POKEDEX3D_MODEL_IDENTITY.verify(model, bytes);
        if (selectedSequence !== loadSequence) return;
        activeObjectUrl = URL.createObjectURL(model.file);
        viewer.src = activeObjectUrl;
      } catch (error) {
        if (selectedSequence !== loadSequence) return;
        clearLoadTimer();
        messageEl.textContent = "Model identity check failed: " +
          String(error.message || error);
        messageEl.classList.remove("hidden");
      }
    })();
  } else if ((fromCommunity || fromRemoteManifest || model.source === "original-switch-local-merge") || catalogUrl.replaceAll("\\", "/").includes("/switch/")) {
    // GitHub inventories and merged local catalogs omit idle metadata.
    // Download once, inspect the real GLB for embedded color and a valid
    // idle, then render that exact same downloaded data through a blob URL.
    const abort = new AbortController();
    remoteAbort = abort;
    (async () => {
      try {
        let downloaded = await window.POKEDEX3D_MODEL_IDENTITY.loadVerified(
          model, catalogUrl, abort.signal);
        if (model.gfpakImport) downloaded = window.POKEDEX3D_GFPAK_ZIP.repairGlb(downloaded);
        // Never modify third-party GLBs with Switch-only shader/UV repairs.
        const data = !fromCommunity && typeof window.POKEDEX3D_REPAIR_SWITCH_MODEL === "function"
          ? await window.POKEDEX3D_REPAIR_SWITCH_MODEL(downloaded, Number(model.dex))
          : downloaded;
        if (abort.signal.aborted || selectedSequence !== loadSequence) return;
        const checked = fromCommunity
          ? window.POKEDEX3D_COMMUNITY_CANDIDATES.inspect(data)
          : fromRemoteManifest ? window.POKEDEX3D_REMOTE_SWITCH.inspect(data)
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
        model.idleAnimation = chooseIdle(model, checked.animations) || checked.idleAnimation;
        model.animations = checked.animations;
        model.idleBreaks = (model.idleBreaks || [])
          .filter(name => checked.animations.includes(name) && name !== checked.idleAnimation);
        activeObjectUrl = URL.createObjectURL(new Blob([data], { type: "model/gltf-binary" }));
        viewer.src = activeObjectUrl;
      } catch (error) {
        if (abort.signal.aborted || selectedSequence !== loadSequence) return;
        clearLoadTimer();
        messageEl.textContent = (fromCommunity ?
          "Could not load the external community preview: " :
          "Could not load verified Switch GLB from GitHub: ") +
          String(error.message || error) + ". Existing Switch models were not changed.";
        messageEl.classList.remove("hidden");
      } finally {
        if (remoteAbort === abort) remoteAbort = null;
      }
    })();
  } else {
    viewer.src = catalogUrl;
  }
}

function updateCandidateSourceLink(model) {
  const link = document.querySelector("#externalModelSource");
  if (!link) return;
  const external = model?.communityCandidate === true;
  link.hidden = !external;
  if (external) link.href = model.sourcePage;
  else link.removeAttribute("href");
}

function selectModel(index, remember = true) {
  if (!filtered.length) return;
  selectedIndex = Math.max(0, Math.min(index, filtered.length - 1));
  const model = filtered[selectedIndex];
  if (remember) rememberViewedDex(model.dex);
  gfpakOrientationLabel.hidden = !model.gfpakImport;
  const isGfpak = model.gfpakImport || model.sourceFormat === "gfpak-zip";
  model.gfpakImport = !!isGfpak;
  gfpakOrientationLabel.hidden = !isGfpak && !githubStorage.connected();
  if (isGfpak) {
    model.orientation = window.POKEDEX3D_GFPAK_ZIP.orientation(model);
    model.orientationVersion = 2;
  }
  gfpakOrientationSelect.value = model.orientation || "0deg 0deg 0deg";
  viewer.orientation = model.orientation || "0deg 90deg 0deg";

  dexEl.textContent = "#" + String(model.dex).padStart(4, "0");
  nameEl.textContent = prettyName(model);
  formEl.textContent = model.eggPlaceholder
    ? "Egg placeholder (source pm0000) · Not Victini's model" :
    model.communityCandidate ?
      "External community preview · " + model.variantLabel + " · Not finished" :
      (model.missingModel ? "Model not uploaded" : "Regular") +
        (!model.missingModel && finishedDex.has(Number(model.dex)) ? " · Finished" : "");
  updateCandidateSourceLink(model);
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
  captureMaterialFinish();
  const hasIdle = setupAnimationSelect();
  noteAnimationInspection(currentModel, hasIdle);
  scheduleCameraFit();
});

viewer.addEventListener("error", () => {
  clearLoadTimer();
  activeAnimationSequence = null;
  materialBaseline = [];
  resetAnimationSelect("Unavailable");
  messageEl.textContent = currentModel?.communityCandidate ?
    "The external community preview could not render. The existing Switch catalog is untouched." :
    "Switch model could not be rendered. No alternate model source was used.";
  messageEl.classList.remove("hidden");
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
  return; // Manual catalog: never reinstate legacy remote models.
  if (localFolderActive) return;
  const incoming = Array.isArray(event.detail?.models) ? event.detail.models : [];
  if (!incoming.length) return;
  const selectedDex = filtered[selectedIndex]?.dex;
  const currentQuery = searchEl.value.trim().toLowerCase().replace(/^#/, "");
  // Never let an online refresh discard locally repaired, verified GLBs.
  // Replace earlier remote revisions, and fill gaps left by local manifests.
  const localModels = models.filter(model =>
    !model.remoteSwitch && !model.missingModel && !model.communityCandidate);
  models = withMissingSpeciesEntries([...localModels, ...incoming]);
  restoreAnimationCoverage();
  window.POKEDEX3D_MODELS = models;
  filtered = currentQuery ? models.filter(model =>
    String(model.dex) === currentQuery || prettyName(model).toLowerCase().includes(currentQuery)
  ) : [...models];
  selectedIndex = Math.max(0, filtered.findIndex(model => model.dex === selectedDex));
  folderStatus.textContent = "Models stream from the public GitHub repository. Individual textures and idles are checked when opened.";
  statusEl.textContent = catalogCoverageText(models);
  renderCoverage();
  renderList();
  if (filtered.length && (!currentModel || !models.some(model => model.dex === currentModel.dex) ||
      (currentModel.missingModel && models.some(model =>
        model.dex === currentModel.dex && !model.missingModel)))) {
    selectModel(selectedIndex);
  }
});
window.addEventListener("pokedex3d:remote-switch-error", event => {
  if (localFolderActive || models.some(model => !model.missingModel)) return;
  folderStatus.textContent = "Hosted model catalog unavailable: " +
    String(event.detail?.message || "unknown error") + ". You can still open a local folder.";
});

// GitHub is the temporary authoritative public catalog for manually imported
// models. Unpublished browser imports still take priority as local drafts.
function publishableLocalModels() {
  // Never try to publish remote URLs, external preview candidates or placeholders.
  return models.filter(model => model?.file instanceof File &&
    model.form === "regular" && model.valid !== false &&
    !model.communityCandidate && !model.missingModel);
}
function refreshGitHubPublishButton() {
  const connected = githubStorage.connected();
  const selected = currentModel?.file instanceof File ||
    currentModel?.githubTemporary === true;
  githubPublishBtn.disabled = githubBusy || !connected || !selected;
  const localCount = publishableLocalModels().length;
  githubPublishAllBtn.textContent = "Save all " + localCount + " loaded model" +
    (localCount === 1 ? "" : "s") + " to GitHub";
  githubPublishAllBtn.disabled = githubBusy || !connected || localCount === 0;
  githubOverrideExisting.disabled = githubBusy || !connected;
  githubDefaultAnimation.disabled = githubBusy || !connected ||
    githubDefaultAnimation.options.length === 0;
  gfpakOrientationLabel.hidden = !currentModel ||
    (!currentModel.gfpakImport && !connected);
}
function refreshGitHubModelOptions() {
  const clips = [...new Set((currentModel?.animations || [])
    .filter(name => typeof name === "string" && name))];
  githubDefaultAnimation.replaceChildren();
  for (const clip of clips) {
    const option = document.createElement("option");
    option.value = clip;
    option.textContent = animationDisplayName(clip);
    githubDefaultAnimation.appendChild(option);
  }
  if (clips.length) {
    githubDefaultAnimation.value = clips.includes(currentModel?.idleAnimation)
      ? currentModel.idleAnimation : chooseIdle(currentModel, clips) || clips[0];
  }
  refreshGitHubPublishButton();
}
githubDefaultAnimation.addEventListener("change", async () => {
  if (!githubStorage.connected() || !currentModel) return;
  const clips = currentModel.animations || availableAnimations();
  if (!clips.includes(githubDefaultAnimation.value)) return;
  currentModel.idleAnimation = githubDefaultAnimation.value;
  playAnimation(currentModel.idleAnimation);
  if (currentModel.gfpakImport && currentModel.file instanceof File) {
    try { await gfpakStorage("save", currentModel); }
    catch (error) { folderStatus.textContent = "Default animation could not be saved locally: " + error; }
  }
  githubStatus.textContent = "Default animation selected. Save the model/settings to publish this choice.";
});
function showGitHubConnected(connected) {
  githubConnectBtn.hidden = connected;
  githubTokenInput.hidden = connected;
  githubDisconnectBtn.hidden = !connected;
  refreshGitHubModelOptions();
}
function mergeGitHubModels(incoming) {
  const incomingDex = new Set(incoming.map(model => Number(model.dex)));
  const drafts = models.filter(model => model.file instanceof File &&
    model.githubPublished !== true);
  const draftDex = new Set(drafts.map(model => Number(model.dex)));
  const remaining = models.filter(model =>
    !model.missingModel && !model.githubTemporary && !draftDex.has(Number(model.dex)) &&
    !incomingDex.has(Number(model.dex)));
  const selectedDex = currentModel?.dex || lastViewedDex();
  models = withMissingSpeciesEntries([...drafts, ...incoming, ...remaining], false);
  window.POKEDEX3D_MODELS = models;
  restoreAnimationCoverage();
  statusEl.textContent = catalogCoverageText(models);
  renderCoverage();
  const query = searchEl.value.trim().toLowerCase().replace(/^#/, "");
  filtered = query ? models.filter(model =>
    String(model.dex) === query || prettyName(model).toLowerCase().includes(query)
  ) : [...models];
  renderList();
  if (filtered.length) {
    const selected = filtered.findIndex(model => Number(model.dex) === selectedDex);
    selectModel(selected < 0 ? 0 : selected, false);
  }
}
async function loadGitHubModels() {
  try {
    const hosted = await githubStorage.load();
    mergeGitHubModels(hosted);
    githubStatus.textContent = hosted.length
      ? hosted.length + " published Pokémon model(s) available from GitHub."
      : "No models have been published to temporary GitHub storage yet.";
  } catch (error) {
    githubStatus.textContent = "Could not refresh GitHub models: " + error.message +
      ". Locally saved imports remain available.";
  }
}
githubConnectBtn.addEventListener("click", async () => {
  if (githubBusy) return;
  githubBusy = true;
  githubConnectBtn.disabled = true;
  githubStatus.textContent = "Checking GitHub owner and repository permissions…";
  try {
    const login = await githubStorage.connect(githubTokenInput.value);
    githubTokenInput.value = ""; // Never persist the credential.
    showGitHubConnected(true);
    githubStatus.textContent = "Connected as " + login +
      ". GFPAK ZIPs still publish automatically. Use Save selected to update their defaults, or Save all for loaded model files.";
  } catch (error) {
    githubStatus.textContent = "GitHub connection failed: " + error.message;
  } finally {
    githubTokenInput.value = "";
    githubBusy = false;
    githubConnectBtn.disabled = false;
    refreshGitHubPublishButton();
  }
});
githubDisconnectBtn.addEventListener("click", () => {
  githubStorage.disconnect();
  githubTokenInput.value = "";
  githubOverrideExisting.checked = false;
  showGitHubConnected(false);
  githubStatus.textContent = "Disconnected. Models remain publicly viewable; uploads are disabled.";
});
async function rememberSuccessfulUpload(model, published) {
  model.githubPublished = true;
  model.sourceBlobSha = published.sourceBlobSha;
  if (model.gfpakImport && model.file instanceof File) {
    try { await gfpakStorage("save", model); }
    catch (error) { console.warn("Could not update local GitHub sync status", error); }
  }
}
function mergePublishedEntries(published) {
  if (!published.length) return;
  const updated = new Set(published.map(model => Number(model.dex)));
  mergeGitHubModels([
    ...published,
    ...models.filter(model => model.githubTemporary &&
      !updated.has(Number(model.dex))),
  ]);
}
githubPublishBtn.addEventListener("click", async () => {
  if (githubBusy || !githubStorage.connected() || !currentModel) return;
  const publishing = currentModel;
  const uploadingFile = publishing.file instanceof File;
  if (!uploadingFile && publishing.githubTemporary !== true) return;
  if (uploadingFile && publishing.eggPlaceholder && !window.confirm(
    "This is the Sword/Shield Egg (pm0000), NOT Victini's actual model. " +
    "Publish it publicly as a clearly labelled Egg placeholder?"
  )) return;
  const replaceExisting = githubOverrideExisting.checked;
  if (uploadingFile && replaceExisting && !window.confirm(
    "Override the existing temporary GitHub model for #" +
    String(publishing.dex).padStart(4, "0") + " if one exists? " +
    "The previous published GLB for this species will be replaced."
  )) return;
  githubBusy = true;
  githubDisconnectBtn.disabled = true;
  refreshGitHubPublishButton();
  githubStatus.textContent = uploadingFile ? "Uploading Pokémon #" +
    String(publishing.dex).padStart(4, "0") + " to GitHub…" :
    "Saving selected model orientation and default animation…";
  try {
    const settingsOnly = !replaceExisting &&
      (publishing.githubTemporary === true || (publishing.githubPublished === true &&
        !!publishing.sourceBlobSha));
    const published = settingsOnly
      ? await githubStorage.saveModelSettings(publishing)
      : await githubStorage.publishModel(publishing, {replaceExisting});
    if (!settingsOnly) await rememberSuccessfulUpload(publishing, published);
    mergePublishedEntries([published]);
    githubStatus.textContent = uploadingFile
      ? publishing.name + " saved to GitHub. Its selected default settings are public."
      : "Saved orientation and default animation for #" + publishing.dex + ".";
    folderStatus.textContent = "Published settings for Pokémon #" +
      String(publishing.dex).padStart(4, "0") + " to GitHub.";
  } catch (error) {
    githubStatus.textContent = "GitHub save failed: " + error.message +
      ". Local models were not removed.";
  } finally {
    githubBusy = false;
    githubDisconnectBtn.disabled = false;
    refreshGitHubPublishButton();
  }
});
githubPublishAllBtn.addEventListener("click", async () => {
  if (githubBusy || !githubStorage.connected()) return;
  const pending = publishableLocalModels();
  if (!pending.length) return;
  const replaceExisting = githubOverrideExisting.checked;
  if (!window.confirm(
    "Save all " + pending.length + " verified, locally loaded Pokémon GLBs to GitHub? " +
    (replaceExisting
      ? "Existing temporary GitHub models with matching Pokédex numbers WILL be overwritten."
      : "Previously published duplicates will be skipped.") +
    " Models remain on your device if an upload fails."
  )) return;
  githubBusy = true;
  githubDisconnectBtn.disabled = true;
  refreshGitHubPublishButton();
  try {
    // Each published model updates the GitHub manifest against the latest HEAD.
    // Sequential writes preserve manifest entries and report partial success.
    const outcome = await githubStorage.publishModels(pending, {
      replaceExisting,
      onProgress: (index, total, model) => {
        githubStatus.textContent = "Saving " + index + "/" + total +
          " · Pokémon #" + String(model.dex).padStart(4, "0") + "…";
      },
    });
    const publishedDex = new Set(outcome.published.map(row => Number(row.dex)));
    for (const local of pending) {
      if (publishedDex.has(Number(local.dex))) {
        const published = outcome.published.find(row => Number(row.dex) === Number(local.dex));
        await rememberSuccessfulUpload(local, published);
      }
    }
    mergePublishedEntries(outcome.published);
    const failures = outcome.failed.slice(0, 3).map(item =>
      "#" + item.dex + ": " + item.message).join(" | ");
    githubStatus.textContent = "Save all: " + outcome.published.length +
      " published, " + outcome.skipped.length + " duplicate(s) skipped, " +
      outcome.failed.length + " failed." +
      (failures ? " " + failures : "") +
      " Local model files were preserved.";
  } catch (error) {
    githubStatus.textContent = "Save all failed: " + error.message +
      ". Local model files were preserved.";
  } finally {
    githubBusy = false;
    githubDisconnectBtn.disabled = false;
    refreshGitHubPublishButton();
  }
});
showGitHubConnected(false);
void loadGitHubModels();

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
// Each GFPAK ZIP is validated and cached independently. Batch imports
// publish sequentially: overlapping GitHub manifest writes would lose entries.
importGfpakBtn.addEventListener("click", () => gfpakZipFile.click());
gfpakZipFile.addEventListener("change", async () => {
  const files = Array.from(gfpakZipFile.files || []);
  if (!files.length) return;
  if (githubBusy) {
    folderStatus.textContent = "Wait for the current GitHub operation to finish before importing ZIPs.";
    gfpakZipFile.value = "";
    return;
  }

  // Block other GitHub writes for the entire batch, including ZIP validation,
  // to avoid concurrent manifest commits.
  githubBusy = true;
  githubDisconnectBtn.disabled = true;
  refreshGitHubPublishButton();
  importGfpakBtn.disabled = true;
  gfpakBatchResults.hidden = true;
  gfpakBatchResultsList.replaceChildren();
  const acceptedModels = [];
  const savedDex = new Set();
  const published = [];
  const publishFailures = [];
  let outcome = null;

  try {
    outcome = await window.POKEDEX3D_GFPAK_BATCH.run(files, {
      read: (file, single) => window.POKEDEX3D_GFPAK_ZIP.read(file, {
        // An Egg placeholder always needs an explicit Victini selection.
        // Selecting many files must not silently assign eggs to Victini.
        targetDex: single && Number(currentModel?.dex) === 494 ? 494 : null
      }),
      accept: async imported => {
        if (imported.eggPlaceholder && !window.confirm(
          "This ZIP contains a Pokémon Egg (pm0000), not Victini. " +
          "Install it in Victini #0494 as a temporary Egg placeholder? " +
          "This replaces the local Victini preview; it does not change the original ZIP."
        )) return {skipped: true, detail: "Egg placeholder import cancelled"};
        const existing = [...acceptedModels, ...models].find(model =>
          Number(model.dex) === Number(imported.dex) && !model.missingModel);
        if (existing && (!githubStorage.connected() || !githubOverrideExisting.checked)) {
          return { skipped: true, detail: "A model for this Pokémon is already loaded. " +
            "Connect GitHub and enable Override existing model to replace it." };
        }
        imported.gfpakImport = true;
        imported.orientation = window.POKEDEX3D_GFPAK_ZIP.orientation(imported);
        try {
          await gfpakStorage("save", imported);
          savedDex.add(imported.dex);
        } catch (error) {
          console.warn("GFPAK import could not persist", imported.dex, error);
        }
        acceptedModels.push(imported);
        return {detail: savedDex.has(imported.dex)
          ? "Saved locally" : "Imported for this session; browser storage unavailable"};
      },
      progress: ({phase, index, total, name, imported, rejected}) => {
        folderStatus.textContent = phase === "reading"
          ? "Checking " + index + "/" + total + ": " + name +
            " (" + imported + " imported, " + rejected + " rejected)…"
          : "Checked " + index + "/" + total + " ZIPs. " +
            imported + " imported; " + rejected + " rejected.";
      }
    });

    if (acceptedModels.length) {
      // Keep earlier local/hosted models for species not included in this batch.
      // Replace each species just once after all the ZIP checks have finished.
      const newDex = new Set(acceptedModels.map(model => Number(model.dex)));
      localFolderActive = true;
      models = withMissingSpeciesEntries([
        ...acceptedModels, ...models.filter(model => !newDex.has(Number(model.dex)))
      ], false);
      window.POKEDEX3D_MODELS = models;
      restoreAnimationCoverage();
      statusEl.textContent = catalogCoverageText(models);
      renderCoverage();
      searchEl.value = "";
      filtered = [...models];
      renderList();
      selectModel(filtered.findIndex(model =>
        Number(model.dex) === Number(acceptedModels[0].dex)));
    }

    // Preserve the existing auto-publish behavior for connected owners.
    // GitHub's manifest is updated with each successful publish; concurrent
    // calls would race and could overwrite another Pokémon's inventory entry.
    if (githubStorage.connected() && acceptedModels.some(model => !model.eggPlaceholder)) {
      githubBusy = true;
      githubDisconnectBtn.disabled = true;
      refreshGitHubPublishButton();
      const eligible = acceptedModels.filter(model => !model.eggPlaceholder);
      for (const [index, imported] of eligible.entries()) {
        githubStatus.textContent = "Publishing " + (index + 1) + "/" +
          eligible.length + " to GitHub: " + imported.name + "…";
        try {
          const entry = await githubStorage.publishModel(imported, {
            replaceExisting: githubOverrideExisting.checked,
          });
          published.push(entry);
          imported.githubPublished = true;
          if (savedDex.has(imported.dex)) {
            try { await gfpakStorage("save", imported); }
            catch (error) { console.warn("Could not save GitHub sync status", error); }
          }
        } catch (error) {
          publishFailures.push({
            dex: imported.dex, message: String(error?.message || error)
          });
          console.warn("Cannot publish GFPAK model", imported.dex, error);
        }
      }
      if (published.length) {
        const publishedDex = new Set(published.map(model => Number(model.dex)));
        mergeGitHubModels([
          ...published, ...models.filter(model =>
            model.githubTemporary && !publishedDex.has(Number(model.dex)))
        ]);
      }
      githubStatus.textContent = published.length + "/" + eligible.length +
        " Pokémon published to GitHub." +
        (publishFailures.length ? " Failed uploads remain locally available." : "");
    } else {
      githubStatus.textContent = githubStorage.connected()
        ? "Egg placeholders are local-only until explicitly published."
        : "Imports are local. Connect GitHub to publish them for everyone.";
    }

    const failedUploads = new Map(publishFailures.map(item => [Number(item.dex), item.message]));
    const publishedDex = new Set(published.map(model => Number(model.dex)));
    for (const item of outcome.results) {
      const row = document.createElement("li");
      const number = Number.isInteger(item.dex)
        ? " (#" + String(item.dex).padStart(4, "0") + ")" : "";
      const prefix = item.status === "imported" ? "✓ " :
        item.status === "skipped" ? "– " : "✗ ";
      const publishProblem = failedUploads.get(Number(item.dex));
      const detail = publishProblem
        ? item.detail + "; GitHub upload failed: " + publishProblem
        : publishedDex.has(Number(item.dex))
          ? item.detail + "; published to GitHub" : item.detail;
      row.textContent = prefix + item.name + number + ": " + detail;
      gfpakBatchResultsList.appendChild(row);
    }
    gfpakBatchSummary.textContent = "GFPAK ZIP results (" +
      outcome.imported + " imported, " + outcome.rejected + " rejected" +
      (outcome.skipped ? ", " + outcome.skipped + " skipped" : "") + ")";
    gfpakBatchResults.hidden = false;
    folderStatus.textContent = "Finished " + files.length + " ZIP" +
      (files.length === 1 ? "" : "s") + ": " + outcome.imported +
      " imported, " + outcome.rejected + " rejected" +
      (outcome.skipped ? ", " + outcome.skipped + " skipped" : "") +
      ". " + savedDex.size + " saved on this device." +
      (published.length ? " " + published.length + " published to GitHub." : "") +
      " See per-file results below.";
  } catch (error) {
    folderStatus.textContent = "GFPAK batch import interrupted: " +
      String(error?.message || error) + ". Successfully saved models remain available.";
    console.error("GFPAK batch import interrupted", error);
  } finally {
    githubBusy = false;
    githubDisconnectBtn.disabled = false;
    refreshGitHubPublishButton();
    importGfpakBtn.disabled = false;
    gfpakZipFile.value = "";
  }
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
    models = withMissingSpeciesEntries(outcome.models, false);
    restoreAnimationCoverage();
    window.POKEDEX3D_MODELS = models;
    folderStatus.textContent = outcome.models.length + " verified Switch models loaded locally. None were uploaded.";
    statusEl.textContent = catalogCoverageText(models);
    renderCoverage();
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

restoreAnimationCoverage();
statusEl.textContent = catalogCoverageText(models);
renderCoverage();

renderList();
if (models.length) {
  const savedDex = lastViewedDex();
  const savedIndex = models.findIndex(model => model.dex === savedDex);
  selectModel(savedIndex >= 0 ? savedIndex : 0, false);
} else {
  formSelect.replaceChildren();
  formSelect.disabled = true;
  resetAnimationSelect("No animations");
  messageEl.textContent = "Open a folder containing verified Switch GLBs, or use a site with published model assets.";
  messageEl.classList.remove("hidden");
}


async function restoreSavedGfpakModels() {
  try {
    // One-time reset: discard old browser imports while keeping imports made
    // after this baseline reset persistent across all later page reloads.
    const resetKey = "pokedex3d-manual-rebuild-20261012";
    if (localStorage.getItem(resetKey) !== "done") {
      const db = await gfpakDB();
      try {
        await new Promise((resolve, reject) => {
          const tx = db.transaction("models", "readwrite");
          tx.objectStore("models").clear();
          tx.oncomplete = resolve;
          tx.onerror = () => reject(tx.error);
        });
      } finally { db.close(); }
      localStorage.setItem(resetKey, "done");
    }
    const rows = await gfpakStorage("load");
    const restored = [];
    for (const row of rows) {
      try {
        if (!row.file || !Number.isInteger(row.dex)) continue;
        const model = {
          ...row, form: "regular", valid: true, ready: true,
          gfpakImport: true, url: "web/models/switch/" +
            String(row.dex).padStart(4, "0") + "/regular.glb"
        };
        await window.POKEDEX3D_MODEL_IDENTITY.verify(model, await model.file.arrayBuffer());
        const clips = await window.POKEDEX3D_LOCAL_SWITCH.inspectGlb(model.file);
        const idle = clips.find(name => /idle|wait|stand|breath|rest|fight[_ -]?a/i.test(name)
          && !/attack|damage|faint|death|down|bind|t[-_ ]?pose/i.test(name));
        if (!idle) continue;
        model.animations = clips;
        model.idleAnimation = clips.includes(row.idleAnimation) ? row.idleAnimation : idle;
        model.idleBreaks = [];
        restored.push(model);
      } catch (error) { console.warn("Invalid saved GFPAK model", row.dex, error); }
    }
    if (!restored.length) return;
    const selectedDex = currentModel?.dex;
    const drafts = restored.filter(model => model.githubPublished !== true);
    const synced = restored.filter(model => model.githubPublished === true);
    // Hosted models take precedence over previously published local copies;
    // never hide an unpublished, newer local edit.
    models = withMissingSpeciesEntries([...drafts,
      ...models.filter(model => model.githubTemporary),
      ...synced,
      ...models.filter(model => !restored.some(saved => saved.dex === Number(model.dex)))], false);
    window.POKEDEX3D_MODELS = models;
    restoreAnimationCoverage();
    statusEl.textContent = catalogCoverageText(models);
    renderCoverage();
    filtered = [...models]; renderList();
    const preferredDex = lastViewedDex() || selectedDex;
    const preferredIndex = filtered.findIndex(model => model.dex === preferredDex);
    selectModel(preferredIndex >= 0 ? preferredIndex : 0, false);
    folderStatus.textContent = restored.length + " saved GFPAK import(s) restored automatically.";
  } catch (error) {
    console.warn("Cannot reload saved GFPAK imports", error);
  }
}
void restoreSavedGfpakModels();
