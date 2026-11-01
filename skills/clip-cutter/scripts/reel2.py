#!/usr/bin/env python3
"""reel2 — stitch MLB's already-cut per-play highlight mp4s (statsapi content) into one PRIVATE catch-up reel.

Lunch Reel / clip-cutter skill v1.9. Self-contained: this file is the whole cutter (stdlib only; ffmpeg/curl to render).
Run it from the directory where cache/ and out/ should live (the scripts/clip-cutter wrapper does that for you).

usage:
  python3 reel2.py GAMEPK                      # fetch content+feed, plan, download (cached), stitch -> out/reel_GAMEPK_hl.mp4
  python3 reel2.py GAMEPK --plan-only          # print the edit decision list (EDL) as JSON, no video work
  python3 reel2.py GAMEPK --fixtures fixtures  # use fixtures/GAMEPK/{content,feed_trim,winProbability}.json instead of network
                                               # (bundled fixtures are SYNTHETIC: gamePks 99xxxx, dates 2099-04-01/02)
  python3 reel2.py --date 2026-09-25 --max-seconds 300 [--top N] [--fixtures fixtures] [--plan-only]
                                               # slate: rank clips across all final games that day, game blocks in start order -> out/slate_DATE.mp4
  python3 reel2.py --date 2026-09-25 --team NYY|147 --max-seconds 240 [--against-weight 0.75]
                                               # team reel: that team's final games only -> out/team_ABBR_DATE.mp4
  --no-labels : skip burn-in lower third + per-game title cards (ADR 0006)
  flags: --no-abs (drop ABS challenge clips; the default since ADR 0007)  --keep-unmapped (keep multi-play packages / unanchored clips)
         --top N  --max-seconds S   (rank clips by |WPA| of their at-bat, keep the hottest, output still in game order)
         --abs-weight W             (ABS challenge clips: default 0 = left out; 0.5 = kept at half score; 1 = no discount)

Editorial rules (v1):
  1. drop non-play content: interview / press-conference / postgame / game-recap / condensed-game / performance taxonomy,
     duration 0 or > 60s, "Field View:" alternate angles, talk-ish headlines ("X on Y")
  2. anchor every kept clip to game time: guid == feed playEvents[].playId (exact); ABS clips -> nearest review event
     at/before publish time; otherwise unmapped (dropped unless --keep-unmapped, then anchored to last pitch before publish)
  3. order by (atBatIndex, eventIndex) = true chronology, dedupe by anchor playId
  4. (optional) rank: score = |homeTeamWinProbabilityAdded| of the clip's at-bat (statsapi winProbability);
     ABS challenge clips are left out by default (--abs-weight 0); with W>0 they are scored x W; greedily keep highest score first under --top / --max-seconds (the single hottest clip is always kept),
     then re-sort to game order. Hot plays with no clip are reported as "missed_hot".
Rights: private viewing only. Ship the cutter, never the clips. Not affiliated with MLB / MLB Advanced Media.
License: MIT (this code only; grants no rights to MLB data or media).
"""
import json, os, re, subprocess, sys, urllib.request as u
from datetime import datetime, timedelta

DROP_TAX = {"interview", "press-conference", "manager-postgame", "player-postgame", "postgame",
            "game-recap", "condensed-game", "performance", "highlight-reel-pitch", "highlight-reel-relie"}
MAX_CLIP_S = 60
TALK_RE = re.compile(r"^[A-Z][\w.'\- ]+ (on|discusses|talks|speaks|reflects)\b", re.I)
ALT_RE = re.compile(r"^(field view|alternate angle|slow[- ]?mo)\b", re.I)
ABS_RE = re.compile(r"\bABS challenge\b", re.I)
ABS_WINDOW = timedelta(minutes=10)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def secs(t):
    try:
        h, m, s = map(int, (t or "00:00:00").split(":")); return h * 3600 + m * 60 + s
    except ValueError:
        return 0


def taxonomy(x):
    return {k.get("value") for k in x.get("keywordsAll", []) if k.get("type") == "taxonomy"}


