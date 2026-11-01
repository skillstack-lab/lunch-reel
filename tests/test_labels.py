"""Burn-in labels (ADR 0006): spoiler-free lower third + per-game title card. No video work; filter strings only."""
import pathlib, re, sys, pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "clip-cutter" / "scripts"))  # vendored cutter
import reel2

FX = str(ROOT / "fixtures")


def texts(vf):
    return [pathlib.Path(p).read_text(encoding="utf-8") for p in re.findall(r"textfile=([^:,]+)", vf)]


def nyy():
    return reel2.plan_team(reel2.load_schedule("2099-04-01", FX), reel2.game_loader(FX), reel2.resolve_team("NYY", reel2.load_teams(FX)),
                           max_seconds=180)


def test_label_text_shape():
    c = {"away": "BAL", "home": "NYY", "pre": [0, 1], "half": "bottom", "inningNum": 4, "abs": False}
    assert reel2.label_text(c) == "BAL 0  NYY 1   BOT 4"
    assert reel2.label_text({**c, "abs": True}).endswith("ABS CHALLENGE")


def test_label_vf_has_team_inning_score(tmp_path):
    c = {"away": "BAL", "home": "NYY", "pre": [3, 2], "half": "top", "inningNum": 7, "abs": False}
    vf = reel2.label_vf(c, d=str(tmp_path))
    assert vf.startswith("scale=1280:720,fps=30,drawbox=") and "expansion=none" in vf and "fontfile=" in vf
    [t] = texts(vf)
    assert "BAL 3" in t and "NYY 2" in t and "TOP 7" in t


def test_awkward_text_needs_no_escaping(tmp_path):
    lines = ["O'Neil: 3, 100% St. Louis \\ Cardinals", "2026-09-25 · GAME 2"]
    vf = reel2.card_vf(lines, d=str(tmp_path))
    assert texts(vf) == lines and vf.count("drawtext=") == 2
    assert "'" not in vf and "%" not in vf  # all user text lives in files


@pytest.mark.parametrize("pk", ["990003", "990002", "990004", "990010"])
def test_every_clip_label_uses_pre_play_score(pk):
    c, f = reel2.load(pk, FX)
    plays = f["liveData"]["plays"]["allPlays"]
    final = (plays[-1]["result"]["awayScore"], plays[-1]["result"]["homeScore"])
    ab = {p["about"]["atBatIndex"]: p for p in plays}
    for clip in reel2.plan(c, f)["clips"]:
        prev = ab.get(clip["atBatIndex"] - 1)
        want = [prev["result"]["awayScore"], prev["result"]["homeScore"]] if prev else [0, 0]
        assert clip["pre"] == want, clip["headline"]
        t = reel2.label_text(clip)
        assert clip["away"] in t and clip["home"] in t and str(clip["inningNum"]) in t
    assert reel2.plan(c, f)["clips"][0]["pre"] != list(final) or final == (0, 0)


def test_990003_known_labels():
    c, f = reel2.load("990003", FX)
    clips = reel2.plan(c, f)["clips"]
    assert reel2.label_text(clips[0]) == "BAL 0  NYY 0   TOP 1"      # second PA of the game: still 0-0
    last = reel2.label_text(clips[-1])                                # final out: score BEFORE it, never the final
    assert last.startswith("BAL 3  NYY 4") and last.endswith("BOT 9")


def test_team_reel_title_cards_spoiler_free():
    e = nyy()
    assert len(e["games"]) == 2
    for g in e["games"]:
        assert g["card"][0] == "Baltimore Orioles at New York Yankees" and "GAME" in g["card"][1]
        assert not re.search(r"\\b\\d+\\s*[-–]\\s*\\d+\\b", " ".join(g["card"][:1]))  # no final score on the card
    assert e["total_seconds"] <= 180
