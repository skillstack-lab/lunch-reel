#!/usr/bin/env python3
"""Generate the bundled SYNTHETIC fixtures (no MLB Advanced Media data, no real players, no real media URLs).

usage: python3 tools/make_synthetic.py [--out fixtures]

Every game, headline, player, playId, timestamp and win-probability number here is made up and deterministic.
The JSON *shapes* mirror what reel2.py reads from statsapi (content, trimmed feed, winProbability, schedule) so
the offline tests exercise the same code paths as live data:
  talk / recap / condensed-game taxonomy, "Field View" alt angles, too-long items, multi-play packages,
  unmapped clips, duplicate anchors, late-published clips (chronology), ABS challenge clips with and without a guid,
  big win-probability swings that were never clipped (missed_hot), doubleheaders where gamePk != start order,
  postponed / cancelled / data-less games.
Team ids/abbreviations/names (fixtures/teams.json) are plain facts used only to look teams up.
Clip URLs point at example.invalid, so a render against fixtures fails fast instead of downloading anything.
"""
import json, os, random, sys, uuid
from datetime import datetime, timedelta, timezone

NS = uuid.UUID("6c756e63-6872-6565-6c2d-73796e746865")  # fixed namespace -> stable playIds
TEAMS = {"BAL": (110, "Baltimore Orioles"), "NYY": (147, "New York Yankees"), "HOU": (117, "Houston Astros"),
         "ATH": (133, "Athletics"), "LAD": (119, "Los Angeles Dodgers"), "SF": (137, "San Francisco Giants"),
         "CHC": (112, "Chicago Cubs"), "BOS": (111, "Boston Red Sox")}
ACTS = ["singles", "doubles", "grounds out", "flies out", "strikes out", "walks", "lines out", "pops out"]

# One spec per synthetic game. runs: atBatIndex -> runs scored (top half = away, bottom = home);
# wpa: atBatIndex -> home-perspective WPA in percent (sign forced by the scoring team on run-scoring at-bats).
# clips: at-bats MLB "clipped"; extra entries add noise the planner must drop or handle.
GAMES = {
    990003: dict(away="BAL", home="NYY", start="2099-04-01T17:05:00Z", seed=1,
                 runs={1: 2, 16: 1, 22: 2, 31: 1, 47: 1}, wpa={1: 14.0, 12: 12.0, 16: 9.5, 22: 21.1, 31: 8.0, 40: -16.0, 47: 6.0},
                 clips=[1, 4, 9, 16, 22, 27, 31, 38, 47, 52, 53], late=[47], abs_review=[12], abs_guid=[], hot_play={22: "two-run home run"}),
    990002: dict(away="BAL", home="NYY", start="2099-04-01T21:10:00Z", seed=2,
                 runs={7: 1, 19: 2, 31: 1, 44: 1}, wpa={7: 9.0, 19: 15.5, 28: 10.0, 31: 11.0, 44: 12.0, 50: 18.0},
                 clips=[3, 7, 13, 19, 25, 31, 36, 44, 49], late=[], abs_review=[28], abs_guid=[], hot_play={}),
    990004: dict(away="HOU", home="ATH", start="2099-04-02T01:40:00Z", seed=3,
                 runs={10: 1, 20: 3, 37: 1, 45: 2}, wpa={10: 7.0, 20: 19.0, 26: 13.0, 34: -9.0, 37: 8.5, 45: 17.5},
                 clips=[2, 10, 15, 20, 30, 37, 42, 45, 53], late=[], abs_review=[], abs_guid=[34], hot_play={}),
    990010: dict(away="CHC", home="BOS", start="2099-04-02T17:35:00Z", seed=4,
                 runs={1: 2, 14: 1, 26: 1, 35: 2, 49: 1}, wpa={1: 10.5, 14: 8.0, 18: 14.0, 26: 12.5, 35: 20.0, 43: -15.8, 49: 9.0},
                 clips=[1, 6, 14, 20, 26, 30, 35, 40, 49, 53], late=[49], abs_review=[18], abs_guid=[], hot_play={}),
}
SCHEDULES = {
    "2099-04-01": [  # gamePk deliberately NOT start order for the doubleheader (G1 = 990003, G2 = 990002)
        dict(pk=990003, away="BAL", home="NYY", gameDate="2099-04-01T17:05:00Z", gameNumber=1, dh="S"),
        dict(pk=990002, away="BAL", home="NYY", gameDate="2099-04-01T21:10:00Z", gameNumber=2, dh="S"),
        dict(pk=990004, away="HOU", home="ATH", gameDate="2099-04-02T01:40:00Z"),
        dict(pk=990005, away="LAD", home="SF", gameDate="2099-04-02T02:15:00Z"),                       # final, no data
        dict(pk=990006, away="CHC", home="BOS", gameDate="2099-04-01T23:10:00Z", state=("Preview", "Postponed")),
    ],
    "2099-04-02": [
        dict(pk=990010, away="CHC", home="BOS", gameDate="2099-04-02T17:35:00Z"),
        dict(pk=990011, away="BAL", home="NYY", gameDate="2099-04-02T23:05:00Z", state=("Final", "Cancelled")),
    ],
}


