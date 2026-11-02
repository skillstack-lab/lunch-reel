# Lunch Reel: a catch-up MLB reel you build yourself, from a skill

[![AgentHub](https://agenthub.nullorder.org/badge.svg)](https://agenthub.nullorder.org)

**Offer:** An Agent Skill you can copy (Claude Code, Grok Bot, or plain bash) that turns one finished MLB game, a whole day's games, or one team's games into a spoiler-free catch-up plan in game order. It ranks plays by win-probability swing and fits them to a time budget. You render the reel on your own machine, for your own private viewing.

**Who it's for first:** people who build skills and agents and want a working, tested "find what mattered → cut → stitch" skill to read, fork, and reuse. Baseball fans who missed a game come second.

## What it does
- Pulls MLB's public play-by-play, win probability, and per-play highlight listings from `statsapi.mlb.com`
- Leaves out talk, recaps, repeat angles, and (by default) replay-challenge clips
- Ties each clip to the pitch it shows, so the reel plays in real game order
- Ranks by how much each at-bat swung win probability, then fills a `--max-seconds` or `--top N` budget
- Lists big swings MLB never clipped (`missed_hot`) and gives a reason for every clip it dropped
- `--plan-only` downloads no video at all. It prints a JSON plan that links to MLB's own hosted clips.
- Optional rendering (ffmpeg) burns in a spoiler-free score label, and the reel stays in your local `out/` folder

## Rights: read before you use it
- **We ship the cutter, never the clips.** This repo has no video, no reels, and no MLB media. Tests enforce that.
- **Private viewing only.** MLB's terms of use forbid redistributing compilations of its content. Don't upload, post, stream, or share a rendered reel. You're responsible for how you use MLB data and media.
- Not affiliated with, endorsed by, or sponsored by MLB or MLB Advanced Media. "MLB" and team names are their owners' trademarks and are used here only to describe the data source.
- Data comes live from MLB's public API, under MLB Advanced Media's copyright notice (non-commercial, individual use). This repo bundles **no** raw MLB API responses: the test fixtures in `fixtures/` are synthetic (made-up games, players, and numbers from `tools/make_synthetic.py`).

## Install
```bash
git clone https://github.com/skillstack-lab/lunch-reel && cd lunch-reel
python3 --version        # 3.10+ (stdlib only)
# plan-only needs nothing else. Rendering needs ffmpeg + ffprobe + curl.
```
**Claude Code plugin (one command):**
```bash
claude plugin install lunch-reel --marketplace skillstack-lab/lunch-reel
```
Or add then install: `claude plugin marketplace add skillstack-lab/lunch-reel` → `claude plugin install lunch-reel@skillstack-lab`. Then ask for a catch-up (skill: `/lunch-reel:clip-cutter`).

**As a Claude Code / Agent Skills skill (manual):** copy or link `skills/clip-cutter/` into your skills directory. The cutter (`scripts/reel2.py`) is vendored inside the skill folder, so it works on its own. `cache/` and `out/` go to `$CLIP_CUTTER_HOME` if set, else the repo root (when run in place), else `~/.cache/clip-cutter`.
**As a CLI:** `skills/clip-cutter/scripts/clip-cutter <gamePk> --plan-only --max-seconds 300` (or `python3 reel2.py ...` from the repo root)
**Grok Bot:** clone or point a skill at `skills/clip-cutter/`. Feedback: ssdesk+clip@mail.grokbot.com.

## 60-second try (no video downloaded)
```bash
skills/clip-cutter/scripts/clip-cutter 824705 --plan-only --max-seconds 120
```
You get the top plays of a September 2026 game in game order, as JSON. Then try your team on a date:
```bash
skills/clip-cutter/scripts/clip-cutter --date 2026-09-27 --team CHC --plan-only --max-seconds 300
```
Find a gamePk with `https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD`.

**Offline (no network):** `skills/clip-cutter/scripts/clip-cutter 990003 --fixtures fixtures --plan-only --max-seconds 120` runs on the synthetic fixtures.

## Develop
```bash
python3 -m pytest -q tests      # or: just check   (offline, synthetic fixtures, no video)
just synthetic                  # regenerate fixtures/ (tests check they match the generator)
just fixture <gamePk>           # real data into local-fixtures/ for YOUR machine only (gitignored)
```
Plan JSON field guide: `skills/clip-cutter/references/OUTPUT.md`. Skill instructions: `skills/clip-cutter/SKILL.md`.

## Feedback
- Email: **ssdesk+clip@mail.grokbot.com**. A bot reads this inbox, and every message gets read.
- GitHub Discussions on this repo (Ideas / Q&A / Show-and-tell) once they're turned on
- Please tell us what you tried, where it broke, and what you'd want it to cut next (another sport? another source?).

## License
MIT for the code (see `LICENSE`). The license covers the cutter only and grants no rights to MLB data, video, or trademarks.
