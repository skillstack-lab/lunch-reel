"""Slate reel (ADR 0004): rank across all final games on a date, group by game."""
import copy, json, pathlib, sys, pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "clip-cutter" / "scripts"))  # vendored cutter
import reel2

FX = str(ROOT / "fixtures")
DATE = "2099-04-01"
SLATE_PKS = {990003, 990002, 990004}
BUDGETS = [{"max_seconds": 60}, {"max_seconds": 300}, {"top": 1}, {"top": 6}, {"top": 10, "max_seconds": 240}, {}]


def slate(sched=None, **kw):
    return reel2.plan_slate(sched or reel2.load_schedule(DATE, FX), reel2.game_loader(FX), **kw)


def all_clips():
    return slate()["clips"]


def test_slate_fixture_has_three_games_with_data():
    sched = reel2.load_schedule(DATE, FX)
    assert SLATE_PKS <= {g["gamePk"] for g in sched["games"]}
    assert {g["gamePk"] for g in slate()["games"]} == SLATE_PKS


@pytest.mark.parametrize("kw", BUDGETS)
def test_league_hottest_clip_always_kept(kw):
    hottest = max(all_clips(), key=lambda c: c["score"])
    assert (hottest["gamePk"], hottest["anchor"]) in {(c["gamePk"], c["anchor"]) for c in slate(**kw)["clips"]}


@pytest.mark.parametrize("kw", BUDGETS)
def test_slate_budget_respected(kw):
    e = slate(**kw)
    if kw.get("top") is not None: assert len(e["clips"]) <= kw["top"]
    if kw.get("max_seconds") is not None: assert e["seconds"] <= kw["max_seconds"]
    assert e["seconds"] == sum(g["seconds"] for g in e["games"]) == sum(c["dur"] for c in e["clips"])


@pytest.mark.parametrize("kw", BUDGETS)
def test_each_game_in_game_order_and_contiguous(kw):
    e = slate(**kw)
    for g in e["games"]:
        keys = [(c["atBatIndex"], c["eventIndex"]) for c in g["clips"]]
        assert keys == sorted(keys) and all(c["gamePk"] == g["gamePk"] for c in g["clips"])
    seq = [c["gamePk"] for c in e["clips"]]
    assert seq == [g["gamePk"] for g in e["games"] for _ in g["clips"]]  # one block per game


@pytest.mark.parametrize("kw", BUDGETS)
def test_games_ordered_chronologically(kw):
    # ADR 0008 (amends 0004): game blocks run in start order (gameDate, then doubleheader gameNumber), not hottest-first
    sched = {g["gamePk"]: g for g in reel2.load_schedule(DATE, FX)["games"]}
    keys = [reel2.game_start_key(sched[g["gamePk"]]) for g in slate(**kw)["games"]]
    assert keys == sorted(keys)


def test_game_start_key_fallbacks():
    k = reel2.game_start_key
    # gamePk is not start order (NYY G1 990003 > G2 990002): gameNumber decides when gameDate is missing or tied
    g1 = {"gamePk": 990003, "officialDate": "2099-04-01", "gameNumber": 1}
    g2 = {"gamePk": 990002, "officialDate": "2099-04-01", "gameNumber": 2}
    assert k(g1) < k(g2)
    assert k({**g1, "gameDate": "2099-04-01T20:05:00Z"}) < k({**g2, "gameDate": "2099-04-01T20:10:00Z"})
    assert k({**g1, "gameDate": "2099-04-01T20:05:00Z"}) < k({**g2, "gameDate": "2099-04-01T20:05:00Z"})


def test_unbudgeted_slate_is_union_of_game_plans():
    for pk in SLATE_PKS:
        c, f = reel2.load(str(pk), FX)
        mine = {x["anchor"] for x in reel2.plan(c, f, wp=reel2.load_wp(str(pk), FX))["clips"]}
        assert mine == {x["anchor"] for x in all_clips() if x["gamePk"] == pk}


def test_known_slate_60s():
    # greedy skip-and-fill, each new game costs a 2.5 s title card (ADR 0006):
    # G1 two-run HR (21.1, 13+2.5) -> HOU@ATH (19.0, 20+2.5) -> 17.5 (34 s), 15.5 (32+2.5), 14.0 (25 s) no fit
    # -> G2 RBI hit (12.0, 19+2.5) fills to 59.5
    e = slate(max_seconds=60)
    # blocks in start order: NYY G1 (17:05Z), NYY G2 (21:10Z), HOU@ATH (01:40Z next day); gamePk is NOT start order
    assert [g["gamePk"] for g in e["games"]] == [990003, 990002, 990004]
    assert [(c["gamePk"], c["atBatIndex"]) for c in e["clips"]] == [(990003, 22), (990002, 44), (990004, 20)]
    assert e["total_seconds"] == 59.5 and e["card_seconds"] == 7.5


@pytest.mark.parametrize("kw", BUDGETS)
def test_budget_includes_title_cards(kw):
    e = slate(**kw)
    if kw.get("max_seconds") is not None and len(e["clips"]) > 1: assert e["total_seconds"] <= kw["max_seconds"]
    assert e["total_seconds"] == e["seconds"] + reel2.CARD_S * len(e["games"])


def test_non_final_and_missing_games_are_skipped_not_silent():
    sched = copy.deepcopy(reel2.load_schedule(DATE, FX))
    g = next(g for g in sched["games"] if g["gamePk"] == 990004)
    g["status"] = {"abstractGameState": "Preview", "detailedState": "Postponed"}
    e = slate(sched)
    why = {s["gamePk"]: s["why"] for s in e["skipped"]}
    assert why[990004] == "status:Postponed" and why[990005] == "no-data" and why[990006] == "status:Postponed"
    assert 990004 not in {x["gamePk"] for x in e["games"]}


def test_slate_cli_plan_only():
    import subprocess
    out = subprocess.run([sys.executable, str(ROOT / "reel2.py"), "--date", DATE, "--fixtures", FX, "--plan-only",
                          "--max-seconds", "300"], capture_output=True, text=True, check=True).stdout
    e = json.loads(out)
    assert e["date"] == DATE and e["seconds"] <= 300 and e["games"]
