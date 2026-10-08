(function(){
"use strict";
const $=s=>document.querySelector(s);
const panel=$("#battlePanel");
if(!panel)return;

const els={
  builder:$("#battleBuilder"),arena:$("#battleArena"),status:$("#battleStatus"),
  teamInputs:[...document.querySelectorAll(".battle-team-input")],difficulty:$("#battleDifficulty"),
  start:$("#battleStart"),reset:$("#battleReset"),
  playerViewer:$("#battlePlayerModel"),foeViewer:$("#battleFoeModel"),
  playerName:$("#battlePlayerName"),foeName:$("#battleFoeName"),
  playerHp:$("#battlePlayerHp"),foeHp:$("#battleFoeHp"),
  playerHpText:$("#battlePlayerHpText"),foeHpText:$("#battleFoeHpText"),
  moves:$("#battleMoves"),switches:$("#battleSwitches"),log:$("#battleLog"),turn:$("#battleTurn")
};

let room=null;
let snap=null;
let engineReady=null;
let renderedLogCount=0;
const MODEL_CDN="https://cdn.jsdelivr.net/gh/Pokemon-3D-api/assets@main/models/opt/regular/";

function pretty(v){return String(v||"").replace(/_/g," ").replace(/\b\w/g,c=>c.toUpperCase());}
function modelForSpecies(species){
  const list=Array.isArray(window.POKEDEX3D_MODELS)?window.POKEDEX3D_MODELS:[];
  const dex=window.BRISK_BATTLE_DATA?.species?.[species]?.nationalDex||species;
  const exact=list.find(m=>Number(m.dex)===Number(dex)&&String(m.form||"").toLowerCase()==="regular")
    ||list.find(m=>Number(m.dex)===Number(dex)&&!String(m.form||"").toLowerCase().includes("shiny"));
  return exact?.url||(window.POKEDEX3D_MODEL_POLICY?.switchOnly ? "" : MODEL_CDN+Number(dex)+".glb");
}
function engine(){
  if(!window.BriskBattleEngine)throw new Error("Brisk battle engine did not load.");
  return window.BriskBattleEngine;
}
async function ensureEngine(){
  if(engineReady)return engineReady;
  engineReady=engine().loadData("web/brisk-engine/brisk-dex-data.json").catch(err=>{engineReady=null;throw err;});
  await engineReady;
  return true;
}
function active(side){
  const p=snap.players[side];
  return p&&p.team[p.active];
}
function hpPct(mon){return Math.max(0,Math.min(100,(Number(mon.hp)||0)/Math.max(1,Number(mon.maxHP)||1)*100));}
function setHp(bar,text,mon){
  const pct=hpPct(mon);bar.style.width=pct+"%";bar.dataset.low=pct<=25?"1":"0";bar.dataset.mid=pct>25&&pct<=50?"1":"0";
  text.textContent=Math.max(0,mon.hp)+" / "+mon.maxHP+(mon.status?" · "+pretty(mon.status):"");
}
function setViewer(viewer,mon,back){
  const url=modelForSpecies(mon.species);
  if(!url){viewer.removeAttribute("src");viewer.setAttribute("alt","No restored Switch model for "+mon.name);return;}
  if(viewer.getAttribute("src")!==url)viewer.setAttribute("src",url);
  viewer.setAttribute("alt","3D model of "+mon.name);
  viewer.cameraOrbit=back?"180deg 75deg auto":"0deg 75deg auto";
}
for(const viewer of [els.playerViewer,els.foeViewer]){
  viewer.addEventListener("load",()=>{
    const idle=(viewer.availableAnimations||[]).find(name=>/idle|wait|stand|breath|fight[_ -]?a/i.test(name));
    if(idle){viewer.animationName=idle;viewer.play();}
  });
}
function appendLogs(){
  const logs=snap?.log||[];
  if(renderedLogCount>logs.length){els.log.replaceChildren();renderedLogCount=0;}
  for(let i=renderedLogCount;i<logs.length;i++){
    const d=document.createElement("div");d.textContent=logs[i];els.log.appendChild(d);
  }
  renderedLogCount=logs.length;
  els.log.scrollTop=els.log.scrollHeight;
}
function animateLatest(){
  const ev=(snap?.animations||[]).at(-1);if(!ev)return;
  const viewer=ev.attacker===0?els.playerViewer:els.foeViewer;
  viewer.classList.remove("battle-lunge");void viewer.offsetWidth;viewer.classList.add("battle-lunge");
  setTimeout(()=>viewer.classList.remove("battle-lunge"),420);
}
function render(){
  if(!snap)return;
  const p=active(0),f=active(1);
  if(!p||!f)return;
  els.playerName.textContent=p.name+" Lv."+p.level+(p.ability?" · "+p.ability:"");
  els.foeName.textContent=f.name+" Lv."+f.level+(f.ability?" · "+f.ability:"");
  setHp(els.playerHp,els.playerHpText,p);setHp(els.foeHp,els.foeHpText,f);
  setViewer(els.playerViewer,p,true);setViewer(els.foeViewer,f,false);
  els.turn.textContent="Turn "+snap.turn+(snap.weather?" · "+pretty(snap.weather):"")+(snap.terrain?" · "+pretty(snap.terrain):"");

  els.moves.replaceChildren();
  p.moves.forEach((move,index)=>{
    const b=document.createElement("button");b.type="button";b.className="battle-move";
    b.disabled=snap.phase!=="battle"||move.pp<=0;
    b.innerHTML="<strong>"+move.name+"</strong><span>"+pretty(move.type)+" · "+move.category+" · "+move.power+" BP · PP "+move.pp+"/"+move.maxPP+"</span>";
    b.addEventListener("click",()=>playMove(index));
    els.moves.appendChild(b);
  });

  els.switches.replaceChildren();
  snap.players[0].team.forEach((mon,index)=>{
    const b=document.createElement("button");b.type="button";b.className="battle-switch";
    b.disabled=snap.phase!=="battle"||index===snap.players[0].active||mon.hp<=0;
    b.innerHTML="<strong>"+mon.name+"</strong><span>"+(mon.hp<=0?"Fainted":mon.hp+"/"+mon.maxHP+" HP"+(mon.status?" · "+pretty(mon.status):""))+"</span>";
    b.addEventListener("click",()=>playSwitch(index));
    els.switches.appendChild(b);
  });

  appendLogs();
  if(snap.phase==="finished"){
    const won=snap.winner===0;
    els.status.textContent=won?"Victory!":"Defeat";
  }else{
    els.status.textContent="Brisk engine "+engine().version+" · Battle in progress";
  }
}
async function playMove(index){
  if(!room||snap.phase!=="battle")return;
  disable(true);
  const oldSeq=(snap.animations||[]).at(-1)?.seq||0;
  snap=engine().submitMove(room,index,null);
  render();
  if(((snap.animations||[]).at(-1)?.seq||0)!==oldSeq)animateLatest();
  disable(false);
}
async function playSwitch(slot){
  if(!room||snap.phase!=="battle")return;
  disable(true);
  snap=engine().submitSwitch(room,slot);
  render();
  disable(false);
}
function disable(value){
  els.moves.querySelectorAll("button").forEach(x=>x.disabled=value||x.disabled);
  els.switches.querySelectorAll("button").forEach(x=>x.disabled=value||x.disabled);
  els.start.disabled=value;
}
async function startBattle(){
  const team=els.teamInputs.map(x=>x.value.trim()).filter(Boolean);
  if(team.length!==3){els.status.textContent="Choose exactly 3 Pokémon.";return;}
  els.start.disabled=true;els.status.textContent="Loading Brisk battle engine…";
  try{
    await ensureEngine();
    room=engine().createBotBattle(team,els.difficulty.value);
    snap=engine().snapshot(room);
    renderedLogCount=0;els.log.replaceChildren();
    els.builder.classList.add("hidden");els.arena.classList.remove("hidden");els.reset.classList.remove("hidden");
    render();
  }catch(err){
    console.error(err);els.status.textContent="Could not start battle: "+err.message;
  }finally{els.start.disabled=false;}
}
function reset(){
  room=null;snap=null;renderedLogCount=0;els.log.replaceChildren();
  els.builder.classList.remove("hidden");els.arena.classList.add("hidden");els.reset.classList.add("hidden");els.status.textContent="Ready";
}
els.start?.addEventListener("click",startBattle);
els.reset?.addEventListener("click",reset);
})();
