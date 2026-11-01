"""Team reels (ADR 0005): one team's final games on a date, perspective-aware scoring."""
import json, pathlib, subprocess, sys, pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "clip-cutter" / "scripts"))  # vendored cutter
import reel2

FX = str(ROOT / "fixtures")
TEAMS = reel2.load_teams(FX)
UNDER = ["NYY", "LAD", "BAL", "ATH", "CHC"]  # the provisional "undercovered five" team-reel personas
# (team, date) cases with data
CASES = [("NYY", "2099-04-01"), ("BAL", "2099-04-01"), ("ATH", "2099-04-01"), ("CHC", "2099-04-02")]
BUDGETS = [{}, {"max_seconds": 60}, {"max_seconds": 180}, {"top": 1}, {"top": 4, "max_seconds": 120}]


def team_reel(abbr, date, **kw):
    return reel2.plan_team(reel2.load_schedule(date, FX), reel2.game_loader(FX), reel2.resolve_team(abbr, TEAMS), **kw)


def test_undercovered_five_resolve():
    assert UNDER == ["NYY", "LAD", "BAL", "ATH", "CHC"]
    assert [reel2.resolve_team(t, TEAMS)["id"] for t in UNDER] == [147, 119, 110, 133, 112]
    assert reel2.resolve_team("147", TEAMS)["abbr"] == "NYY" and reel2.resolve_team("nyy", TEAMS)["id"] == 147
    with pytest.raises(ValueError): reel2.resolve_team("XXX", TEAMS)


@pytest.mark.parametrize("abbr,date", CASES)
@pytest.mark.parametrize("kw", BUDGETS)
def test_only_that_teams_games(abbr, date, kw):
    tid = reel2.resolve_team(abbr, TEAMS)["id"]
    sched = {g["gamePk"]: g for g in reel2.load_schedule(date, FX)["games"]}
    e = team_reel(abbr, date, **kw)
    assert e["games"]
    for g in e["games"]:
        assert tid in (sched[g["gamePk"]]["teams"]["home"]["id"], sched[g["gamePk"]]["teams"]["away"]["id"])
    assert all(s.get("gamePk") is None or tid in (sched[s["gamePk"]]["teams"]["home"]["id"], sched[s["gamePk"]]["teams"]["away"]["id"])
               for s in e["skipped"])


@pytest.mark.parametrize("abbr,date", CASES)
@pytest.mark.parametrize("kw", BUDGETS)
def test_team_hottest_kept_budget_and_order(abbr, date, kw):
    full = team_reel(abbr, date)["clips"]
    hottest = max(full, key=lambda c: c["score"])
    e = team_reel(abbr, date, **kw)
    assert (hottest["gamePk"], hottest["anchor"]) in {(c["gamePk"], c["anchor"]) for c in e["clips"]}
    if kw.get("top") is not None: assert len(e["clips"]) <= kw["top"]
    if kw.get("max_seconds") is not None: assert e["seconds"] <= kw["max_seconds"]
    for g in e["games"]:
        keys = [(c["atBatIndex"], c["eventIndex"]) for c in g["clips"]]
        assert keys == sorted(keys)


@pytest.mark.parametrize("abbr,date", CASES)
def test_perspective_scoring(abbr, date):
    tid = reel2.resolve_team(abbr, TEAMS)["id"]
    home = {g["gamePk"]: g["teams"]["home"]["id"] == tid for g in reel2.load_schedule(date, FX)["games"]}
    for c in team_reel(abbr, date, against_weight=0.5)["clips"]:
        helped = c["home_wpa"] == 0 or (c["home_wpa"] > 0) == home[c["gamePk"]]
        assert c["for_team"] == helped
        base = round(c["wpa"] * (reel2.ABS_WEIGHT if c["abs"] else 1.0), 2)
        assert c["score"] == (base if helped else round(base * 0.5, 2))


def test_same_game_opposite_perspective_990010():
    # a play that helps BOS (home) hurts CHC: the CHC reel discounts it, the BOS reel does not
    chc = {c["anchor"]: c for c in team_reel("CHC", "2099-04-02")["clips"]}
    bos = {c["anchor"]: c for c in team_reel("BOS", "2099-04-02")["clips"]}
    r = next(a for a, c in bos.items() if c["home_wpa"] > 0)
    assert not chc[r]["for_team"] and bos[r]["for_team"] and chc[r]["score"] < bos[r]["score"]