def drop_reason(x):
    """Return why an item is not a single-play game-action clip, or None to keep."""
    h = (x.get("headline") or "").strip()
    tax = taxonomy(x)
    if tax & DROP_TAX: return "taxonomy:" + ",".join(sorted(tax & DROP_TAX))
    d = secs(x.get("duration"))
    if d == 0: return "no-duration"
    if d > MAX_CLIP_S: return f"too-long:{d}s"
    if ALT_RE.search(h): return "alt-angle"
    if TALK_RE.search(h) and not x.get("guid"): return "talk-headline"
    if not any(p.get("url", "").endswith(".mp4") for p in x.get("playbacks", [])): return "no-mp4"
    return None


def index_feed(feed):
    """playId -> anchor; plus ordered list of review events and all pitches with startTime."""
    by_id, reviews, events = {}, [], []
    score = (0, 0)  # (away, home) BEFORE the current plate appearance -> spoiler-free scoreboard (ADR 0006)
    for p in feed["liveData"]["plays"]["allPlays"]:
        ab = p["about"]
        evs = [e for e in p["playEvents"] if e.get("playId")]
        for i, e in enumerate(p["playEvents"]):
            if not e.get("playId"): continue
            a = {"playId": e["playId"], "atBatIndex": ab["atBatIndex"], "eventIndex": i, "inning": ab["inning"],
                 "half": ab["halfInning"], "t": ts(e.get("startTime")), "desc": p["result"].get("description", ""),
                 "pre": score}
            by_id[e["playId"]] = a; events.append(a)
            if e.get("reviewDetails"): reviews.append(a)
        if p.get("reviewDetails") and evs:  # play-level review -> last pitch of the PA
            reviews.append(by_id[evs[-1]["playId"]])
        r = p["result"]
        if r.get("awayScore") is not None and r.get("homeScore") is not None: score = (r["awayScore"], r["homeScore"])
    return by_id, sorted(reviews, key=lambda a: a["t"]), sorted([e for e in events if e["t"]], key=lambda a: a["t"])


def last_before(cands, t, window=None):
    best = None
    for a in cands:
        if a["t"] and a["t"] <= t and (window is None or t - a["t"] <= window): best = a
    return best


ABS_WEIGHT = 0.0  # ADR 0007 (amends 0003): lunch reels skip challenges by default; 0 = drop ABS clips, 0.5 = old discount


def plan(content, feed, abs_clips=True, keep_unmapped=False, wp=None, top=None, max_seconds=None, abs_weight=ABS_WEIGHT):
    if not abs_weight: abs_clips = False  # ADR 0007: weight 0 means no challenge clips at all, budgeted or not
    by_id, reviews, events = index_feed(feed)
    gt = feed.get("gameData", {}).get("teams", {})
    teams = {s: gt.get(s, {}).get("abbreviation", s.upper()) for s in ("away", "home")}
    keep, dropped, used_reviews = [], [], set()
    items = content["highlights"]["highlights"]["items"]
    for x in sorted(items, key=lambda x: x.get("date", "")):
        h = (x.get("headline") or "").strip()
        r = drop_reason(x)
        if r: dropped.append({"headline": h, "why": r}); continue
        if ABS_RE.search(h) and not abs_clips: dropped.append({"headline": h, "why": "abs-off"}); continue
        anchor, how = by_id.get(x.get("guid")), "guid"
        if anchor is None and ABS_RE.search(h):
            free = [a for a in reviews if a["playId"] not in used_reviews]
            anchor, how = last_before(free, ts(x.get("date")), ABS_WINDOW), "abs-review"
            if anchor: used_reviews.add(anchor["playId"])
        if anchor is None:
            if not keep_unmapped: dropped.append({"headline": h, "why": "unmapped"}); continue
            anchor, how = last_before(events, ts(x.get("date"))), "publish-time"
            if anchor is None: dropped.append({"headline": h, "why": "unanchored"}); continue
        mp4 = [p["url"] for p in x["playbacks"] if p["url"].endswith(".mp4")][0]
        keep.append({"key": x.get("guid") or str(x.get("id")), "headline": h, "url": mp4, "dur": secs(x.get("duration")),
                     "anchor": anchor["playId"], "how": how, "atBatIndex": anchor["atBatIndex"],
                     "eventIndex": anchor["eventIndex"], "inning": f'{anchor["half"][:3]} {anchor["inning"]}',
                     "abs": bool(ABS_RE.search(h)), "half": anchor["half"], "inningNum": anchor["inning"],
                     "pre": list(anchor["pre"]), "away": teams["away"], "home": teams["home"]})
    keep.sort(key=lambda c: (c["atBatIndex"], c["eventIndex"], not c["abs"]))
    seen, edl = set(), []
    for c in keep:  # one clip per anchor pitch (ABS + its play can share a PA but not a pitch)
        if c["anchor"] in seen: dropped.append({"headline": c["headline"], "why": "dup-anchor"}); continue
        seen.add(c["anchor"]); edl.append(c)
    out = {"clips": edl, "dropped": dropped}
    if wp is not None:
        out.update(rank(edl, wp, top, max_seconds, abs_weight=abs_weight))
        for c in edl:
            if c not in out["clips"]: dropped.append({"headline": c["headline"], "why": "below-cut"})
    elif top or max_seconds:
        raise ValueError("--top/--max-seconds need winProbability data")
    out["seconds"] = sum(c["dur"] for c in out["clips"])
    return out


