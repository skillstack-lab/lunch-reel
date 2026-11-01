import json, pathlib, subprocess, sys
ENV = pathlib.Path(__file__).resolve().parents[1] / "tools" / "envelope.py"


def run(tmp_path, *args):
    log = tmp_path / "runs.jsonl"
    rc = subprocess.run([sys.executable, str(ENV), *args], env={"ENVELOPE_LOG": str(log), "PATH": "/usr/bin:/bin"},
                        capture_output=True).returncode
    return rc, [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


def test_records_success(tmp_path):
    rc, recs = run(tmp_path, "demo", "--notes", "hi", "--tokens-in", "10", "--", "true")
    assert rc == 0 and recs[-1]["ok"] and recs[-1]["cut"] == "demo" and recs[-1]["tokens_in"] == 10 and recs[-1]["notes"] == "hi"


def test_passes_failure_through(tmp_path):
    rc, recs = run(tmp_path, "demo", "--", "false")
    assert rc == 1 and recs[-1]["ok"] is False and recs[-1]["tokens_out"] is None


def test_fails_closed_over_wall(tmp_path):
    rc, recs = run(tmp_path, "slow", "--max-wall", "0.2", "--", "sleep", "2")
    assert rc == 124 and recs[-1]["over_envelope"] and recs[-1]["wall_s"] < 2
