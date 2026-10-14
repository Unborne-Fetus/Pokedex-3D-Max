/* Sequential, fault-isolated GFPAK Pokémon ZIP batch imports.
 * The caller owns local storage and optional GitHub publishing. A malformed
 * archive must not interrupt later Pokémon in the selected group.
 */
(() => {
  "use strict";

  async function run(files, { read, accept, progress = () => {} }) {
    const selected = Array.from(files || []);
    const seen = new Set();
    const results = [];
    for (const [index, file] of selected.entries()) {
      const state = phase => progress({
        phase, index: index + 1, total: selected.length,
        name: String(file?.name || "Unnamed file"),
        imported: results.filter(item => item.status === "imported").length,
        rejected: results.filter(item => item.status === "rejected").length,
        skipped: results.filter(item => item.status === "skipped").length
      });
      state("reading");
      try {
        if (!/\.zip$/i.test(String(file?.name || "")))
          throw Error("Select a .zip archive exported by GFPAK Open");
        const model = await read(file, selected.length === 1);
        const dex = Number(model?.dex);
        if (!Number.isInteger(dex) || dex < 1 || dex > 1025)
          throw Error("ZIP has no valid National Pokédex identity");
        if (seen.has(dex))
          throw Error("Duplicate Pokémon #" + String(dex).padStart(4, "0") +
            " in this batch; the earlier ZIP was kept");
        const outcome = await accept(model, file);
        if (outcome?.skipped) {
          results.push({name: file.name, dex, status: "skipped",
            detail: outcome.detail || "Skipped by user"});
        } else {
          seen.add(dex);
          results.push({name: file.name, dex, status: "imported",
            detail: outcome?.detail || "Imported"});
        }
      } catch (error) {
        results.push({name: String(file?.name || "Unnamed file"),
          status: "rejected", detail: String(error?.message || error)});
      }
      state("finished");
    }
    return {
      results,
      imported: results.filter(item => item.status === "imported").length,
      rejected: results.filter(item => item.status === "rejected").length,
      skipped: results.filter(item => item.status === "skipped").length
    };
  }

  window.POKEDEX3D_GFPAK_BATCH = Object.freeze({run});
})();