def select(clips, top=None, max_seconds=None, group_cost=0.0):
    """Greedy by score (ties: real play before ABS, then game/at-bat order); #1 always kept; skip-and-continue fill.
    group_cost: seconds charged the first time a clip's game enters the reel (title card, ADR 0006)."""
    order = sorted(clips, key=lambda c: (-c["score"], c["abs"], c.get("gamePk", 0), c["atBatIndex"], c["eventIndex"]))
    picked, secs_used, groups = [], 0.0, set()
    for i, c in enumerate(order):
        if top is not None and len(picked) >= top: break
        cost = c["dur"] + (group_cost if c.get("gamePk") not in groups else 0)
        if i > 0 and max_seconds is not None and secs_used + cost > max_seconds: continue
        picked.append(c); secs_used += cost; groups.add(c.get("gamePk"))
    return picked


AGAINST_WEIGHT = 0.75  # ADR 0005: in a team reel, plays that hurt the team still matter (how they lost), but rank lower


def resolve_team(team, teams):
    """ABBR or numeric id -> {'id','abbr','name'}; raises on unknown."""
    t = str(team).upper()
    for x in teams["teams"]:
        if t == x["abbr"].upper() or t == str(x["id"]): return x
    raise ValueError(f"unknown team {team!r}")


def load_teams(fixtures=None):
    if fixtures and os.path.exists(os.path.join(fixtures, "teams.json")): return json.load(open(os.path.join(fixtures, "teams.json")))
    if os.environ.get("CLIP_CUTTER_TEAMS"): return json.load(open(os.environ["CLIP_CUTTER_TEAMS"]))  # skill assets/teams.json
    return {"teams": [{"id": x["id"], "abbr": x["abbreviation"], "name": x["name"]}
                      for x in J("https://statsapi.mlb.com/api/v1/teams?sportId=1")["teams"]]}


def plan_team(schedule, loader, team, top=None, max_seconds=None, against_weight=AGAINST_WEIGHT, **kw):
    """One reel for one team on a date (ADR 0005): only its games; clips that helped the team score x1, hurt x against_weight."""
    tid = team["id"]
    mine = [g for g in schedule["games"] if tid in (g["teams"]["away"]["id"], g["teams"]["home"]["id"])]
    e = plan_slate({"date": schedule.get("date"), "games": mine}, loader, top=top, max_seconds=max_seconds,
                   team_id=tid, against_weight=against_weight, **kw)
    e["team"] = team
    if not mine: e["skipped"].append({"team": team["abbr"], "why": "no-game"})
    elif not e["games"]: e["skipped"].append({"team": team["abbr"], "why": "no-playable-game"})
    return e


def game_start_key(g):
    """Chronological sort key for a schedule game (ADR 0008). gameDate is ISO-8601 UTC, so string order is time order;
    gameNumber breaks doubleheader ties (and stands in when gameDate is missing); gamePk last (it is NOT start order)."""
    return (g.get("officialDate") or "", g.get("gameDate") or "", g.get("gameNumber") or 1, g["gamePk"])