def iso(t): return t.strftime("%Y-%m-%dT%H:%M:%SZ")
def dur(s): return f"00:{s // 60:02d}:{s % 60:02d}"


def build(pk, g):
    rng = random.Random(g["seed"])
    t0 = datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
    review_abs = set(g["abs_review"]) | set(g["abs_guid"])
    plays, wp, pitch, score = [], [], {}, [0, 0]
    for ab in range(54):  # 9 innings x 6 PAs (3 per half), enough for every case
        inning, half = ab // 6 + 1, ("top" if ab % 6 < 3 else "bottom")
        n = max(2 if ab in review_abs else 1, rng.randint(1, 5))
        evs = []
        for j in range(n):
            e = {"playId": str(uuid.uuid5(NS, f"{pk}-{ab}-{j}")), "startTime": iso(t0 + timedelta(minutes=3 * ab, seconds=25 * j)), "index": j}
            if ab in review_abs and j == 0: e["reviewDetails"] = {"isOverturned": True, "reviewType": "MJ", "challengeTeamId": 0}
            evs.append(e)
        pitch[ab] = evs
        r = g["runs"].get(ab, 0)
        score[0 if half == "top" else 1] += r
        batter = f"Synthetic Batter {ab % 13 + 1}"
        desc = f"{batter} {'homers' if r else rng.choice(ACTS)}." + (f" {r} run(s) score." if r else "")
        plays.append({"about": {"atBatIndex": ab, "halfInning": half, "inning": inning, "startTime": evs[0]["startTime"]},
                      "result": {"description": desc, "awayScore": score[0], "homeScore": score[1]}, "playEvents": evs})
        w = g["wpa"].get(ab, round(rng.uniform(-3.5, 3.5), 1))
        if r: w = abs(w) if half == "bottom" else -abs(w)  # runs for the home team raise home win probability
        wp.append({"about": {"atBatIndex": ab}, "homeTeamWinProbability": None, "homeTeamWinProbabilityAdded": w,
                   "result": {"description": desc}})
    feed = {"gamePk": pk, "gameData": {"teams": {"away": {"abbreviation": g["away"]}, "home": {"abbreviation": g["home"]}},
                                        "datetime": {"officialDate": g["start"][:10]}}, "liveData": {"plays": {"allPlays": plays}}}
    end = t0 + timedelta(minutes=3 * 54)
    items, nid = [], [pk * 100]

    def item(headline, guid=None, date=None, secs=20, tax=("highlight",)):
        nid[0] += 1
        it = {"id": nid[0], "headline": headline, "date": iso(date or end), "duration": dur(secs),
              "keywordsAll": [{"type": "taxonomy", "value": t} for t in tax],
              "playbacks": [{"name": "mp4Avc", "url": f"https://example.invalid/lunch-reel-synthetic/{pk}/{nid[0]}.mp4"}]}
        if guid: it["guid"] = guid
        items.append(it)

    last = lambda ab: pitch[ab][-1]
    pub = lambda ab: datetime.fromisoformat(last(ab)["startTime"].replace("Z", "+00:00")) + timedelta(minutes=4)
    for ab in g["clips"]:
        what = g["hot_play"].get(ab) or ("RBI hit" if g["runs"].get(ab) else rng.choice(["diving stop", "strikeout", "leaping catch", "stolen base"]))
        h = f"Synthetic Batter {ab % 13 + 1}'s {what} (inning {ab // 6 + 1}, synthetic)"
        if ab == 53: h = f"Synthetic Closer {pk % 7} seals the synthetic win"
        item(h, last(ab)["playId"], end + timedelta(hours=4) if ab in g["late"] else pub(ab), rng.randint(12, 34))
    for ab in g["abs_review"]:  # ABS clip with NO guid -> anchored to the review pitch published just before it
        rt = datetime.fromisoformat(pitch[ab][0]["startTime"].replace("Z", "+00:00"))
        item(f"ABS challenge overturns a called strike (synthetic, inning {ab // 6 + 1})", None, rt + timedelta(minutes=2), 10)
    for ab in g["abs_guid"]:    # ABS clip WITH a guid on the review pitch
        item(f"ABS challenge: ball call overturned (synthetic, inning {ab // 6 + 1})", pitch[ab][0]["playId"], pub(ab), 11)
    c0 = g["clips"]
    item("Synthetic Manager on the series win", None, end + timedelta(minutes=30), 95, ("interview", "manager-postgame"))
    item(f"Field View: Synthetic Batter {c0[1] % 13 + 1}'s highlight", last(c0[1])["playId"], pub(c0[1]), 18)
    item("Condensed Game: synthetic", None, end + timedelta(hours=1), 900, ("condensed-game",))
    item("Synthetic Pitcher strikes out five", None, end + timedelta(minutes=20), 40, ("performance",))
    item("Synthetic Batter 3 crushes a 450-foot homer", None, end + timedelta(minutes=50), 22)        # no guid -> unmapped
    item(f"Synthetic Batter {c0[3] % 13 + 1}'s highlight, broadcast cut", last(c0[3])["playId"], pub(c0[3]) + timedelta(minutes=1), 21)  # dup anchor
    item("Synthetic ceremony, full", last(c0[5])["playId"], pub(c0[5]), 75)                            # too long
    return {"copyright": "SYNTHETIC test data generated by tools/make_synthetic.py. Not MLB data.",
            "highlights": {"highlights": {"items": items}}}, feed, wp


