/* Safeguard against Switch game-internal IDs being displayed as National Dex IDs.
 * This validates the actual GLB, not merely the label in a manifest.
 */
(() => {
  "use strict";
  const swsh = Object.freeze({"701":676,"702":708,"703":709,"704":667,"705":668,"706":664,"707":665,"708":666,"709":690,"710":691,"711":659,"712":660,"713":669,"714":670,"715":671,"716":714,"717":653,"718":654,"719":655,"720":650,"721":651,"722":652,"723":656,"724":657,"725":658,"726":686,"727":687,"728":672,"729":673,"730":675,"731":694,"732":695,"733":677,"734":678,"735":710,"736":711,"737":696,"738":697,"739":698,"740":699,"741":702,"742":684,"743":685,"744":679,"745":680,"746":681,"747":688,"748":689,"749":712,"751":713,"752":674,"753":661,"754":662,"755":663,"756":692,"757":693,"758":682,"759":683,"760":707,"761":701,"762":715,"763":704,"764":705,"765":706,"766":703,"767":700,"768":716,"769":717,"770":718,"772":719,"773":721,"774":720,"801":747,"802":748,"803":755,"804":756,"805":757,"806":758,"807":731,"808":732,"809":733,"810":765,"811":775,"812":761,"813":762,"814":763,"815":766,"816":782,"817":783,"818":784,"819":778,"820":746,"821":771,"822":769,"823":770,"824":774,"825":741,"826":734,"827":735,"828":744,"829":745,"830":785,"831":786,"832":787,"833":788,"834":742,"835":743,"836":736,"837":737,"838":738,"839":749,"840":750,"841":722,"842":723,"843":724,"844":725,"845":726,"846":727,"847":728,"848":729,"849":730,"850":751,"851":752,"852":759,"853":760,"854":776,"855":779,"856":780,"857":781,"858":777,"859":739,"860":740,"861":772,"862":773,"863":764,"865":800,"866":767,"867":768,"868":753,"869":754,"871":789,"872":790,"873":791,"874":792,"875":793,"876":799,"877":794,"878":796,"879":795,"880":798,"881":797,"882":801,"883":802,"884":805,"885":806,"886":803,"887":804,"888":807,"891":808,"892":809,"901":827,"902":828,"903":833,"904":834,"905":829,"906":830,"907":835,"908":836,"909":819,"910":820,"911":831,"912":832,"913":846,"914":847,"915":850,"916":851,"917":845,"918":821,"919":822,"920":823,"921":848,"922":849,"923":870,"924":868,"925":869,"926":878,"927":879,"928":862,"929":884,"930":824,"931":825,"932":826,"933":837,"934":838,"935":839,"936":843,"937":844,"938":888,"939":889,"940":890,"941":877,"942":876,"943":863,"944":871,"945":872,"946":873,"947":864,"948":810,"949":811,"950":812,"951":816,"952":817,"953":818,"954":813,"955":814,"956":815,"957":859,"958":860,"959":861,"960":880,"961":881,"962":882,"963":883,"964":852,"965":853,"966":840,"967":841,"968":842,"969":856,"970":857,"971":858,"972":854,"973":855,"974":874,"975":875,"976":885,"977":886,"978":887,"979":867,"980":866,"981":865,"982":891,"983":892,"984":896,"985":897,"986":898,"988":893,"989":894,"990":895});
  const sv = Object.freeze({"1001":899,"1002":900,"1003":903,"1004":905,"1005":904,"1006":902,"1007":901,"1010":906,"1011":907,"1012":908,"1013":909,"1014":910,"1015":911,"1016":912,"1017":913,"1018":914,"1019":915,"1020":916,"1021":982,"1022":917,"1023":918,"1024":919,"1025":920,"1026":953,"1027":954,"1028":971,"1029":972,"1030":955,"1031":956,"1032":981,"1033":960,"1034":961,"1035":977,"1036":976,"1037":963,"1038":964,"1039":928,"1040":929,"1041":930,"1042":951,"1043":952,"1044":938,"1045":939,"1046":965,"1047":966,"1048":968,"1049":924,"1050":925,"1051":974,"1052":975,"1053":996,"1054":997,"1055":998,"1056":978,"1057":967,"1058":921,"1059":922,"1060":923,"1061":940,"1062":941,"1063":962,"1064":931,"1065":973,"1066":950,"1067":932,"1068":933,"1069":934,"1070":969,"1071":970,"1072":944,"1073":945,"1074":926,"1075":927,"1076":942,"1077":943,"1078":946,"1079":947,"1080":999,"1081":1000,"1082":984,"1083":986,"1084":1009,"1085":989,"1086":985,"1087":987,"1088":988,"1089":1005,"1090":990,"1091":1010,"1092":994,"1093":992,"1094":993,"1095":995,"1096":991,"1097":1006,"1098":1003,"1099":1002,"1100":1001,"1101":1004,"1102":1007,"1103":1008,"1104":957,"1105":958,"1106":959,"1107":935,"1108":936,"1109":937,"1110":948,"1111":949,"1112":983,"1113":980,"1114":979,"1120":1017,"1121":1011,"1122":1019,"1123":1014,"1124":1015,"1125":1016,"1126":1020,"1127":1021,"1128":1023,"1129":1022,"1130":1024,"1131":1025,"1132":1018,"1133":1012,"1134":1013});
  const marker = /(?:^|[^a-z0-9])pm(\d{4})(?!\d)/ig;

  function gameName(value) {
    const source = String(value || "").toLowerCase().replace(/^official-game-assets:/, "");
    if (source.startsWith("sv") || source.startsWith("scarlet")) return "sv";
    if (source.startsWith("swsh") || source.startsWith("sword")) return "swsh";
    if (source.startsWith("la") || source.startsWith("pla")) return "la";
    if (source.startsWith("za")) return "za";
    return null;
  }

  function nationalDex(modelId, sourceGame) {
    const id = Number(modelId);
    const game = gameName(sourceGame);
    if (game === "sv") return id >= 1001 ? (sv[id] || 0) : (swsh[id] || id);
    if (game === "swsh") return swsh[id] || id;
    if ((game === "la" || game === "za") && id >= 1001 && id <= 1007) {
      return sv[id] || 0;
    }
    return id;
  }

  function glbDocument(bytes) {
    if (!(bytes instanceof ArrayBuffer) || bytes.byteLength < 24) {
      throw Error("Incomplete GLB model");
    }
    const view = new DataView(bytes);
    const jsonLength = view.getUint32(12, true);
    if (view.getUint32(0, true) !== 0x46546c67 ||
        view.getUint32(4, true) !== 2 ||
        view.getUint32(8, true) !== bytes.byteLength ||
        view.getUint32(16, true) !== 0x4e4f534a ||
        jsonLength < 2 || jsonLength > bytes.byteLength - 20 ||
        jsonLength > 24 * 1024 * 1024) throw Error("Corrupted GLB header");
    return JSON.parse(new TextDecoder().decode(new Uint8Array(bytes, 20, jsonLength)));
  }

  function embeddedModelId(doc) {
    // Blender may rename textures, so look for source codes in descending
    // confidence order and never resolve a conflicting set by guessing.
    for (const key of ["images", "meshes", "nodes", "materials"]) {
      const ids = new Set();
      for (const entry of doc[key] || []) {
        const name = String(entry && entry.name || "");
        marker.lastIndex = 0;
        for (const match of name.matchAll(marker)) ids.add(Number(match[1]));
      }
      if (ids.size === 1) return [...ids][0];
      if (ids.size > 1) return null;
    }
    return null;
  }

  async function gitBlobSha(bytes) {
    if (!globalThis.crypto?.subtle) return null;
    const header = new TextEncoder().encode("blob " + bytes.byteLength + "\u0000");
    const joined = new Uint8Array(header.length + bytes.byteLength);
    joined.set(header);
    joined.set(new Uint8Array(bytes), header.length);
    const digest = new Uint8Array(await globalThis.crypto.subtle.digest("SHA-1", joined));
    return [...digest].map(n => n.toString(16).padStart(2, "0")).join("");
  }

  async function verify(model, bytes) {
    const dex = Number(model?.dex);
    if (!Number.isInteger(dex) || dex < 1 || dex > 1025) {
      throw Error("Invalid National Dex entry");
    }
    const doc = glbDocument(bytes);
    const sha = await gitBlobSha(bytes);
    const statedSha = String(model?.sourceBlobSha || model?.sha || "").toLowerCase();
    if (sha && /^[a-f0-9]{40}$/.test(statedSha) && sha !== statedSha) {
      throw Error("Downloaded model differs from its verified inventory fingerprint");
    }
    const original = sha && window.POKEDEX3D_SOURCE_PROVENANCE?.[sha];
    const embedded = embeddedModelId(doc);
    const statedId = Number(model?.sourceModelId || model?.modelId || 0);
    const provenId = original ? Number(original[0]) : 0;
    const provenGame = original ? gameName(original[1]) : null;
    if (provenId && embedded && provenId !== embedded) {
      throw Error("Embedded source ID disagrees with the original game asset");
    }
    if (!provenId && embedded && statedId && embedded !== statedId) {
      throw Error("GLB contains pm" + embedded + " but the catalog lists pm" + statedId);
    }
    const id = provenId || embedded || statedId;
    const game = provenGame || gameName(model?.sourceGame || model?.source);
    if (game && id) {
      const actual = nationalDex(id, game);
      if (actual !== dex) {
        throw Error("Wrong Pokémon: " + game + " model pm" + id +
          " is National #" + actual + ", not #" + dex);
      }
    } else if (id >= 1008 && !statedSha) {
      // High Pokémon asset IDs are often S/V internal IDs.
      // Never guess that pm1025 is Pecharunt (#1025).
      throw Error("Unverified game-internal model ID pm" + id);
    }
    return { embeddedModelId: embedded, sourceGame: game, sourceModelId: id || null };
  }

  async function loadVerified(model, url, signal) {
    // Cache only GLBs that passed exact National Dex and source-binary checks.
    // Each URL includes an asset revision so fixes never replay stale models.
    let cache = null;
    if (globalThis.caches?.open) {
      try { cache = await globalThis.caches.open("pokedex3d-verified-switch-v2"); }
      catch (_) { /* Private-browsing and restrictive WebViews can disable caching. */ }
    }
    if (cache) {
      try {
        const saved = await cache.match(url);
        if (saved) {
          const bytes = await saved.arrayBuffer();
          try {
            await verify(model, bytes);
            return bytes;
          } catch (_) {
            await cache.delete(url);
          }
        }
      } catch (_) { /* A broken cache must not prevent a normal network fetch. */ }
    }
    const response = await fetch(url, { mode: "cors", signal });
    if (!response.ok) throw Error("Model download failed (HTTP " + response.status + ")");
    const bytes = await response.arrayBuffer();
    await verify(model, bytes);
    if (cache && typeof Response !== "undefined") {
      try {
        await cache.put(url, new Response(bytes, {
          headers: { "Content-Type": "model/gltf-binary" },
        }));
      } catch (_) { /* Quota limits are fine: models still render. */ }
    }
    return bytes;
  }

  window.POKEDEX3D_MODEL_IDENTITY = Object.freeze({
    verify, embeddedModelId, glbDocument, nationalDex, loadVerified,
  });
})();