def plan_slate(schedule, loader, top=None, max_seconds=None, abs_weight=ABS_WEIGHT, abs_clips=True, keep_unmapped=False,
               team_id=None, against_weight=AGAINST_WEIGHT, card_s=None):
    """League-wide reel for one date (ADR 0004).
    loader(pk) -> (content, feed, wp) or None (skipped). Rank ALL clips across final games by score under the budget,
    then group by game: game blocks in chronological order (ADR 0008: start time, then doubleheader game number, then gamePk);
    clips inside a game in game order."""
    card_s = CARD_S if card_s is None else card_s
    games, pool, skipped = {}, [], []
    for g in schedule["games"]:
        pk = g["gamePk"]
        if g["status"]["abstractGameState"] != "Final" or g["status"]["detailedState"] not in ("Final", "Completed Early"):
            skipped.append({"gamePk": pk, "why": "status:" + g["status"]["detailedState"]}); continue
        data = loader(pk)
        if data is None: skipped.append({"gamePk": pk, "why": "no-data"}); continue
        content, feed, wp = data
        e = plan(content, feed, abs_clips=abs_clips, keep_unmapped=keep_unmapped, wp=wp, abs_weight=abs_weight)
        label = f'{g["teams"]["away"]["name"]} @ {g["teams"]["home"]["name"]}' + (f' (G{g["gameNumber"]})' if g.get("doubleHeader") not in (None, "N") else "")
        games[pk] = {"gamePk": pk, "label": label, "start": game_start_key(g), "card": card_lines(g, schedule.get("date")), "missed_hot": e.get("missed_hot", []), "clips": []}
        team_home = None if team_id is None else (g["teams"]["home"]["id"] == team_id)
        for c in e["clips"]:
            c["gamePk"] = pk
            if team_home is not None:
                c["for_team"] = (c["home_wpa"] > 0) == team_home if c["home_wpa"] else True
                if not c["for_team"]: c["score"] = round(c["score"] * against_weight, 2)
            pool.append(c)
    for c in select(pool, top, max_seconds, group_cost=card_s): games[c["gamePk"]]["clips"].append(c)
    out_games = [g for g in games.values() if g["clips"]]
    for g in out_games:
        g["clips"].sort(key=lambda c: (c["atBatIndex"], c["eventIndex"], not c["abs"]))
        g["seconds"] = sum(c["dur"] for c in g["clips"]); g["best"] = max(c["score"] for c in g["clips"])
    out_games.sort(key=lambda g: g["start"])  # chronological game blocks (ADR 0008; was hottest-first under 0004)
    for g in games.values(): del g["start"]
    skipped += [{"gamePk": pk, "why": "below-cut"} for pk, g in games.items() if not g["clips"]]
    clips = [c for g in out_games for c in g["clips"]]
    secs_ = sum(c["dur"] for c in clips)
    return {"date": schedule.get("date"), "games": out_games, "clips": clips, "seconds": secs_,
            "card_seconds": card_s * len(out_games), "total_seconds": secs_ + card_s * len(out_games), "skipped": skipped}


def load_schedule(date, fixtures=None):
    if fixtures: return json.load(open(os.path.join(fixtures, "schedule", f"{date}.json")))
    d = J(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}")
    return {"date": date, "games": [{"gamePk": x["gamePk"], "officialDate": x["officialDate"], "gameDate": x.get("gameDate"), "gameNumber": x.get("gameNumber"),
            "doubleHeader": x.get("doubleHeader"), "status": {k: x["status"][k] for k in ("abstractGameState", "detailedState")},
            "teams": {s: {"id": x["teams"][s]["team"]["id"], "name": x["teams"][s]["team"]["name"]} for s in ("away", "home")}}
            for dd in d["dates"] for x in dd["games"]]}


def game_loader(fixtures=None):
    def f(pk):
        if fixtures and not os.path.exists(os.path.join(fixtures, str(pk), "content.json")): return None
        c, fd = load(pk, fixtures); return c, fd, load_wp(pk, fixtures)
    return f


def rank(edl, wp, top=None, max_seconds=None, missed_n=5, abs_weight=ABS_WEIGHT):
    """Score clips by |WPA| of their at-bat; keep hottest under budget; return in game order."""
    home = {p["about"]["atBatIndex"]: (p.get("homeTeamWinProbabilityAdded") or 0.0) for p in wp}
    wpa = {k: abs(v) for k, v in home.items()}
    for c in edl:
        c["wpa"] = round(wpa.get(c["atBatIndex"], 0.0), 2)  # raw at-bat |WPA|
        c["home_wpa"] = round(home.get(c["atBatIndex"], 0.0), 2)  # signed, home perspective
        c["score"] = round(c["wpa"] * (abs_weight if c["abs"] else 1.0), 2)  # ranking key
    picked = select(edl, top, max_seconds)
    picked.sort(key=lambda c: (c["atBatIndex"], c["eventIndex"], not c["abs"]))
    covered = {c["atBatIndex"] for c in edl}
    hot = sorted(wp, key=lambda p: -abs(p.get("homeTeamWinProbabilityAdded") or 0.0))[:missed_n]
    missed = [{"atBatIndex": p["about"]["atBatIndex"], "wpa": round(abs(p.get("homeTeamWinProbabilityAdded") or 0), 2),
               "desc": p.get("result", {}).get("description", "")[:100]} for p in hot if p["about"]["atBatIndex"] not in covered]
    return {"clips": picked, "missed_hot": missed}


