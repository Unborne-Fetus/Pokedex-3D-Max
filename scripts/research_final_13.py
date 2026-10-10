#!/usr/bin/env python3
"""Find existing, attributable external 3D previews for the last 13 species.

Research only: never copies, rehosts, or republishes another artist's models.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".cache" / "final-13-research"
SPECIES = {
    854: "Sinistea", 864: "Cursola", 931: "Squawkabilly", 938: "Tadbulb",
    939: "Bellibolt", 961: "Wugtrio", 963: "Finizen", 972: "Houndstone",
    986: "Brute Bonnet", 988: "Slither Wing", 991: "Iron Bundle",
    992: "Iron Hands", 993: "Iron Jugulis",
}

def get(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Pokedex3DMax/1.0; community asset research)",
        "Accept": "application/json, text/html, */*",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP {response.status}")
        return response.read()

def sketchfab(species: str) -> dict:
    query = urllib.parse.urlencode({"type":"models", "q":species, "count":40})
    urls = [
        "https://api.sketchfab.com/v3/search?" + query,
        "https://api.sketchfab.com/v3/models?" + urllib.parse.urlencode({"search":species,"count":40}),
    ]
    errors = []
    items = []
    used_url = None
    for url in urls:
        try:
            data = json.loads(get(url))
            items = data.get("results") or []
            used_url = url
            break
        except Exception as err:
            errors.append(f"{type(err).__name__}: {err}")
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).casefold())
    wanted = norm(species)
    matching = []
    for item in items:
        name = str(item.get("name") or "")
        comparable = norm(name)
        if wanted not in comparable:
            continue
        uid = item.get("uid")
        if not isinstance(uid, str) or not re.fullmatch(r"[0-9a-f]{32}", uid):
            continue
        license = item.get("license") or {}
        if isinstance(license, dict):
            lic = {"label": license.get("label"), "slug":license.get("slug"), "url":license.get("url")}
        else:
            lic = {"label":str(license)}
        user = item.get("user") or {}
        if not isinstance(user, dict): user={}
        matching.append({
            "uid":uid, "name":name, "page":"https://sketchfab.com/models/"+uid,
            "embed":"https://sketchfab.com/models/"+uid+"/embed",
            "animated":item.get("isAnimated", item.get("animated")),
            "downloadable":item.get("isDownloadable",item.get("downloadable")),
            "license":lic,
            "artist":user.get("displayName") or user.get("username"),
            "publishedAt":item.get("publishedAt"),
            "likes":item.get("likeCount",0),
            "views":item.get("viewCount",0),
            "tags":[t.get("slug") if isinstance(t,dict) else str(t) for t in (item.get("tags") or [])][:12],
        })
    matching.sort(key=lambda r:(
        1 if r["animated"] else 0,
        1 if r["downloadable"] else 0,
        (int(r.get("likes") or 0)),
    ), reverse=True)
    return {"searchedAt":used_url,"errors":errors if used_url is None else [],"matches":matching[:12],"totalMatches":len(matching)}

def cobblemon_tools(species: str) -> dict:
    path=urllib.parse.quote(species.lower().replace(" ","-"))
    url="https://cobblemon.tools/pokedex/pokemon/"+path
    try:
        raw=get(url).decode("utf-8","replace")
        patterns = [
            r'https?[^"\\<> ]+\\.(?:glb|gltf)(?:\\?[^"\\<> ]*)?',
            r'[^"\\<> ]{0,160}\\.(?:glb|gltf)(?:\\?[^"\\<> ]*)?',
            r'[^"\\<> ]{0,160}\\.geo\\.json[^"\\<> ]*',
            r'["\\'](?:modelUrl|gltfUrl|modelPath|model_url|model_src)["\\']\\s*:\\s*["\\'][^"\\']+',
        ]
        hits=[]
        for p in patterns:
            hits.extend(re.findall(p,raw,flags=re.I)[:12])
        return {"url":url,"status":"retrieved","htmlBytes":len(raw),"has3DSection":"in 3D" in raw,
                "assetClues":list(dict.fromkeys(hits))[:20]}
    except Exception as ex:
        return {"url":url,"error":f"{type(ex).__name__}: {ex}"}

def main():
    result={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        jobs={pool.submit(sketchfab,name):(number,name) for number,name in SPECIES.items()}
        for fut in concurrent.futures.as_completed(jobs):
            dex,name=jobs[fut]
            try:
                row=fut.result()
            except Exception as ex:
                row={"errors":[f"{type(ex).__name__}: {ex}"],"matches":[]}
            result[dex]={"dex":dex,"species":name,**row}
            top=row.get("matches") or []
            print(f"#{dex:04d} {name}: {len(top)} match(es) "
                  f"animated={sum(x.get('animated') is True for x in top)}",flush=True)
            for cand in top[:6]:
                print(f"    {cand['name']!r}  animated={cand['animated']} "
                      f"downloadable={cand['downloadable']} license={cand['license'].get('label')} "
                      f"url={cand['page']}",flush=True)
            if row.get("errors"):
                print("    ERRORS: "+str(row["errors"]),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        jobs={pool.submit(cobblemon_tools,name):(number,name) for number,name in SPECIES.items()}
        for fut in concurrent.futures.as_completed(jobs):
            dex,name=jobs[fut]
            result[dex]["cobblemonTools"]=fut.result()
            print(f"Cobblemon #{dex:04d}: "
                  f"{result[dex]['cobblemonTools']}",flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/"research.json"
    target.write_text(json.dumps([result[k] for k in sorted(result)],indent=2,ensure_ascii=False)+"\\n",
                      encoding="utf-8")
    print("Saved:",target)

if __name__=="__main__":
    main()
