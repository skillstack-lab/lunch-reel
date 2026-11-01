#!/usr/bin/env python3
"""usage: python3 tools/make_fixture.py GAMEPK [--feed-only] [--out DIR]
   -> DIR/GAMEPK/{content.json,feed_trim.json,winProbability.json}  (default DIR: local-fixtures/, gitignored)

Pulls REAL MLB Advanced Media API responses for your own local, offline testing. That data is MLBAM's
(non-commercial, individual use); do not commit it to a public repo. The bundled fixtures/ are synthetic
(tools/make_synthetic.py). Use: python3 reel2.py GAMEPK --fixtures local-fixtures --plan-only"""
import json, os, sys, urllib.request as u
pk = sys.argv[1]
FEED_ONLY = "--feed-only" in sys.argv  # refresh feed_trim.json only (keeps content/winProbability stable for tests)
J = lambda url: json.load(u.urlopen(u.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30))
OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "local-fixtures"
d = f"{OUT}/{pk}"; os.makedirs(d, exist_ok=True)
if not FEED_ONLY: json.dump(J(f"https://statsapi.mlb.com/api/v1/game/{pk}/content"), open(f"{d}/content.json", "w"))
f = J(f"https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live")
plays = [{"about": {k: p["about"].get(k) for k in ("atBatIndex", "halfInning", "inning", "startTime")},
          "result": {"description": p["result"].get("description", ""), "awayScore": p["result"].get("awayScore"),
                     "homeScore": p["result"].get("homeScore")},
          "matchup": {"batter": p["matchup"]["batter"], "pitcher": p["matchup"]["pitcher"]},
          "reviewDetails": p.get("reviewDetails"),
          "playEvents": [{k: e.get(k) for k in ("playId", "startTime", "reviewDetails", "index") if e.get(k) is not None}
                         for e in p["playEvents"]]} for p in f["liveData"]["plays"]["allPlays"]]
json.dump({"gamePk": int(pk),
           "gameData": {"teams": {s: {"abbreviation": f["gameData"]["teams"][s]["abbreviation"]} for s in ("away", "home")},
                        "datetime": {"officialDate": f["gameData"]["datetime"].get("officialDate")}},
           "liveData": {"plays": {"allPlays": plays}}}, open(f"{d}/feed_trim.json", "w"))
print("wrote", d)
if FEED_ONLY: sys.exit(0)
wp = J(f"https://statsapi.mlb.com/api/v1/game/{pk}/winProbability")
json.dump([{"about": {"atBatIndex": p["about"]["atBatIndex"]},
            "homeTeamWinProbability": p.get("homeTeamWinProbability"),
            "homeTeamWinProbabilityAdded": p.get("homeTeamWinProbabilityAdded"),
            "result": {"description": p.get("result", {}).get("description", "")[:120]}} for p in wp],
          open(f"{d}/winProbability.json", "w"))
print("wrote", f"{d}/winProbability.json")
