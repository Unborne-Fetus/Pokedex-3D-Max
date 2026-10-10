/* External candidate previews: no copyrighted model bytes are bundled or republished.
 * Source commit is pinned to the GLBs structurally audited in run 38027082807.
 * These are NOT verified Switch originals and do not count as Finished Pokémon.
 */
(() => {
  "use strict";

  const SOURCE_REPO = "pokemon-party/3d-pokemon";
  const SOURCE_COMMIT = "429de1288cea0d43f5b4f56305d2276e94239d65";
  const ROOT = "https://raw.githubusercontent.com/" + SOURCE_REPO + "/" +
    SOURCE_COMMIT + "/models/opt/regular/";
  const SOURCE_PAGE = "https://github.com/" + SOURCE_REPO + "/blob/" +
    SOURCE_COMMIT + "/models/opt/regular/";
  const AUDITED = [
  {
    "dex": 645,
    "file": "645.glb",
    "revision": "541b334734016bb7748697d165e17f8b5b604498"
  },
  {
    "dex": 899,
    "file": "899.glb",
    "revision": "e13f0816bccc6ec2bea529b93098cec52b97b4fe"
  },
  {
    "dex": 900,
    "file": "900.glb",
    "revision": "22aaf5e9f4ab8003189426a4ce65087ff267fb8e"
  },
  {
    "dex": 905,
    "file": "905.glb",
    "revision": "baf47a36cd33ed95a17b76ea9feb80c6535cf1a0"
  },
  {
    "dex": 911,
    "file": "911.glb",
    "revision": "4b3e65afc1a92e5813e085ff783defa0d475082e"
  },
  {
    "dex": 916,
    "file": "916-M.glb",
    "revision": "f6674ad705b9e51222d290458a825eeb32fa722d"
  },
  {
    "dex": 916,
    "file": "916-F.glb",
    "revision": "b635c6486a91d7ecfe871fd6996e1eeeaa1dafad"
  },
  {
    "dex": 941,
    "file": "941.glb",
    "revision": "92acbcc91745a0c07efc51e33eb1948aef412444"
  },
  {
    "dex": 947,
    "file": "947.glb",
    "revision": "c3ad078ee5d505b03a15f7662338dd1d7e320912"
  },
  {
    "dex": 981,
    "file": "981.glb",
    "revision": "589f7cc21628568423fd3fa0376306748b597f25"
  },
  {
    "dex": 983,
    "file": "983.glb",
    "revision": "99b0c3eb9f0f380097862488bc007b1fb817df3e"
  },
  {
    "dex": 987,
    "file": "987.glb",
    "revision": "cf74959d5c3722c982b7e3a8b4b15585030b58f6"
  },
  {
    "dex": 994,
    "file": "994.glb",
    "revision": "065914ad0e21b11e02b1ef0a5377118efe55e7ab"
  },
  {
    "dex": 995,
    "file": "995.glb",
    "revision": "1be877f05ee72603d9a60421d2edebbe64b5c0de"
  },
  {
    "dex": 999,
    "file": "999.glb",
    "revision": "b80dcdc1c4cd0016d840e3ab88b723e399a56934"
  },
  {
    "dex": 1000,
    "file": "1000.glb",
    "revision": "06d35c7ef80a2f84e7f22c61d3231cc858378b14"
  },
  {
    "dex": 1003,
    "file": "1003.glb",
    "revision": "eff5026fdf6fb06cf742d59ed155e553742f8e84"
  },
  {
    "dex": 1004,
    "file": "1004.glb",
    "revision": "3bb19085f4c95c19a69ae974e81b90fbcd81fc66"
  }
];
  const IDLE = /default(?:idle|wait)|battle(?:idle|wait)|fight[_ -]?a|idle|wait|stand|breath|rest/i;
  const NOT_IDLE = /attack|damage|faint|death|down|hit|move|run|walk|jump|bind|t[-_ ]?pose/i;

  const byDex = new Map();
  for (const row of AUDITED) {
    if (!byDex.has(row.dex)) byDex.set(row.dex, []);
    const variant = {
      name: row.file,
      label: row.file.endsWith("-F.glb") ? "Female" :
        row.file.endsWith("-M.glb") ? "Male" : "Regular",
      url: ROOT + row.file,
      sourcePage: SOURCE_PAGE + row.file,
      revision: row.revision,
    };
    byDex.get(row.dex).push(Object.freeze(variant));
  }

  const models = Object.freeze([...byDex.entries()].map(([dex, variants]) => {
    // Default Oinkologne to male; both genders were separately audited.
    const chosen = variants.find(item => item.label === "Male") || variants[0];
    return {
      dex, name: window.POKEDEX3D_NAMES?.[dex] || "#" + String(dex).padStart(4, "0"),
      form: "regular", url: chosen.url, assetRevision: chosen.revision,
      sourcePage: chosen.sourcePage, variantLabel: chosen.label,
      variants: [...variants], communityCandidate: true, remoteSwitch: true,
      source: "third-party-preview:" + SOURCE_REPO,
      ready: true, valid: true, preflightRequired: true,
      idleAnimation: null, idleBreaks: [],
      auditRun: "38027082807",
    };
  }).sort((a, b) => a.dex - b.dex));

  const allowed = new Map([...byDex.entries()].map(([dex, variants]) =>
    [dex, new Set(variants.map(v => v.url))]));
  function isCandidateURL(dex, url) {
    return Boolean(allowed.get(Number(dex))?.has(String(url)));
  }

  function parseGlb(data) {
    if (!(data instanceof ArrayBuffer) || data.byteLength < 32) {
      throw Error("Community preview is not a complete GLB");
    }
    const view = new DataView(data);
    const jsonLength = view.getUint32(12, true);
    if (view.getUint32(0, true) !== 0x46546c67 ||
        view.getUint32(4, true) !== 2 ||
        view.getUint32(8, true) !== data.byteLength ||
        view.getUint32(16, true) !== 0x4e4f534a ||
        jsonLength < 2 || jsonLength > data.byteLength - 20 ||
        jsonLength > 24 * 1024 * 1024) {
      throw Error("Community preview has invalid GLB metadata");
    }
    let doc;
    try {
      doc = JSON.parse(new TextDecoder("utf-8").decode(
        new Uint8Array(data, 20, jsonLength)));
    } catch (_) {
      throw Error("Community preview has corrupted JSON");
    }
    const binStart = 20 + jsonLength;
    if (binStart + 8 > data.byteLength || view.getUint32(binStart + 4, true) !== 0x004e4942) {
      throw Error("Community preview has no GLB binary data");
    }
    const binarySize = view.getUint32(binStart, true);
    if (binStart + 8 + binarySize !== data.byteLength) {
      throw Error("Community preview binary size is inconsistent");
    }
    return { doc, binary: new Uint8Array(data, binStart + 8, binarySize) };
  }

  function validImage(doc, binary, index) {
    const image = doc.images?.[index];
    if (!image) return false;
    if (Number.isInteger(image.bufferView)) {
      const buffer = doc.bufferViews?.[image.bufferView];
      if (!buffer) return false;
      const start = Number(buffer.byteOffset || 0);
      const size = Number(buffer.byteLength || 0);
      if (!Number.isSafeInteger(start) || !Number.isSafeInteger(size) ||
          start < 0 || size < 12 || start + size > binary.length) return false;
      const bytes = binary.subarray(start, start + Math.min(size, 12));
      if (image.mimeType === "image/png") {
        return bytes[0] === 137 && bytes[1] === 80 && bytes[2] === 78 && bytes[3] === 71;
      }
      if (image.mimeType === "image/jpeg") return bytes[0] === 255 && bytes[1] === 216;
      if (image.mimeType === "image/webp") {
        return bytes[0] === 82 && bytes[1] === 73 && bytes[2] === 70 &&
          bytes[3] === 70 && bytes[8] === 87 && bytes[9] === 69 &&
          bytes[10] === 66 && bytes[11] === 80;
      }
      if (image.mimeType === "image/ktx2") return bytes[0] === 171 && bytes[1] === 75;
      return false;
    }
    return typeof image.uri === "string" && /^data:image\/(png|jpeg|webp|ktx2);base64,/i.test(image.uri);
  }

  function inspect(data) {
    const { doc, binary } = parseGlb(data);
    if (!Array.isArray(doc.meshes) || !doc.meshes.length ||
        !Array.isArray(doc.scenes) || !doc.scenes.length) {
      throw Error("Community preview contains no scene or mesh");
    }
    const materials = doc.materials || [];
    const textures = doc.textures || [];
    const materialIndices = new Set();
    let primitiveCount = 0;
    for (const mesh of doc.meshes) {
      for (const primitive of mesh.primitives || []) {
        primitiveCount++;
        if (!Number.isInteger(primitive.material)) {
          throw Error("Community preview has a primitive without material");
        }
        materialIndices.add(primitive.material);
      }
    }
    if (!primitiveCount || !materialIndices.size) {
      throw Error("Community preview has no drawable textured mesh");
    }

    for (const index of materialIndices) {
      const material = materials[index];
      const texIndex = material?.pbrMetallicRoughness?.baseColorTexture?.index;
      if (!Number.isInteger(texIndex) || !textures[texIndex]) {
        throw Error("Community preview contains an untextured mesh material");
      }
      const texture = textures[texIndex];
      const ext = texture.extensions || {};
      const source = ext.EXT_texture_webp?.source ??
        ext.KHR_texture_basisu?.source ?? texture.source;
      if (!Number.isInteger(source) || !validImage(doc, binary, source)) {
        throw Error("Community preview has an incomplete embedded base-color texture");
      }
    }

    const accessors = doc.accessors || [];
    const nodes = doc.nodes || [];
    const valid = (doc.animations || [])
      .map((clip, i) => ({ clip, name: String(clip.name || "animation_" + i) }))
      .filter(({ clip }) => (clip.channels || []).some(channel => {
        const sampler = clip.samplers?.[channel.sampler];
        const target = channel.target || {};
        return sampler && Number.isInteger(sampler.input) &&
          Number.isInteger(sampler.output) &&
          accessors[sampler.input] && accessors[sampler.output] &&
          (!Number.isInteger(target.node) || nodes[target.node]) &&
          ["rotation", "translation", "scale", "weights"].includes(target.path);
      }));
    const idle = valid.find(({ name }) => IDLE.test(name) && !NOT_IDLE.test(name));
    if (!idle) throw Error("Community preview has no verifiable named idle animation");
    return { idleAnimation: idle.name, animations: valid.map(row => row.name) };
  }

  window.POKEDEX3D_COMMUNITY_CANDIDATES = Object.freeze({
    models, isCandidateURL, inspect, sourceRepository: SOURCE_REPO,
  });
})();
