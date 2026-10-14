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
      throw Error("GitHub HTTP " + response.status + ": " +
        String(result.message || "request failed").slice(0, 220));
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
      const repo = await request("");
      if (repo.permissions?.push !== true) {
        throw Error("Token needs Contents: Read and write on " + REPO);
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
  async function publishModel(model) {
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
    // Re-read HEAD and manifest immediately before creating the commit.
    const head = await request("/git/ref/heads/" + BRANCH);
    const parentSha = head.object?.sha;
    if (!/^[0-9a-f]{40}$/i.test(parentSha || "")) throw Error("Cannot identify GitHub branch");
    const parent = await request("/git/commits/" + parentSha);
    const manifest = await currentManifest();
    const fileBlob = await request("/git/blobs", {
      method: "POST", body: { content: base64(bytes), encoding: "base64" },
    });
    const now = new Date().toISOString();
    const entry = {
      dex, name: String(model.name || window.POKEDEX3D_NAMES?.[dex] || ""),
      path: pathFor(dex), sha: fileBlob.sha, bytes: model.file.size,
      sourceGame: model.sourceGame || null,
      sourceModelId: model.eggPlaceholder === true ? 0 : (Number(model.sourceModelId) || null),
      eggPlaceholder: model.eggPlaceholder === true,
      gfpakImport: model.gfpakImport === true,
      orientation: model.gfpakImport
        ? window.POKEDEX3D_GFPAK_ZIP.orientation(model) : model.orientation || "0deg 90deg 0deg",
      orientationVersion: model.gfpakImport ? 2 : model.orientationVersion,
      idleAnimation: model.idleAnimation || null,
      updatedAt: now,
    };
    manifest.entries = manifest.entries
      .filter(item => Number(item?.dex) !== dex).concat(entry)
      .sort((a, b) => Number(a.dex) - Number(b.dex));
    const manifestBlob = await request("/git/blobs", {
      method: "POST",
      body: { content: JSON.stringify(manifest, null, 2) + "\n", encoding: "utf-8" },
    });
    const tree = await request("/git/trees", {
      method: "POST",
      body: {
        base_tree: parent.tree.sha,
        tree: [
          { path: entry.path, mode: "100644", type: "blob", sha: fileBlob.sha },
          { path: DIR + "/manifest.json", mode: "100644", type: "blob", sha: manifestBlob.sha },
        ],
      },
    });
    const commit = await request("/git/commits", {
      method: "POST",
      body: {
        message: "Save Pokémon #" + String(dex).padStart(4, "0") + " from Pokédex 3D Max",
        tree: tree.sha, parents: [parentSha],
      },
    });
    // No force push: conflicts fail rather than overwriting another upload.
    await request("/git/refs/heads/" + BRANCH, {
      method: "PATCH", body: { sha: commit.sha, force: false },
    });
    return fromManifest({ format: 1, source: FORMAT, entries: [entry] })[0];
  }

  window.POKEDEX3D_GITHUB_STORAGE = Object.freeze({
    load, connect, disconnect, connected, publishModel,
    storageRepository: OWNER + "/" + REPO,
  });
})();
