(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const panel = $("#battlePanel");
  if (!panel) return;

  const POKE_API = "https://pokeapi.co/api/v2";
  const MODEL_CDN = "https://cdn.jsdelivr.net/gh/Pokemon-3D-api/assets@main/models/opt/regular/";
  const statCache = new Map();
  const moveCache = new Map();

  const TYPE_CHART = {
    normal:{rock:.5,ghost:0,steel:.5},
    fire:{fire:.5,water:.5,grass:2,ice:2,bug:2,rock:.5,dragon:.5,steel:2},
    water:{fire:2,water:.5,grass:.5,ground:2,rock:2,dragon:.5},
    electric:{water:2,electric:.5,grass:.5,ground:0,flying:2,dragon:.5},
    grass:{fire:.5,water:2,grass:.5,poison:.5,ground:2,flying:.5,bug:.5,rock:2,dragon:.5,steel:.5},
    ice:{fire:.5,water:.5,grass:2,ice:.5,ground:2,flying:2,dragon:2,steel:.5},
    fighting:{normal:2,ice:2,poison:.5,flying:.5,psychic:.5,bug:.5,rock:2,ghost:0,dark:2,steel:2,fairy:.5},
    poison:{grass:2,poison:.5,ground:.5,rock:.5,ghost:.5,steel:0,fairy:2},
    ground:{fire:2,electric:2,grass:.5,poison:2,flying:0,bug:.5,rock:2,steel:2},
    flying:{electric:.5,grass:2,fighting:2,bug:2,rock:.5,steel:.5},
    psychic:{fighting:2,poison:2,psychic:.5,dark:0,steel:.5},
    bug:{fire:.5,grass:2,fighting:.5,poison:.5,flying:.5,psychic:2,ghost:.5,dark:2,steel:.5,fairy:.5},
    rock:{fire:2,ice:2,fighting:.5,ground:.5,flying:2,bug:2,steel:.5},
    ghost:{normal:0,psychic:2,ghost:2,dark:.5},
    dragon:{dragon:2,steel:.5,fairy:0},
    dark:{fighting:.5,psychic:2,ghost:2,dark:.5,fairy:.5},
    steel:{fire:.5,water:.5,electric:.5,ice:2,rock:2,steel:.5,fairy:2},
    fairy:{fire:.5,fighting:2,poison:.5,dragon:2,dark:2,steel:.5}
  };

  const els = {
    builder: $("#battleBuilder"),
    arena: $("#battleArena"),
    status: $("#battleStatus"),
    teamInputs: [...document.querySelectorAll(".battle-team-input")],
    difficulty: $("#battleDifficulty"),
    start: $("#battleStart"),
    reset: $("#battleReset"),
    playerViewer: $("#battlePlayerModel"),
    foeViewer: $("#battleFoeModel"),
    playerName: $("#battlePlayerName"),
    foeName: $("#battleFoeName"),
    playerHp: $("#battlePlayerHp"),
    foeHp: $("#battleFoeHp"),
    playerHpText: $("#battlePlayerHpText"),
    foeHpText: $("#battleFoeHpText"),
    moves: $("#battleMoves"),
    switches: $("#battleSwitches"),
    log: $("#battleLog"),
    turn: $("#battleTurn")
  };

  let state = null;

  function normalizeName(value) {
    return String(value || "").trim().toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-");
  }

  function modelForDex(dex) {
    const models = Array.isArray(window.POKEDEX3D_MODELS) ? window.POKEDEX3D_MODELS : [];
    const regular = models.find(m => Number(m.dex) === Number(dex) && String(m.form || "").toLowerCase() === "regular")
      || models.find(m => Number(m.dex) === Number(dex) && !String(m.form || "").toLowerCase().includes("shiny"));
    return regular?.url || (MODEL_CDN + Number(dex) + ".glb");
  }

  async function json(url) {
    const response = await fetch(url, {cache:"force-cache"});
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }

  function pretty(value) {
    return String(value || "")
      .replace(/-/g, " ")
      .replace(/\b\w/g, c => c.toUpperCase());
  }

  async function getMove(urlOrName) {
    const key = String(urlOrName);
    if (moveCache.has(key)) return moveCache.get(key);
    const url = key.startsWith("http") ? key : POKE_API + "/move/" + normalizeName(key);
    const raw = await json(url);
    const move = {
      id: raw.id,
      name: pretty(raw.name),
      key: raw.name,
      type: raw.type?.name || "normal",
      power: Number(raw.power) || 0,
      accuracy: raw.accuracy == null ? 100 : Number(raw.accuracy),
      pp: Number(raw.pp) || 5,
      damageClass: raw.damage_class?.name || "status",
      priority: Number(raw.priority) || 0
    };
    moveCache.set(key, move);
    moveCache.set(raw.name, move);
    return move;
  }

  async function pickMoves(pokemon) {
    const levelMoves = [];
    const otherMoves = [];
    for (const entry of pokemon.moves || []) {
      let bestLevel = Infinity;
      for (const detail of entry.version_group_details || []) {
        if (detail.move_learn_method?.name === "level-up") {
          bestLevel = Math.min(bestLevel, Number(detail.level_learned_at) || 1);
        }
      }
      const bucket = bestLevel <= 50 ? levelMoves : otherMoves;
      bucket.push({url:entry.move.url, level:bestLevel});
    }

    async function loadCandidates(source, limit) {
      const sample = source.slice(-Math.min(source.length, limit));
      const loaded = await Promise.all(sample.map(x => getMove(x.url).catch(() => null)));
      return loaded.filter(m => m && m.power > 0 && (m.damageClass === "physical" || m.damageClass === "special"));
    }

    let damaging = await loadCandidates(levelMoves, 28);
    if (damaging.length < 4) damaging = damaging.concat(await loadCandidates(otherMoves, 18));

    const unique = [...new Map(damaging.map(m => [m.key, m])).values()];
    unique.sort((a,b) => (b.power * b.accuracy) - (a.power * a.accuracy));
    const selected = unique.slice(0, 4);

    if (!selected.length) {
      selected.push(await getMove("tackle"));
    }
    while (selected.length < 4) selected.push({...selected[selected.length % selected.length]});
    return selected.map(m => ({...m, currentPp:m.pp}));
  }

  async function getPokemon(query) {
    const key = normalizeName(query);
    if (!key) throw new Error("Choose a Pokémon");
    if (statCache.has(key)) return structuredClone(statCache.get(key));

    const raw = await json(POKE_API + "/pokemon/" + encodeURIComponent(key));
    const stats = Object.fromEntries((raw.stats || []).map(s => [s.stat.name, Number(s.base_stat) || 1]));
    const level = 50;
    const calcHp = base => Math.floor(((2 * base + 31) * level) / 100) + level + 10;
    const calcOther = base => Math.floor((Math.floor(((2 * base + 31) * level) / 100) + 5));
    const mon = {
      id: raw.id,
      dex: raw.id,
      name: pretty(raw.name),
      level,
      types: (raw.types || []).sort((a,b)=>a.slot-b.slot).map(t=>t.type.name),
      maxHp: calcHp(stats.hp || 1),
      hp: calcHp(stats.hp || 1),
      attack: calcOther(stats.attack || 1),
      defense: calcOther(stats.defense || 1),
      spAttack: calcOther(stats["special-attack"] || 1),
      spDefense: calcOther(stats["special-defense"] || 1),
      speed: calcOther(stats.speed || 1),
      fainted:false,
      modelUrl:modelForDex(raw.id),
      moves: await pickMoves(raw)
    };
    statCache.set(key, mon);
    statCache.set(String(raw.id), mon);
    return structuredClone(mon);
  }

  function effectiveness(moveType, defenderTypes) {
    const row = TYPE_CHART[moveType] || {};
    return defenderTypes.reduce((mult, type) => mult * (row[type] ?? 1), 1);
  }

  function estimatedDamage(attacker, defender, move) {
    if (!move.power) return 0;
    const offense = move.damageClass === "special" ? attacker.spAttack : attacker.attack;
    const defense = Math.max(1, move.damageClass === "special" ? defender.spDefense : defender.defense);
    const stab = attacker.types.includes(move.type) ? 1.5 : 1;
    const eff = effectiveness(move.type, defender.types);
    return (((2 * attacker.level / 5 + 2) * move.power * offense / defense) / 50 + 2) * stab * eff;
  }

  function useMove(attacker, defender, move, side) {
    if (move.currentPp <= 0) {
      log(attacker.name + " has no PP left for " + move.name + "!");
      return;
    }
    move.currentPp--;
    log(attacker.name + " used " + move.name + "!");

    if (Math.random() * 100 > move.accuracy) {
      log("It missed.");
      animateAttack(side, true);
      return;
    }

    const crit = Math.random() < 1/24 ? 1.5 : 1;
    const random = 0.85 + Math.random() * 0.15;
    const eff = effectiveness(move.type, defender.types);
    const damage = Math.max(eff === 0 ? 0 : 1, Math.floor(estimatedDamage(attacker, defender, move) * crit * random));
    defender.hp = Math.max(0, defender.hp - damage);

    animateAttack(side, false);
    if (crit > 1) log("A critical hit!");
    if (eff === 0) log("It doesn't affect " + defender.name + ".");
    else if (eff > 1) log("It's super effective!");
    else if (eff < 1) log("It's not very effective.");
    log(defender.name + " lost " + damage + " HP.");

    if (defender.hp <= 0) {
      defender.fainted = true;
      log(defender.name + " fainted!");
    }
  }

  function animateAttack(side, miss) {
    const node = side === "player" ? els.playerViewer : els.foeViewer;
    node.classList.remove("battle-lunge", "battle-miss");
    void node.offsetWidth;
    node.classList.add(miss ? "battle-miss" : "battle-lunge");
    setTimeout(() => node.classList.remove("battle-lunge", "battle-miss"), 420);
  }

  function log(message) {
    if (!els.log) return;
    const div = document.createElement("div");
    div.textContent = message;
    els.log.appendChild(div);
    els.log.scrollTop = els.log.scrollHeight;
  }

  function active(side) {
    return state[side].team[state[side].active];
  }

  function living(team) {
    return team.map((m,i)=>({m,i})).filter(x=>!x.m.fainted && x.m.hp > 0);
  }

  function chooseBotMove(bot, target) {
    const usable = bot.moves.filter(m => m.currentPp > 0);
    const choices = usable.length ? usable : bot.moves;
    if (state.difficulty === "easy") return choices[Math.floor(Math.random()*choices.length)];
    const ranked = [...choices].sort((a,b)=>estimatedDamage(bot,target,b)-estimatedDamage(bot,target,a));
    if (state.difficulty === "hard") return ranked[0];
    return Math.random() < .7 ? ranked[0] : choices[Math.floor(Math.random()*choices.length)];
  }

  function checkBattleEnd() {
    const playerAlive = living(state.player.team);
    const foeAlive = living(state.foe.team);
    if (!playerAlive.length || !foeAlive.length) {
      state.over = true;
      const won = !!playerAlive.length;
      els.status.textContent = won ? "Victory!" : "Defeat";
      log(won ? "You won the battle!" : "The opposing trainer won.");
      render();
      return true;
    }
    return false;
  }

  function forceNext(side) {
    const choices = living(state[side].team);
    if (!choices.length) return false;
    state[side].active = choices[0].i;
    log((side === "player" ? "Go! " : "The foe sent out ") + active(side).name + "!");
    return true;
  }

  async function takeTurn(playerMoveIndex) {
    if (!state || state.busy || state.over) return;
    state.busy = true;
    disableActions(true);

    let p = active("player");
    let f = active("foe");
    const pMove = p.moves[playerMoveIndex];
    const fMove = chooseBotMove(f,p);
    const actions = [
      {side:"player", mon:p, target:f, move:pMove},
      {side:"foe", mon:f, target:p, move:fMove}
    ].sort((a,b) => {
      if (a.move.priority !== b.move.priority) return b.move.priority - a.move.priority;
      if (a.mon.speed !== b.mon.speed) return b.mon.speed - a.mon.speed;
      return Math.random() < .5 ? -1 : 1;
    });

    for (const action of actions) {
      if (action.mon.fainted || action.target.fainted) continue;
      useMove(action.mon, action.target, action.move, action.side);
      renderHud();
      await new Promise(r=>setTimeout(r, 520));
    }

    state.turn++;
    if (!checkBattleEnd()) {
      if (active("player").fainted) forceNext("player");
      if (active("foe").fainted) forceNext("foe");
      render();
    }
    state.busy = false;
    disableActions(false);
  }

  async function switchPlayer(index) {
    if (!state || state.busy || state.over || index === state.player.active) return;
    const next = state.player.team[index];
    if (!next || next.fainted) return;
    state.busy = true;
    disableActions(true);

    const old = active("player");
    log("Come back, " + old.name + "!");
    state.player.active = index;
    log("Go! " + active("player").name + "!");
    render();

    const foe = active("foe");
    const move = chooseBotMove(foe, active("player"));
    await new Promise(r=>setTimeout(r, 350));
    useMove(foe, active("player"), move, "foe");
    renderHud();

    if (!checkBattleEnd() && active("player").fainted) forceNext("player");
    state.turn++;
    render();
    state.busy = false;
    disableActions(false);
  }

  function disableActions(disabled) {
    els.moves.querySelectorAll("button").forEach(b=>b.disabled=disabled);
    els.switches.querySelectorAll("button").forEach(b=>b.disabled=disabled || b.dataset.locked === "1");
  }

  function hpPercent(mon) {
    return Math.max(0, Math.min(100, mon.hp / mon.maxHp * 100));
  }

  function setHp(bar, text, mon) {
    const pct = hpPercent(mon);
    bar.style.width = pct + "%";
    bar.dataset.low = pct <= 25 ? "1" : "0";
    bar.dataset.mid = pct > 25 && pct <= 50 ? "1" : "0";
    text.textContent = mon.hp + " / " + mon.maxHp;
  }

  function setViewer(viewer, mon, back=false) {
    if (!viewer || !mon) return;
    if (viewer.getAttribute("src") !== mon.modelUrl) viewer.setAttribute("src", mon.modelUrl);
    viewer.setAttribute("alt", "3D model of " + mon.name);
    viewer.cameraOrbit = back ? "180deg 75deg auto" : "0deg 75deg auto";
    viewer.setAttribute("camera-target", "auto auto auto");
  }

  function renderHud() {
    if (!state) return;
    const p = active("player");
    const f = active("foe");
    els.playerName.textContent = p.name + " Lv.50";
    els.foeName.textContent = f.name + " Lv.50";
    setHp(els.playerHp, els.playerHpText, p);
    setHp(els.foeHp, els.foeHpText, f);
    setViewer(els.playerViewer, p, true);
    setViewer(els.foeViewer, f, false);
    els.turn.textContent = "Turn " + state.turn;
  }

  function render() {
    if (!state) return;
    renderHud();
    const p = active("player");

    els.moves.replaceChildren();
    p.moves.forEach((move, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "battle-move";
      button.disabled = state.busy || state.over || move.currentPp <= 0;
      const eff = effectiveness(move.type, active("foe").types);
      button.innerHTML = "<strong>" + move.name + "</strong><span>" + pretty(move.type) +
        " · " + move.power + " BP · PP " + move.currentPp + "/" + move.pp +
        (eff > 1 ? " · Super" : eff === 0 ? " · No effect" : eff < 1 ? " · Resist" : "") + "</span>";
      button.addEventListener("click",()=>takeTurn(index));
      els.moves.appendChild(button);
    });

    els.switches.replaceChildren();
    state.player.team.forEach((mon,index)=>{
      const button = document.createElement("button");
      button.type = "button";
      button.className = "battle-switch";
      const locked = index === state.player.active || mon.fainted;
      button.dataset.locked = locked ? "1" : "0";
      button.disabled = locked || state.busy || state.over;
      button.innerHTML = "<strong>" + mon.name + "</strong><span>" +
        (mon.fainted ? "Fainted" : mon.hp + "/" + mon.maxHp + " HP") + "</span>";
      button.addEventListener("click",()=>switchPlayer(index));
      els.switches.appendChild(button);
    });
  }

  function parseTeamInputs() {
    return els.teamInputs.map(input => input.value.trim()).filter(Boolean);
  }

  function randomDex(exclude) {
    let dex;
    do dex = 1 + Math.floor(Math.random()*1025);
    while (exclude.has(dex));
    exclude.add(dex);
    return dex;
  }

  async function startBattle() {
    const choices = parseTeamInputs();
    if (choices.length !== 3) {
      els.status.textContent = "Choose exactly 3 Pokémon.";
      return;
    }
    els.start.disabled = true;
    els.status.textContent = "Building teams…";
    els.log.replaceChildren();

    try {
      const playerTeam = await Promise.all(choices.map(getPokemon));
      const used = new Set(playerTeam.map(m=>m.dex));
      const foeDex = [randomDex(used), randomDex(used), randomDex(used)];
      const foeTeam = await Promise.all(foeDex.map(d=>getPokemon(String(d))));
      state = {
        turn:1,
        difficulty:els.difficulty.value,
        over:false,
        busy:false,
        player:{team:playerTeam,active:0},
        foe:{team:foeTeam,active:0}
      };
      els.builder.classList.add("hidden");
      els.arena.classList.remove("hidden");
      els.reset.classList.remove("hidden");
      els.status.textContent = "Battle in progress";
      log("A battle started!");
      log("Go! " + active("player").name + "!");
      log("The foe sent out " + active("foe").name + "!");
      render();
    } catch (error) {
      console.error(error);
      els.status.textContent = "Could not build battle: " + error.message;
    } finally {
      els.start.disabled = false;
    }
  }

  function resetBattle() {
    state = null;
    els.builder.classList.remove("hidden");
    els.arena.classList.add("hidden");
    els.reset.classList.add("hidden");
    els.status.textContent = "Ready";
    els.log.replaceChildren();
  }

  function hydrateTeamDefaults() {
    const defaults = ["charizard","pikachu","lucario"];
    els.teamInputs.forEach((input,i)=>{
      if (!input.value) input.value = defaults[i];
    });
  }

  els.start?.addEventListener("click", startBattle);
  els.reset?.addEventListener("click", resetBattle);
  hydrateTeamDefaults();
})();
