/* Local-only GFPAK ZIP -> already-converted GLB extraction.
 * No uploads, external ZIP library, Blender, or automatic catalog overwrites.
 * A browser preview does not write the Pokémon into the desktop install.
 */
(function () {
  'use strict';
  const decoder = new TextDecoder();
  const MAX_ZIP = 512 * 1024 * 1024;
  const MAX_GLB = 256 * 1024 * 1024;
  const MANIFEST = 'gfpak-pokemon-export.json';
  const MODEL = 'pokedex3d/regular.glb';
  const GAMES = new Set(['lgpe', 'swsh', 'la', 'sv', 'za', 'bdsp']);

  function zipDirectory(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let end = -1;
    for (let i = bytes.byteLength - 22; i >= Math.max(0, bytes.byteLength - 65557); i--) {
      if (view.getUint32(i, true) === 0x06054b50) { end = i; break; }
    }
    if (end < 0) throw Error('Not a readable ZIP archive');
    const size = view.getUint32(end + 12, true);
    let cursor = view.getUint32(end + 16, true);
    const count = view.getUint16(end + 10, true);
    if (size === 0xffffffff || cursor === 0xffffffff || count === 0xffff ||
        cursor + size > end || count > 100000) {
      throw Error('Unsupported ZIP64 or invalid ZIP directory');
    }
    const results = new Map();
    for (let i = 0; i < count; i++) {
      if (cursor + 46 > bytes.byteLength || view.getUint32(cursor, true) !== 0x02014b50)
        throw Error('Damaged ZIP directory');
      const method = view.getUint16(cursor + 10, true);
      const compressed = view.getUint32(cursor + 20, true);
      const sizeOut = view.getUint32(cursor + 24, true);
      const nameLen = view.getUint16(cursor + 28, true);
      const extraLen = view.getUint16(cursor + 30, true);
      const commentLen = view.getUint16(cursor + 32, true);
      const offset = view.getUint32(cursor + 42, true);
      const next = cursor + 46 + nameLen + extraLen + commentLen;
      if (next > bytes.byteLength) throw Error('Truncated ZIP filename');
      const name = decoder.decode(bytes.subarray(cursor + 46, cursor + 46 + nameLen));
      if (name.startsWith('/') || name.split('/').includes('..') || /^[a-z]:/i.test(name))
        throw Error('Unsafe ZIP member path');
      if (results.has(name.toLowerCase())) throw Error('Ambiguous duplicate ZIP member');
      results.set(name.toLowerCase(), {name, method, compressed, sizeOut, offset});
      cursor = next;
    }
    return results;
  }

  async function readEntry(bytes, entries, name, limit) {
    const entry = entries.get(name.toLowerCase());
    if (!entry) throw Error('ZIP has no ' + name);
    if (entry.sizeOut > limit || entry.compressed > MAX_ZIP)
      throw Error('ZIP entry exceeds safe import size');
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const start = entry.offset;
    if (start + 30 > bytes.byteLength || view.getUint32(start, true) !== 0x04034b50)
      throw Error('Broken ZIP file header');
    const dataStart = start + 30 + view.getUint16(start + 26, true)
      + view.getUint16(start + 28, true);
    if (dataStart + entry.compressed > bytes.byteLength)
      throw Error('Truncated ZIP member');
    const compressed = bytes.slice(dataStart, dataStart + entry.compressed);
    let result;
    if (entry.method === 0) {
      result = compressed;
    } else if (entry.method === 8) {
      if (typeof DecompressionStream === 'undefined')
        throw Error('This browser cannot unzip deflate archives. Use import-gfpak-pokemon.bat on Windows.');
      const stream = new Blob([compressed]).stream()
        .pipeThrough(new DecompressionStream('deflate-raw'));
      result = new Uint8Array(await new Response(stream).arrayBuffer());
    } else {
      throw Error('Unsupported ZIP compression method: ' + entry.method);
    }
    if (result.byteLength !== entry.sizeOut || result.byteLength > limit)
      throw Error('Incorrect decompressed ZIP member size');
    return result;
  }

  async function read(file) {
    if (!file || file.size <= 0 || file.size > MAX_ZIP)
      throw Error('Select a GFPAK ZIP no larger than 512 MiB');
    const raw = new Uint8Array(await file.arrayBuffer());
    const entries = zipDirectory(raw);
    const meta = JSON.parse(decoder.decode(await readEntry(raw, entries, MANIFEST, 65536)));
    if (meta?.format !== 'gfpak-pokemon-export' || meta.version !== 1)
      throw Error('ZIP was not exported by a compatible GFPAK Open version');
    if (meta.convertedModel !== MODEL)
      throw Error('This ZIP has original assets only. Re-export after textures and animations finish loading.');
    const selected = String(meta.selectedModel || '');
    const ids = [...selected.matchAll(/(?:^|[^a-z0-9])pm(\d{4})(?!\d)/ig)]
      .map(match => Number(match[1]));
    if (new Set(ids).size !== 1)
      throw Error('Cannot identify the selected Pokémon from the original model filename');
    const modelId = ids[0];
    const game = meta.sourceGame === 'pla' ? 'la' : String(meta.sourceGame || '');
    if (!GAMES.has(game))
      throw Error('Unknown source game. Choose the correct Game Source in GFPAK and export again.');
    const dex = window.POKEDEX3D_MODEL_IDENTITY.nationalDex(modelId, game);
    if (!Number.isInteger(dex) || dex < 1 || dex > 1025)
      throw Error('Unmapped game-internal Pokémon ID pm' + modelId);
    const glb = await readEntry(raw, entries, MODEL, MAX_GLB);
    const buffer = glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength);
    const model = {
      dex, form:'regular', sourceGame:game, sourceModelId:modelId,
      name: window.POKEDEX3D_NAMES?.[dex] || '#' + String(dex).padStart(4, '0'),
      url:'web/models/switch/' + String(dex).padStart(4, '0') + '/regular.glb',
      file: new File([buffer], 'regular.glb', {type:'model/gltf-binary'}),
      valid:true, ready:true
    };
    await window.POKEDEX3D_MODEL_IDENTITY.verify(model, buffer);
    const clips = await window.POKEDEX3D_LOCAL_SWITCH.inspectGlb(model.file);
    if (!clips?.length) throw Error('GLB is missing textured geometry or usable animations');
    const idle = clips.find(name => /idle|wait|stand|breath|rest|fight[_ -]?a/i.test(name) &&
      !/attack|damage|faint|death|down|bind|t[-_ ]?pose/i.test(name));
    if (!idle) throw Error('No verified idle animation; existing Pokédex models were preserved');
    model.animations = clips.map(name => ({name}));
    model.idleAnimation = idle;
    model.idleBreaks = [];
    return model;
  }

  window.POKEDEX3D_GFPAK_ZIP = Object.freeze({read});
})();
