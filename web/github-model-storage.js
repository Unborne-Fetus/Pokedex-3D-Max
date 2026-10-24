"use strict";

/* Temporary GitHub model storage for the static Pokédex site.
 * Reading is public. Publishing uses a user-supplied, repo-scoped GitHub
 * fine-grained token held ONLY in memory, never in pages, URLs or storage.
 * Remove this module and the temporary-imports directory when retired. */
(() => {
  const OWNER = "Unborne-Fetus";
  const REPO = "Pokedex-3D-Models-Animations";
  const BRANCH = "main";
  const DIR = "temporary-imports";
  const ROOT = `https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}/${DIR}/`;
  const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
  const MAX_BYTES = 40 * 1024 * 1024; // Larger files need a non-Git storage backend.
  const FORMAT = "pokedex3d-temporary-github-imports";
  const PERMISSION_HELP = "Edit or recreate your fine-grained token with Resource owner: " +
    OWNER + ", Repository access: Only select repositories → " + REPO +
    ", and Repository permissions → Contents: Read and write. Reconnect using the updated token; do not share it.";
  let token = "";
  let account = "";

  function validDex(value) {
    const dex = Number(value);
    return Number.isInteger(dex) && dex >= 1 && dex <= 1025 ? dex : null;
  }
  function pathFor(dex) {
    return `${DIR}/${String(dex).padStart(4, "0")}/regular.glb`;
  }
  function checkedManifest(raw) {
    if (!raw || raw.format !== 1 || raw.source !== FORMAT ||
        !Array.isArray(raw.entries)) throw Error("Unrecognized GitHub model inventory");
    return raw;
  }
  function fromManifest(raw) {
    const manifest = checkedManifest(raw);
    const result = new Map();
    for (const row of manifest.entries) {
      const dex = validDex(row?.dex);
      if (!dex || row.path !== pathFor(dex) ||
          !/^[0-9a-f]{40}$/i.test(String(row.sha || "")) ||
          !Number.isSafeInteger(row.bytes) || row.bytes <= 0) continue;
      const url = new URL(`${String(dex).padStart(4, "0")}/regular.glb`, ROOT);
      url.searchParams.set("rev", row.sha);
      result.set(dex, {
        dex, name: window.POKEDEX3D_NAMES?.[dex] || row.name || ("#" + dex),
        form: "regular", url: url.href, ready: true, valid: true,
        remoteSwitch: true, githubTemporary: true, gfpakImport: row.gfpakImport === true,
        orientation: typeof row.orientation === "string" ? row.orientation : "0deg 90deg 0deg",
        orientationVersion: row.orientationVersion,
        sourceGame: row.sourceGame || null,
        sourceModelId: row.eggPlaceholder === true ? 0 : (Number(row.sourceModelId) || null),
        eggPlaceholder: row.eggPlaceholder === true,
        sourceBlobSha: row.sha, assetRevision: row.sha, bytes: row.bytes,
        idleAnimation: row.idleAnimation || null, idleBreaks: [],
      });
    }
    return [...result.values()].sort((a, b) => a.dex - b.dex);
  }
  function publicManifestUrl() {
    return ROOT + "manifest.json?t=" + Date.now();
  }
  async function load() {
    const response = await fetch(publicManifestUrl(), { mode: "cors", cache: "no-store" });
    if (!response.ok) throw Error("GitHub model catalog unavailable (HTTP " + response.status + ")");
    return fromManifest(await response.json());
  }
  async function request(path, options = {}) {
    if (!token) throw Error("Connect your GitHub account before uploading");
    const headers = {
      Accept: "application/vnd.github+json",
      Authorization: "Bearer " + token,
    };
    if (options.body != null) headers["Content-Type"] = "application/json";
    let response;
    try {
      response = await fetch(path.startsWith("https:") ? path : API + path, {
        method: options.method || "GET", headers,
        body: options.body == null ? undefined : JSON.stringify(options.body),
        cache: "no-store", mode: "cors",
      });
    } catch (_) {
      throw Error("Cannot contact GitHub. Check your connection and browser permissions");
    }
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const reason = String(result.message || "request failed").slice(0, 180);
      const stage = options.stage || "the request";
      if (response.status === 401) {
        throw Error("GitHub rejected " + stage + " (HTTP 401). The token is invalid or expired. " +
          PERMISSION_HELP);
      }
      if (response.status === 403) {
        throw Error("GitHub denied " + stage + " for " + OWNER + "/" + REPO +
          " (HTTP 403: " + reason + "). " + PERMISSION_HELP +
          " If the write check succeeded but publishing still fails, inspect the main branch rules.");
      }
      throw Error("GitHub rejected " + stage + " (HTTP " + response.status +
        ": " + reason + ")");
    }
    return result;
  }
  async function connect(credential) {
    if (!String(credential || "").trim().startsWith("github_pat_")) {
      throw Error("Enter a GitHub fine-grained personal access token");
    }
    token = String(credential).trim();
    try {
      const response = await fetch("https://api.github.com/user", {
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: "Bearer " + token,
            },
        mode: "cors", cache: "no-store",
      });
      if (!response.ok) throw Error("GitHub authentication failed (HTTP " + response.status + ")");
      const user = await response.json();
      if (String(user.login || "").toLowerCase() !== OWNER.toLowerCase()) {
        throw Error("Only the repository owner may publish Pokémon models");
      }
      const repo = await request("", { stage: "repository access check" });
      if (repo.permissions?.push !== true) {
        throw Error("GitHub did not confirm repository push access for " + OWNER + "/" +
          REPO + ". " + PERMISSION_HELP);
      }
      // A public repository's GET response can report the user's push rights
      // even when a fine-grained PAT lacks Contents write permission. Verify
      // actual write authorization BEFORE accepting automated model imports.
      // This creates only a tiny *unreferenced* Git blob (no commit, branch,
      // file, manifest or uploaded model is changed).
      const probe = await request("/git/blobs", {
        method: "POST",
        stage: "the safe write-permission check",
        body: {
          content: "Pokedex 3D Max temporary storage permission check",
          encoding: "utf-8",
        },
      });
      if (!/^[0-9a-f]{40}$/i.test(String(probe.sha || ""))) {
        throw Error("GitHub did not confirm write access to " + OWNER + "/" + REPO);
      }
      account = user.login;
      return account;
    } catch (error) {
      disconnect();
      throw error;
    }
  }
  function disconnect() {
    token = "";
    account = "";
  }
  function connected() { return !!token && !!account; }

  function base64(buffer) {
    const bytes = new Uint8Array(buffer);
    const chunk = 0x8000;
    const pieces = [];
    for (let offset = 0; offset < bytes.length; offset += chunk) {
      pieces.push(String.fromCharCode(...bytes.subarray(offset, offset + chunk)));
    }
    return btoa(pieces.join(""));
  }
  function decodeBase64(value) {
    const decoded = atob(String(value).replace(/\s/g, ""));
    return new TextDecoder().decode(Uint8Array.from(decoded, letter => letter.charCodeAt(0)));
  }
  async function currentManifest() {
    try {
      const result = await request("/contents/" + DIR + "/manifest.json?ref=" + BRANCH);
      return checkedManifest(JSON.parse(decodeBase64(result.content)));
    } catch (error) {
      // Fail closed: do not silently discard a catalog on 403/404/invalid JSON.
      throw Error("Could not read the existing GitHub inventory: " + error.message);
    }
  }
  function validatedOrientation(model) {
    const value = String(model?.orientation || (model?.gfpakImport ? "0deg 0deg 0deg" : "0deg 90deg 0deg"));
    if (!/^-?\d{1,3}deg(?: -?\d{1,3}deg){2}$/.test(value)) {
      throw Error("Choose a supported three-axis model orientation before publishing");
    }
    return value;
  }
  function verifiedAnimation(model, animations) {
    const preferred = String(model?.idleAnimation || "");
    if (preferred && !animations.includes(preferred)) {
      throw Error("Selected default animation is missing from the uploaded model");
    }
    return preferred || animations.find(name => /idle|wait|stand|breath|rest/i.test(name)) || animations[0];
  }
  async function publishModel(model, options = {}) {
    if (!connected()) throw Error("Connect GitHub first");
    const dex = validDex(model?.dex);
    if (!dex || !(model.file instanceof File)) {
      throw Error("Select an imported, verified Pokémon model first");
    }
    if (model.file.size <= 0 || model.file.size > MAX_BYTES) {
      throw Error("GitHub temporary storage accepts models up to 40 MiB. Model remains on this device.");
    }
    const bytes = await model.file.arrayBuffer();
    await window.POKEDEX3D_MODEL_IDENTITY.verify(model, bytes);
    const animations = await window.POKEDEX3D_LOCAL_SWITCH.inspectGlb(model.file);
    if (!animations.length) throw Error("This model has no usable animations");
    const idleAnimation = verifiedAnimation(model, animations);
    const orientation = validatedOrientation(model);
    // Re-read HEAD and manifest immediately before creating the commit.
    const head = await request("/git/ref/heads/" + BRANCH, { stage: "reading the main branch" });
    const parentSha = head.object?.sha;
    if (!/^[0-9a-f]{40}$/i.test(parentSha || "")) throw Error("Cannot identify GitHub branch");
    const parent = await request("/git/commits/" + parentSha, { stage: "reading the parent commit" });
    const manifest = await currentManifest();
    if (manifest.entries.some(item => Number(item.dex) === dex) &&
        options.replaceExisting !== true) {
      throw Error("Pokémon #" + String(dex).padStart(4, "0") +
        " is already published. Enable Override existing model to replace it.");
    }
    const fileBlob = await request("/git/blobs", {
      method: "POST", stage: "uploading the model blob",
      body: { content: base64(bytes), encoding: "base64" },
    });
    const now = new Date().toISOString();
    const entry = {
      dex, name: String(model.name || window.POKEDEX3D_NAMES?.[dex] || ""),
      path: pathFor(dex), sha: fileBlob.sha, bytes: model.file.size,
      sourceGame: model.sourceGame || null,
      sourceModelId: model.eggPlaceholder === true ? 0 : (Number(model.sourceModelId) || null),
      eggPlaceholder: model.eggPlaceholder === true,
      gfpakImport: model.gfpakImport === true,
      orientation, orientationVersion: 2,
      idleAnimation,
      updatedAt: now,
    };
    manifest.entries = manifest.entries
      .filter(item => Number(item?.dex) !== dex).concat(entry)
      .sort((a, b) => Number(a.dex) - Number(b.dex));
    const manifestBlob = await request("/git/blobs", {
      method: "POST", stage: "uploading the updated model inventory",
      body: { content: JSON.stringify(manifest, null, 2) + "\n", encoding: "utf-8" },
    });
    const tree = await request("/git/trees", {
      method: "POST", stage: "preparing the model commit",
      body: {
        base_tree: parent.tree.sha,
        tree: [
          { path: entry.path, mode: "100644", type: "blob", sha: fileBlob.sha },
          { path: DIR + "/manifest.json", mode: "100644", type: "blob", sha: manifestBlob.sha },
        ],
      },
    });
    const commit = await request("/git/commits", {
      method: "POST", stage: "creating the model commit",
      body: {
        message: "Save Pokémon #" + String(dex).padStart(4, "0") + " from Pokédex 3D Max",
        tree: tree.sha, parents: [parentSha],
      },
    });
    // No force push: conflicts fail rather than overwriting another upload.
    await request("/git/refs/heads/" + BRANCH, {
      method: "PATCH", stage: "updating the main branch",
      body: { sha: commit.sha, force: false },
    });
    return fromManifest({ format: 1, source: FORMAT, entries: [entry] })[0];
  }

  // Update appearance and preferred animation for a previously published
  // temporary import without uploading or replacing its GLB contents.
  async function saveModelSettings(model) {
    if (!connected()) throw Error("Connect GitHub first");
    const dex = validDex(model?.dex);
    if (!dex || model.githubTemporary !== true) {
      throw Error("Only previously published temporary models can be edited without a local GLB");
    }
    const orientation = validatedOrientation(model);
    if (!model?.idleAnimation || !Array.isArray(model.animations) ||
        !model.animations.includes(model.idleAnimation)) {
      throw Error("Load the model and choose a playable default animation first");
    }
    const head = await request("/git/ref/heads/" + BRANCH, { stage: "reading the main branch" });
    const parentSha = head.object?.sha;
    if (!/^[0-9a-f]{40}$/i.test(parentSha || "")) throw Error("Cannot identify GitHub branch");
    const parent = await request("/git/commits/" + parentSha, { stage: "reading the parent commit" });
    const manifest = await currentManifest();
    const index = manifest.entries.findIndex(row => Number(row.dex) === dex);
    if (index < 0) throw Error("The published model is missing. Refresh its GitHub catalog.");
    const existing = manifest.entries[index];
    if (existing.path !== pathFor(dex)) throw Error("Cannot edit an unexpected model path");
    const entry = { ...existing, orientation, orientationVersion: 2,
      idleAnimation: model.idleAnimation, updatedAt: new Date().toISOString() };
    manifest.entries[index] = entry;
    const manifestBlob = await request("/git/blobs", {
      method: "POST", stage: "uploading model settings",
      body: { content: JSON.stringify(manifest, null, 2) + "\n", encoding: "utf-8" },
    });
    const tree = await request("/git/trees", {
      method: "POST", stage: "preparing settings commit",
      body: { base_tree: parent.tree.sha,
        tree: [{ path: DIR + "/manifest.json", mode: "100644",
          type: "blob", sha: manifestBlob.sha }] },
    });
    const commit = await request("/git/commits", {
      method: "POST", stage: "creating settings commit",
      body: { message: "Set default orientation and animation for #" + dex,
        tree: tree.sha, parents: [parentSha] },
    });
    await request("/git/refs/heads/" + BRANCH, {
      method: "PATCH", stage: "updating settings on main",
      body: { sha: commit.sha, force: false },
    });
    return fromManifest({ format: 1, source: FORMAT, entries: [entry] })[0];
  }

  async function publishModels(models, options = {}) {
    if (!connected()) throw Error("Connect GitHub first");
    if (!Array.isArray(models)) throw Error("Choose local model files to publish");
    const unique = new Map();
    for (const model of models) {
      if (model?.file instanceof File && validDex(model.dex)) unique.set(Number(model.dex), model);
    }
    const result = { published: [], skipped: [], failed: [] };
    let position = 0;
    for (const model of unique.values()) {
      position++;
      options.onProgress?.(position, unique.size, model);
      try {
        result.published.push(await publishModel(model, {
          replaceExisting: options.replaceExisting === true,
        }));
      } catch (error) {
        const item = { dex: model.dex, message: String(error?.message || error) };
        if (/already published/.test(item.message)) result.skipped.push(item);
        else result.failed.push(item);
        if (/HTTP 40[13]/.test(item.message)) break;
      }
    }
    return result;
  }

  window.POKEDEX3D_GITHUB_STORAGE = Object.freeze({
    load, connect, disconnect, connected, publishModel, publishModels, saveModelSettings,
    storageRepository: OWNER + "/" + REPO,
  });
})();
