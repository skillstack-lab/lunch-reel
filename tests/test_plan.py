"""Offline editorial checks on the bundled SYNTHETIC fixtures (tools/make_synthetic.py).
No network, no video, no MLB data. `just check` must exit 0."""
import json, pathlib, pytest, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "clip-cutter" / "scripts"))  # vendored cutter
import reel2

FIXTURES = ROOT / "fixtures"
PKS = sorted(p.name for p in FIXTURES.iterdir() if (p / "content.json").exists())
TALK_TAX = {"interview", "press-conference", "manager-postgame", "player-postgame", "game-recap", "condensed-game"}


def load(pk):
    return reel2.load(pk, str(FIXTURES))


def edl(pk, **kw):
    return reel2.plan(*load(pk), **kw)


def tax_by_headline(pk):
    c, _ = load(pk)
    return {x["headline"].strip(): reel2.taxonomy(x) for x in c["highlights"]["highlights"]["items"]}


def test_at_least_two_fixtures():
    assert len(PKS) >= 2, PKS


@pytest.mark.parametrize("pk", PKS)
def test_no_talk_in_reel(pk):
    tax = tax_by_headline(pk)
    for c in edl(pk)["clips"]:
        assert not (tax[c["headline"]] & TALK_TAX), c["headline"]
        assert not c["headline"].lower().startswith("field view"), c["headline"]


@pytest.mark.parametrize("pk", PKS)
def test_true_chronology(pk):
    keys = [(c["atBatIndex"], c["eventIndex"]) for c in edl(pk)["clips"]]
    assert keys == sorted(keys)


@pytest.mark.parametrize("pk", PKS)
def test_every_clip_anchored_and_unique(pk):
    clips = edl(pk)["clips"]
    assert all(c["anchor"] for c in clips)
    assert len({c["anchor"] for c in clips}) == len(clips)


@pytest.mark.parametrize("pk", PKS)
def test_lunch_break_length(pk):
    s = edl(pk)["seconds"]
    assert 120 <= s <= 15 * 60, s


@pytest.mark.parametrize("pk", PKS)
def test_abs_toggle(pk):
    on, off = edl(pk, abs_weight=0.5), edl(pk, abs_clips=False)
    assert any(c["abs"] for c in on["clips"]), "fixture should exercise ABS"
    assert not any(c["abs"] for c in off["clips"])
    assert all(c["how"] in {"guid", "abs-review"} for c in on["clips"] if c["abs"])  # 990004 has a guid-tagged ABS clip


def test_late_published_clip_keeps_game_position_990003():
    # regression (v0 bug): a clip published hours after the final out must still play at its pitch, not at the end
    c, _ = load("990003")
    items = c["highlights"]["highlights"]["items"]
    clips = edl("990003")["clips"]
    late = next(x for x in clips if x["atBatIndex"] == 47)
    late_item = next(x for x in items if x.get("guid") == late["anchor"])
    assert late_item["date"] == max(x["date"] for x in items if x.get("guid"))  # published last of all guid clips
    abs_ = [x["atBatIndex"] for x in clips]
    assert abs_.index(47) < abs_.index(53) and clips[-1]["headline"].endswith("seals the synthetic win")
    assert clips[0]["atBatIndex"] == 1


def test_rights_no_media_in_fixtures():
    media = [p for p in FIXTURES.rglob("*") if p.suffix.lower() in {".mp4", ".m3u8", ".ts", ".mov", ".webm"}]
    assert not media, media


# --- WPA ranking (cut: --top / --max-seconds) -------------------------------------------
def ranked(pk, **kw):
    c, f = load(pk)
    return reel2.plan(c, f, wp=reel2.load_wp(pk, str(FIXTURES)), **kw)


def test_wp_fixtures_present():
    for pk in PKS:
        assert (FIXTURES / pk / "winProbability.json").exists(), pk


@pytest.mark.parametrize("pk", PKS)
@pytest.mark.parametrize("kw", [{"top": 1}, {"top": 5}, {"max_seconds": 90}, {"top": 8, "max_seconds": 150}])
def test_hottest_clip_always_kept(pk, kw):
    full = ranked(pk)["clips"]
    hottest = max(full, key=lambda c: (c["score"], -c["atBatIndex"]))
    assert hottest["anchor"] in {c["anchor"] for c in ranked(pk, **kw)["clips"]}


@pytest.mark.parametrize("pk", PKS)
@pytest.mark.parametrize("kw", [{"top": 5}, {"max_seconds": 120}, {"top": 10, "max_seconds": 200}])
def test_ranked_output_stays_chronological(pk, kw):
    keys = [(c["atBatIndex"], c["eventIndex"]) for c in ranked(pk, **kw)["clips"]]
    assert keys == sorted(keys)


@pytest.mark.parametrize("pk", PKS)
@pytest.mark.parametrize("n,s", [(3, None), (6, None), (None, 60), (None, 120), (10, 180)])
def test_budget_respected(pk, n, s):
    e = ranked(pk, top=n, max_seconds=s)
    if n is not None: assert len(e["clips"]) <= n
    if s is not None: assert e["seconds"] <= s
    assert e["seconds"] == sum(c["dur"] for c in e["clips"])


@pytest.mark.parametrize("pk", PKS)
def test_ranked_subset_of_unranked(pk):
    full = {c["anchor"] for c in edl(pk)["clips"]}
    assert {c["anchor"] for c in ranked(pk, top=5)["clips"]} <= full
    assert len(ranked(pk)["clips"]) == len(full)  # wp without budget = same reel, just scored


