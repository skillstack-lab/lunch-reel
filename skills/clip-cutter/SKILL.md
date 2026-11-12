---
name: clip-cutter
description: Builds a private MLB catch-up reel from MLB's already-public per-play highlight clips, ordered by real game chronology and ranked by win-probability swing. Covers one game, a whole date's slate, or one team's games, with a time budget. Start with --plan-only and return the game-ordered plan; render a private local reel only when the user explicitly asks. Some highlight titles can reveal the result. Use when someone missed an MLB game and wants a short catch-up, asks for the biggest plays of a day or of their team, or wants to cut, rank, or stitch MLB highlights. Private viewing only; it ships the cutter, never the clips.
compatibility: Python 3.10+ (stdlib only), ffmpeg/ffprobe and curl for rendering, network access to statsapi.mlb.com and MLB clip CDNs (plan-only also runs offline on the bundled synthetic fixtures). Runs anywhere bash runs, e.g. Grok Bot, Claude Code, or a terminal.
license: MIT (code only; no rights to MLB data or media)
metadata:
  version: "1.9.0"
  entry: scripts/reel2.py
  rights: private-viewing-only
---

# Clip Cutter

Turns MLB's own per-play highlight clips into a lunch-break reel:
- filters out talk, recaps, and repeat angles
- orders clips by the real at-bat and pitch sequence
- ranks by how much each at-bat swung win probability
- burns in a scoreboard label with the score before the plate appearance (highlight titles can still reveal the result)

## Rights: read first
- **Private viewing only.** MLB's terms forbid redistributing compilations. Never upload, post, send, or share a rendered reel. Leave it in `out/` for the person who asked.
- **Ship the cutter, not the clips.** Public pages may link to MLB's own video pages; never host clip bytes.
- `--plan-only` downloads no video. In a chat catch-up, including "the 5-minute version" or "catch me up in 5 minutes", always run `--plan-only` first and answer from that plan. Only drop `--plan-only` when the user explicitly asks you to render or save a local video.
- Not affiliated with, endorsed by, or sponsored by MLB or MLB Advanced Media. Data comes live from MLB's public API for individual, non-commercial use.

## When to use
- "I missed the Cubs game, catch me up in 5 minutes" / "give me the 5-minute version": run the matching `--date`/`--team` (or gamePk) command with `--plan-only`, then list `inning: headline`. Do not render yet.
- "What were the biggest moments around MLB on Sept 25?": `--date` slate, plan-only
- "Make me a Yankees reel for yesterday": `--team NYY --date ...` with `--plan-only` first; render only if they then ask for a local video.
- Not for: live games, other sports, or anything that requires publishing video.

## Commands
Run via `scripts/clip-cutter`. The cutter (`scripts/reel2.py`, stdlib Python) is vendored in this folder, so the skill works on its own. The wrapper runs from a home directory where `cache/` and `out/` live: `$CLIP_CUTTER_HOME` if set, else the repo root when the skill sits at `<repo>/skills/clip-cutter`, else `~/.cache/clip-cutter`. You need a gamePk (from `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD`) or a date plus a team (abbreviation or MLB id; see `assets/teams.json`).

Live, plan-only (needs network to statsapi.mlb.com, downloads no video):

```text
scripts/clip-cutter 824705 --plan-only --max-seconds 120
scripts/clip-cutter --date 2026-09-27 --team CHC --plan-only --max-seconds 300
```

Offline examples. They run against the repo's **synthetic** fixtures (`fixtures/`, made-up games 99xxxx on 2099-04-01/02; no MLB data), and the skill's tests run every line:

```bash
scripts/clip-cutter 990003 --fixtures fixtures --plan-only
scripts/clip-cutter 990003 --fixtures fixtures --plan-only --max-seconds 120
scripts/clip-cutter 990004 --fixtures fixtures --plan-only --top 5 --abs-weight 0.5
scripts/clip-cutter --date 2099-04-01 --fixtures fixtures --plan-only --max-seconds 300
scripts/clip-cutter --date 2099-04-01 --team NYY --fixtures fixtures --plan-only --max-seconds 180
scripts/clip-cutter --date 2099-04-02 --team 112 --fixtures fixtures --plan-only --top 6 --against-weight 1
```

Live data: drop `--fixtures fixtures`. Render only when the user explicitly asks for a local video: drop `--plan-only`. That downloads only the clips it needs into `cache/<gamePk>/` and writes the reel:
- `out/reel_<pk>_hl.mp4` for a single game
- `out/slate_<date>.mp4` for a date
- `out/team_<ABBR>_<date>.mp4` for a team

## Flags
| Flag | Effect |
|---|---|
| `--max-seconds S` / `--top N` | Budget. Highest-scoring clips first (the #1 clip is always kept), then output in game order. Title cards (2.5 s each) count toward S. |
| `--date D` | Slate: every final game that day, ranked league-wide, grouped per game, games in start order (earlier game first). |
| `--team ABBR\|ID` (with `--date`) | That team's games only. Plays that hurt the team are scored ×`--against-weight` (default 0.75). |
| `--abs-weight W` | ABS challenge clips are **left out by default** (W=0; nobody wants a replay review at lunch). W>0 keeps them, scored ×W (0.5 = old default, 1 = no discount). |
| `--keep-unmapped` | Keep clips that can't be tied to a pitch (multi-play packages). Off by default. |
| `--no-labels` | No lower-third score or title cards. |
| `--plan-only` | Print the JSON plan; no video work. |

## Reading the output
`--plan-only` prints JSON (field guide: `references/OUTPUT.md`):
- `clips[]` is in play order. Each has a `headline`, `inning`, `dur`, `wpa` (raw at-bat swing), `score` (ranking key), `abs`, and the pre-at-bat score `pre`.
- `dropped[]` gives a reason for every excluded item.
- `missed_hot[]` lists big-swing at-bats that MLB never clipped.
- Slate and team plans add `games[]`, `skipped[]` (`no-data`, `status:Cancelled`, `no-game`, `no-playable-game`), and `total_seconds`.

Exit codes: 0 ok; 1 for a team with no playable game (nothing rendered); 2 for bad usage or a missing dependency.

When reporting to a person, list the clips as `inning: headline`. Mention anything in `missed_hot` or `skipped`. Give the local reel path and say it's for private viewing.

## Related
`references/OUTPUT.md` (plan JSON field guide), repo `README.md`, `just check` (tests), `tools/make_synthetic.py` (offline fixtures), `tools/make_fixture.py` (pull real data into a gitignored `local-fixtures/` for your own use only).