def J(url):
    return json.load(u.urlopen(u.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30))


def load_wp(pk, fixtures=None):
    if fixtures:
        f = os.path.join(fixtures, str(pk), "winProbability.json")
        if os.path.exists(f): return json.load(open(f))
    return J(f"https://statsapi.mlb.com/api/v1/game/{pk}/winProbability")


def load(pk, fixtures=None):
    if fixtures:
        d = os.path.join(fixtures, str(pk))
        return json.load(open(f"{d}/content.json")), json.load(open(f"{d}/feed_trim.json"))
    return (J(f"https://statsapi.mlb.com/api/v1/game/{pk}/content"),
            J(f"https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"))


# ---- burn-in labels (ADR 0006) ----------------------------------------------------------------------------------
CARD_S = 2.5
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
VENC = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", "-video_track_timescale", "15360",
        "-c:a", "aac", "-ar", "48000", "-ac", "2"]


def label_text(c):
    """Spoiler-free lower third: score BEFORE the plate appearance + half-inning, e.g. 'BAL 0  NYY 1   BOT 4'."""
    a, h = c.get("pre", [0, 0])
    half = {"top": "TOP", "bottom": "BOT"}.get(c.get("half"), (c.get("half") or "").upper()[:3])
    t = f'{c.get("away", "AWAY")} {a}  {c.get("home", "HOME")} {h}   {half} {c.get("inningNum", "")}'.rstrip()
    return t + ("   ABS CHALLENGE" if c.get("abs") else "")


def card_lines(g, date):
    """Title card: matchup, doubleheader game no., date. No final score (spoiler-free)."""
    dh = f' · GAME {g["gameNumber"]}' if g.get("doubleHeader") not in (None, "N") else ""
    return [f'{g["teams"]["away"]["name"]} at {g["teams"]["home"]["name"]}', f'{date or ""}{dh}'.strip(" ·")]


TEXT_DIR = os.path.join("cache", "labels")  # relative to the run dir, so the vendored skill folder stays read-only


def textfile(t, d=None):
    """Write label text to a content-addressed file and return its path. drawtext reads it via textfile= with
    expansion=none, so no filtergraph escaping is needed for ':' ',' '%' quotes or accents (ADR 0006)."""
    import hashlib
    d = d or TEXT_DIR; os.makedirs(d, exist_ok=True)
    p = os.path.join(d, hashlib.sha1(t.encode()).hexdigest()[:12] + ".txt")
    if not os.path.exists(p): open(p, "w", encoding="utf-8").write(t)
    return p


def drawtext(t, x, y, size, font=FONT, d=None):
    return f"drawtext=fontfile={font}:textfile={textfile(t, d)}:expansion=none:x={x}:y={y}:fontsize={size}:fontcolor=white"


def label_vf(c, font=FONT, d=None):
    return ("scale=1280:720,fps=30,drawbox=x=0:y=ih-84:w=iw:h=84:color=black@0.6:t=fill,"
            + drawtext(label_text(c), 32, "h-60", 38, font, d))


def card_vf(lines, font=FONT, d=None):
    spots = [("h/2-70", 54), ("h/2+10", 36)]
    return ",".join(drawtext(ln, "(w-text_w)/2", y, sz, font, d) for ln, (y, sz) in zip(lines, spots)) or "null"


def make_card(lines, dst, secs=CARD_S):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x0b1f3a:s=1280x720:r=30:d={secs}",
                    "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo", "-t", str(secs), "-vf", card_vf(lines), *VENC, dst],
                   check=True)


