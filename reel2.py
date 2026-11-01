#!/usr/bin/env python3
"""Convenience entry point: `python3 reel2.py ...` from the repo root.
The cutter itself is vendored in skills/clip-cutter/scripts/reel2.py so the skill folder is self-contained."""
import os, runpy, sys

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills", "clip-cutter", "scripts", "reel2.py")
if __name__ == "__main__":
    sys.argv[0] = SCRIPT
    runpy.run_path(SCRIPT, run_name="__main__")
