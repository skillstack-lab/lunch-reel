"""Agent Skills packaging: valid frontmatter, every documented command runs, self-contained folder, no video bytes."""
import json, os, pathlib, re, shlex, subprocess, pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "clip-cutter"
MEDIA = {".mp4", ".m3u8", ".ts", ".mov", ".webm", ".mkv", ".m4a", ".aac", ".mp3"}


def frontmatter():
    text = (SKILL / "SKILL.md").read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "SKILL.md must start with --- frontmatter ---"
    fm, cur = {}, None
    for line in m.group(1).splitlines():
        if not line.strip(): continue
        if line.startswith("  ") and cur:  # one-level map (metadata)
            k, v = line.strip().split(":", 1); fm[cur][k.strip()] = v.strip().strip('"')
        else:
            k, v = line.split(":", 1); k, v = k.strip(), v.strip()
            fm[k] = {} if v == "" else v; cur = k if v == "" else None
    return fm, m.group(2)


def test_frontmatter_valid():
    fm, body = frontmatter()
    assert set(fm) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    n = fm["name"]
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", n) and len(n) <= 64 and n == SKILL.name
    assert 1 <= len(fm["description"]) <= 1024 and "Use when" in fm["description"]
    assert len(fm.get("compatibility", "x")) <= 500
    assert all(isinstance(v, str) for v in fm["metadata"].values())
    assert len(body.splitlines()) < 500


def test_body_covers_rights_and_pointers():
    _, body = frontmatter()
    for must in ("Private viewing only", "Ship the cutter, not the clips", "--plan-only", "--date", "--team",
                 "references/OUTPUT.md", "Not affiliated"):
        assert must in body, must


def commands():
    _, body = frontmatter()
    blocks = re.findall(r"```bash\n(.*?)```", body, re.S)
    return [l.strip() for b in blocks for l in b.splitlines() if l.strip().startswith("scripts/clip-cutter")]


def test_has_commands_for_each_mode():
    cmds = " ".join(commands())
    assert len(commands()) >= 5 and "--date" in cmds and "--team" in cmds and "--max-seconds" in cmds


@pytest.mark.parametrize("cmd", commands())
def test_documented_command_runs_plan_only(cmd, tmp_path):
    argv = shlex.split(cmd)
    assert "--plan-only" in argv and "--fixtures" in argv, "documented examples must be offline + plan-only"
    # run from an unrelated cwd to prove the wrapper sets its own
    r = subprocess.run([str(SKILL / argv[0]), *argv[1:]], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    plan = json.loads(r.stdout)
    assert plan["clips"], cmd
    assert not list(tmp_path.iterdir())  # nothing written to caller's cwd


def test_wrapper_bad_home_fails_cleanly(tmp_path):
    r = subprocess.run([str(SKILL / "scripts" / "clip-cutter"), "990003", "--plan-only"], capture_output=True, text=True,
                       env={**os.environ, "CLIP_CUTTER_HOME": str(tmp_path / "nope")})
    assert r.returncode == 2 and "CLIP_CUTTER_HOME" in r.stderr


def test_skill_folder_is_self_contained(tmp_path):
    # copy ONLY the skill folder elsewhere (marketplace-style install); it must still run with no repo-root reel2.py
    import shutil
    dst = tmp_path / "skills" / "clip-cutter"; shutil.copytree(SKILL, dst, ignore=shutil.ignore_patterns("__pycache__"))
    work = tmp_path / "work"; shutil.copytree(ROOT / "fixtures", work / "fixtures")
    r = subprocess.run([str(dst / "scripts" / "clip-cutter"), "990003", "--fixtures", "fixtures", "--plan-only", "--max-seconds", "60"],
                       capture_output=True, text=True, timeout=60, env={**os.environ, "CLIP_CUTTER_HOME": str(work)})
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["seconds"] <= 60
    assert not [p for p in dst.rglob("*") if p.name in ("cache", "out", "__pycache__")]  # skill folder stays read-only


def test_team_lookup_uses_skill_assets_offline(tmp_path):
    import sys; sys.path.insert(0, str(SKILL / "scripts")); import reel2
    os.environ["CLIP_CUTTER_TEAMS"] = str(SKILL / "assets" / "teams.json")
    try:
        assert reel2.resolve_team("ATH", reel2.load_teams(str(tmp_path)))["id"] == 133  # no teams.json in tmp -> asset
    finally:
        del os.environ["CLIP_CUTTER_TEAMS"]
    assert json.loads((SKILL / "assets" / "teams.json").read_text()) == json.loads((ROOT / "fixtures" / "teams.json").read_text())


def test_no_video_or_symlinks_in_skill():
    files = list(SKILL.rglob("*"))
    assert not [p for p in files if p.suffix.lower() in MEDIA]
    assert not [p for p in files if p.is_symlink()]  # skills get zipped/copied; symlinks break
    assert sum(p.stat().st_size for p in files if p.is_file()) < 200_000