def render(pk, edl, cache="cache", out="out", name=None, labels=True):
    os.makedirs(f"{cache}/{pk}", exist_ok=True); os.makedirs(out, exist_ok=True)
    norm = []
    import hashlib
    first_of = {g["clips"][0]["anchor"]: g for g in edl.get("games", []) if g["clips"]} if labels else {}
    for c in edl["clips"]:
        gpk = c.get("gamePk", pk); os.makedirs(f"{cache}/{gpk}", exist_ok=True)
        if c["anchor"] in first_of:
            g = first_of[c["anchor"]]; tag = hashlib.sha1("|".join(g["card"]).encode()).hexdigest()[:8]
            card = f"{cache}/{gpk}/card_{tag}.mp4"
            if not os.path.exists(card): make_card(g["card"], card)
            norm.append(os.path.abspath(card)); print(f"   [card] {' / '.join(g['card'])}")
        raw = f"{cache}/{gpk}/{c['key']}.mp4"
        vf = label_vf(c) if labels else "scale=1280:720,fps=30"
        n = f"{cache}/{gpk}/l_{c['key']}_{hashlib.sha1(vf.encode()).hexdigest()[:8]}.mp4"
        if not os.path.exists(n):
            if not os.path.exists(raw): subprocess.run(["curl", "-sfL", "-o", raw, c["url"]], check=True)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-t", str(c["dur"]), "-vf", vf, *VENC, n],
                           check=True)  # -t: trim to metadata length so the reel honours the budget
        norm.append(os.path.abspath(n)); print(f"{c['inning']:>7}  {c['how']:<12} {c['headline']}")
    lst = f"{cache}/{pk}/list.txt"
    open(lst, "w").write("".join(f"file '{n}'\n" for n in norm))
    dst = f"{out}/{name or f'reel_{pk}_hl'}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", dst], check=True)
    return dst


def main(argv):
    if not argv or (argv[0].startswith("-") and "--date" not in argv): print(__doc__); return 2
    flags = set(a for a in argv if a.startswith("--"))
    fx = argv[argv.index("--fixtures") + 1] if "--fixtures" in argv else None
    opt = lambda k, f: f(argv[argv.index(k) + 1]) if k in argv else None
    top, max_s, abs_w = opt("--top", int), opt("--max-seconds", int), opt("--abs-weight", float)
    if "--date" in flags and "--team" in flags:
        date = opt("--date", str)
        team = resolve_team(opt("--team", str), load_teams(fx))
        aw = opt("--against-weight", float)
        e = plan_team(load_schedule(date, fx), game_loader(fx), team, top=top, max_seconds=max_s,
                      against_weight=AGAINST_WEIGHT if aw is None else aw, abs_weight=ABS_WEIGHT if abs_w is None else abs_w,
                      abs_clips="--no-abs" not in flags, keep_unmapped="--keep-unmapped" in flags)
        if "--plan-only" in flags: print(json.dumps(e, indent=1)); return 0
        if not e["clips"]: print("no reel:", e["skipped"]); return 1
        print("done", render("team", e, name=f"team_{team['abbr']}_{date}", labels="--no-labels" not in flags), f"{len(e['clips'])} clips ~{e['seconds']}s")
        return 0
    if "--date" in flags:
        date = opt("--date", str)
        e = plan_slate(load_schedule(date, fx), game_loader(fx), top=top, max_seconds=max_s,
                       abs_weight=ABS_WEIGHT if abs_w is None else abs_w, abs_clips="--no-abs" not in flags,
                       keep_unmapped="--keep-unmapped" in flags)
        if "--plan-only" in flags: print(json.dumps(e, indent=1)); return 0
        print("done", render("slate", e, name=f"slate_{date}", labels="--no-labels" not in flags), f"{len(e['clips'])} clips ~{e['seconds']}s")
        return 0
    pk = argv[0]
    content, feed = load(pk, fx)
    wp = load_wp(pk, fx) if (top or max_s or "--rank" in flags) else None
    edl = plan(content, feed, abs_clips="--no-abs" not in flags, keep_unmapped="--keep-unmapped" in flags,
               wp=wp, top=top, max_seconds=max_s, abs_weight=ABS_WEIGHT if abs_w is None else abs_w)
    if "--plan-only" in flags: print(json.dumps(edl, indent=1)); return 0
    print("done", render(pk, edl, labels="--no-labels" not in flags), f"{len(edl['clips'])} clips ~{edl['seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