def test_against_weight_1_matches_slate_scores():
    a = {c["anchor"]: c["score"] for c in team_reel("ATH", "2099-04-01", against_weight=1.0)["clips"]}
    s = {c["anchor"]: c["score"] for c in reel2.plan_slate(reel2.load_schedule("2099-04-01", FX), reel2.game_loader(FX))["clips"]
         if c["gamePk"] == 990004}
    assert a == s


@pytest.mark.parametrize("abbr,date,why", [
    ("LAD", "2099-04-01", "no-playable-game"),   # LAD@SF final, no fixture data
    ("CHC", "2099-04-01", "no-playable-game"),   # CHC@BOS postponed
    ("NYY", "2099-04-02", "no-playable-game"),   # 990011 cancelled
])
def test_team_without_playable_game_reported(abbr, date, why):
    e = team_reel(abbr, date)
    assert e["clips"] == [] and {"team": abbr, "why": why} in e["skipped"]


def test_team_with_no_game_that_day():
    sched = reel2.load_schedule("2099-04-01", FX)
    sched["games"] = [g for g in sched["games"] if 133 not in (g["teams"]["home"]["id"], g["teams"]["away"]["id"])]
    e = reel2.plan_team(sched, reel2.game_loader(FX), reel2.resolve_team("ATH", TEAMS))
    assert e["clips"] == [] and {"team": "ATH", "why": "no-game"} in e["skipped"]


def test_cancelled_status_reported_nyy_0402():
    e = team_reel("NYY", "2099-04-02")
    assert {"gamePk": 990011, "why": "status:Cancelled"} in e["skipped"]


def test_team_cli():
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "reel2.py"), "--date", "2099-04-01", "--fixtures", FX, *a],
                                    capture_output=True, text=True)
    r = run("--team", "ATH", "--plan-only", "--max-seconds", "120")
    e = json.loads(r.stdout)
    assert r.returncode == 0 and e["team"]["abbr"] == "ATH" and e["seconds"] <= 120
    assert run("--team", "LAD").returncode == 1  # no reel, no render attempted


# --- ABS off by default (ADR 0007) ------------------------------------------------------
def test_team_and_slate_default_no_abs_flag_restores():
    chc = lambda **kw: team_reel("CHC", "2099-04-02", max_seconds=120, **kw)["clips"]
    assert not any(c["abs"] for c in chc())
    old = chc(abs_weight=0.5)  # pre-0007 default: a high-swing ABS challenge makes the 2-min CHC reel
    assert any(c["abs"] and c["how"] == "abs-review" for c in old)
    full = team_reel("CHC", "2099-04-02")["clips"]
    assert not any(c["abs"] for c in full) and any(c["abs"] for c in team_reel("CHC", "2099-04-02", abs_weight=0.5)["clips"])


@pytest.mark.parametrize("kw", BUDGETS)
def test_nyy_doubleheader_game1_block_first(kw):
    # ADR 0008: a doubleheader reel once played G2 before G1 -> chronological game blocks
    e = team_reel("NYY", "2099-04-01", **kw)
    pks = [g["gamePk"] for g in e["games"]]
    if len(pks) == 2: assert pks == [990003, 990002]  # GAME 1 then GAME 2 (gamePk is not start order)
    assert [c["gamePk"] for c in e["clips"]] == [g["gamePk"] for g in e["games"] for _ in g["clips"]]
    for g in e["games"]:  # within a game: still true chronology of the selected clips
        keys = [(c["atBatIndex"], c["eventIndex"]) for c in g["clips"]]
        assert keys == sorted(keys)


def test_nyy_180_plan_both_games_g1_first():
    e = team_reel("NYY", "2099-04-01", max_seconds=180)
    assert [g["gamePk"] for g in e["games"]] == [990003, 990002]
    assert [g["card"][1][-6:] for g in e["games"]] == ["GAME 1", "GAME 2"]
    assert e["total_seconds"] <= 180

