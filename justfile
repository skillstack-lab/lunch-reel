# Lunch Reel / clip-cutter. `just check` exit 0 == green. Private viewing only.
set shell := ["bash", "-euo", "pipefail", "-c"]

default: check

# offline tests on SYNTHETIC fixtures (no network, no video, no MLB data)
check:
    python3 -m pytest -q tests

# same gate, timed + appended to runs.jsonl (local, gitignored). usage: just tracked-check "cut name" "notes"
tracked-check cut="manual" notes="":
    python3 tools/envelope.py "{{cut}}" --notes "{{notes}}" --max-wall 300 -- python3 -m pytest -q tests

# LIVE plan, no video: hottest plays of a real game under a budget. e.g. just live 824705 120
live pk="824705" s="120":
    python3 reel2.py {{pk}} --plan-only --max-seconds {{s}}

# LIVE team plan, no video. e.g. just live-team CHC 2026-09-27 300
live-team abbr="CHC" date="2026-09-27" s="300":
    python3 reel2.py --date {{date}} --team {{abbr}} --plan-only --max-seconds {{s}}

# offline plans on the synthetic fixtures
plan pk="990003":
    python3 reel2.py {{pk}} --fixtures fixtures --plan-only

top pk="990003" n="6" s="900":
    python3 reel2.py {{pk}} --fixtures fixtures --plan-only --top {{n}} --max-seconds {{s}}

slate date="2099-04-01" s="300":
    python3 reel2.py --date {{date}} --fixtures fixtures --plan-only --max-seconds {{s}}

team abbr="NYY" date="2099-04-01" s="180":
    python3 reel2.py --date {{date}} --team {{abbr}} --fixtures fixtures --plan-only --max-seconds {{s}}

# REAL private render of a live team reel (downloads MLB-hosted clips into cache/, writes out/). Never share the mp4.
render-team abbr="CHC" date="2026-09-27" s="300":
    python3 reel2.py --date {{date}} --team {{abbr}} --max-seconds {{s}}
    python3 -c "import subprocess,sys; d=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0','out/team_{{abbr}}_{{date}}.mp4'])); print('duration',d,'budget',{{s}}); sys.exit(0 if d <= {{s}} + 0.5 else 1)"

# regenerate the bundled synthetic fixtures (deterministic; tests check they match)
synthetic:
    python3 tools/make_synthetic.py

# pull REAL statsapi data for your own offline use into local-fixtures/ (gitignored; never commit it)
fixture pk:
    python3 tools/make_fixture.py {{pk}}

# validate the Agent Skills package (spec validator via uvx; offline checks are in tests/test_skill.py)
skill-validate:
    cd /tmp && uvx --from skills-ref agentskills validate {{justfile_directory()}}/skills/clip-cutter
    python3 -m pytest -q tests/test_skill.py