def schedule(date, games):
    out = []
    for x in games:
        st = x.get("state", ("Final", "Final"))
        out.append({"gamePk": x["pk"], "officialDate": date, "gameDate": x["gameDate"], "gameNumber": x.get("gameNumber", 1),
                    "doubleHeader": x.get("dh", "N"), "status": {"abstractGameState": st[0], "detailedState": st[1]},
                    "teams": {s: {"id": TEAMS[x[s]][0], "name": TEAMS[x[s]][1]} for s in ("away", "home")}})
    return {"date": date, "synthetic": True, "games": out}


def main(argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures")
    for pk, g in GAMES.items():
        c, f, w = build(pk, g)
        d = os.path.join(out, str(pk)); os.makedirs(d, exist_ok=True)
        for name, obj in (("content.json", c), ("feed_trim.json", f), ("winProbability.json", w)):
            with open(os.path.join(d, name), "w") as fh: json.dump(obj, fh, indent=1); fh.write("\n")
    os.makedirs(os.path.join(out, "schedule"), exist_ok=True)
    for date, games in SCHEDULES.items():
        with open(os.path.join(out, "schedule", f"{date}.json"), "w") as fh: json.dump(schedule(date, games), fh, indent=1); fh.write("\n")
    print("wrote synthetic fixtures ->", os.path.normpath(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