def test_known_hot_990003():
    e = ranked("990003", top=3)
    assert [c["atBatIndex"] for c in e["clips"]] == [1, 16, 22]  # |WPA| 14.0, 9.5, 21.1 -> game order
    assert "two-run home run" in e["clips"][-1]["headline"]
    assert 40 in {m["atBatIndex"] for m in e["missed_hot"]}  # big swing (16.0), no clip -> surfaced, not hidden


def test_budget_flags_need_wp():
    with pytest.raises(ValueError):
        reel2.plan(*load("990003"), top=3)


# --- ABS discount (ADR 0003) -------------------------------------------------------------
def test_abs_discount_2min_picks_real_play_over_challenge():
    # ABS challenge (|WPA| 16) vs two real plays (10, 9) under a 120 s budget
    def edl_():
        mk = lambda ab, d, a, h: {"atBatIndex": ab, "eventIndex": 0, "dur": d, "abs": a, "headline": h, "anchor": h}
        return [mk(1, 60, False, "play A"), mk(2, 50, True, "ABS challenge"), mk(3, 55, False, "play B")]
    wp = [{"about": {"atBatIndex": 1}, "homeTeamWinProbabilityAdded": 10.0},
          {"about": {"atBatIndex": 2}, "homeTeamWinProbabilityAdded": -16.0},
          {"about": {"atBatIndex": 3}, "homeTeamWinProbabilityAdded": 9.0}]
    # weight 1 (old behaviour): the challenge is picked and play B, worth >= half its raw score, is left out
    old = [c["headline"] for c in reel2.rank(edl_(), wp, max_seconds=120, abs_weight=1.0)["clips"]]
    assert old == ["play A", "ABS challenge"]
    # weight 0.5 (ADR 0003): no challenge, both real plays, budget respected
    new = reel2.rank(edl_(), wp, max_seconds=120, abs_weight=0.5)["clips"]
    assert [c["headline"] for c in new] == ["play A", "play B"] and sum(c["dur"] for c in new) <= 120


@pytest.mark.parametrize("pk", PKS)
def test_abs_score_is_discounted_raw_kept(pk):
    for c in ranked(pk, abs_weight=0.5)["clips"]:
        assert c["score"] == round(c["wpa"] * (0.5 if c["abs"] else 1.0), 2)


@pytest.mark.parametrize("pk", PKS)
def test_abs_weight_small_ranks_every_abs_low(pk):
    order = ranked(pk, abs_weight=0.01)["clips"]
    assert all(c["score"] == round(c["wpa"] * 0.01, 2) for c in order if c["abs"])


# --- ABS off by default (ADR 0007) ------------------------------------------------------
@pytest.mark.parametrize("pk", PKS)
def test_default_has_no_abs_budgeted_or_not(pk):
    assert reel2.ABS_WEIGHT == 0
    for e in (edl(pk), ranked(pk), ranked(pk, max_seconds=120)):
        assert not any(c["abs"] for c in e["clips"])
    assert edl(pk)["clips"] == edl(pk, abs_clips=False)["clips"]  # weight 0 == --no-abs
    assert any(d["why"] == "abs-off" for d in edl(pk)["dropped"])  # every fixture has a challenge; it is reported, not hidden


@pytest.mark.parametrize("pk", PKS)
def test_positive_weight_restores_abs(pk):
    assert any(c["abs"] for c in edl(pk, abs_weight=0.5)["clips"])
    assert any(c["abs"] for c in ranked(pk, abs_weight=1.0)["clips"])


def test_abs_weight_cli_flag():
    import subprocess
    out = subprocess.run([sys.executable, str(ROOT / "reel2.py"), "990003", "--fixtures", str(FIXTURES), "--plan-only",
                          "--max-seconds", "120", "--abs-weight", "1"], capture_output=True, text=True, check=True).stdout
    assert any(c["abs"] for c in json.loads(out)["clips"])


def test_cli_default_drops_abs_and_flag_restores():
    import subprocess
    run = lambda *a: json.loads(subprocess.run([sys.executable, str(ROOT / "reel2.py"), "990003", "--fixtures", str(FIXTURES),
                                                "--plan-only", *a], capture_output=True, text=True, check=True).stdout)["clips"]
    assert not any(c["abs"] for c in run()) and any(c["abs"] for c in run("--abs-weight", "0.5"))


# --- publish hygiene: bundled fixtures are synthetic, never MLB Advanced Media responses ----------------------------
def test_fixtures_are_synthetic_not_mlbam():
    for p in FIXTURES.rglob("*.json"):
        t = p.read_text()
        assert "MLB Advanced Media" not in t and "mlb.com" not in t and "mlbstatic" not in t, p
    for pk in PKS:
        c, f = load(pk)
        assert pk.startswith("99") and c["copyright"].startswith("SYNTHETIC")
        assert all(pb["url"].startswith("https://example.invalid/") for x in c["highlights"]["highlights"]["items"] for pb in x["playbacks"])


def test_synthetic_generator_is_reproducible(tmp_path):
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_synthetic.py"), "--out", str(tmp_path)], check=True, capture_output=True)
    for p in tmp_path.rglob("*.json"):
        assert p.read_text() == (FIXTURES / p.relative_to(tmp_path)).read_text(), p
