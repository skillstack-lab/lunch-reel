#!/usr/bin/env python3
"""Envelope: run a command for a named cut, time it, append one JSON line to runs.jsonl, pass through its exit code.

usage: python3 tools/envelope.py CUT [--notes TEXT] [--tokens-in N] [--tokens-out N] [--model M] [--max-wall S] -- CMD...
  --max-wall S : fail closed (exit 124 recorded as over_envelope) if the command runs longer than S seconds
Token fields are optional/blank until a forge (Claude) reports usage. runs.jsonl is local burn tracking, never shared.
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone

LOG = os.environ.get("ENVELOPE_LOG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs.jsonl"))


def main(argv):
    if "--" not in argv or not argv or argv[0].startswith("-"): print(__doc__); return 2
    head, cmd = argv[:argv.index("--")], argv[argv.index("--") + 1:]
    cut, opts = head[0], dict(zip(head[1::2], head[2::2]))
    max_wall = float(opts["--max-wall"]) if "--max-wall" in opts else None
    t0, over = time.monotonic(), False
    try:
        rc = subprocess.run(cmd, timeout=max_wall).returncode
    except subprocess.TimeoutExpired:
        rc, over = 124, True
    wall = round(time.monotonic() - t0, 3)
    num = lambda k: int(opts[k]) if k in opts else None
    rec = {"ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "cut": cut, "cmd": " ".join(cmd),
           "exit": rc, "ok": rc == 0, "wall_s": wall, "max_wall_s": max_wall, "over_envelope": over,
           "tokens_in": num("--tokens-in"), "tokens_out": num("--tokens-out"), "model": opts.get("--model"),
           "notes": opts.get("--notes", "")}
    with open(LOG, "a") as f: f.write(json.dumps(rec) + "\n")
    print(f"[envelope] {cut}: exit={rc} wall={wall}s{' OVER' if over else ''} -> {os.path.relpath(LOG)}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
