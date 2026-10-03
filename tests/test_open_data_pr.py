"""scripts/open_data_pr.sh: the only way automated data reaches the default branch.

Each test runs the real script against a local bare remote, with a stub `gh`
that keeps PRs in a JSON file. It pins the controls the live run cannot prove:
data-only commits, re-runs that resume instead of colliding, a run that fails
when its PR is not queued to land, and the stacked-PR dependency written down.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "open_data_pr.sh"

STUB = r'''#!/usr/bin/env python3
import json, os, sys
state_path = os.environ["GH_STUB_STATE"]
state = json.load(open(state_path))
args = sys.argv[1:]
state["calls"].append(args)
def opt(name):
    return args[args.index(name) + 1] if name in args else None
out, code = "", 0
if args[:2] == ["pr", "list"]:
    prs = [p for p in state["prs"] if p["head"] == opt("--head")]
    if "number,state" in args:
        out = f'{prs[0]["number"]} {prs[0]["state"]}' if prs else "null null"
    else:
        out = str(prs[0]["number"]) if prs else ""
elif args[:2] == ["pr", "create"]:
    n = 100 + len(state["prs"])
    state["prs"].append({"number": n, "head": opt("--head"), "state": "OPEN", "body": opt("--body")})
    out = f"https://github.com/o/r/pull/{n}"
elif args[:2] == ["pr", "merge"]:
    code = 1 if os.environ.get("GH_STUB_MERGE_FAIL") else 0
json.dump(state, open(state_path, "w"))
if out:
    print(out)
sys.exit(code)
'''


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def env(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(remote), str(seed))
    (seed / "data").mkdir()
    (seed / "data" / "master.json").write_text("{}\n")
    (seed / "README").write_text("r\n")
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "init")
    git(seed, "push", "-q", "origin", "HEAD:main")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "gh").write_text(STUB)
    (bindir / "gh").chmod(0o755)
    state = tmp_path / "gh.json"
    state.write_text(json.dumps({"prs": [], "calls": []}))
    e = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "GH_STUB_STATE": str(state),
         "BASE_BRANCH": "main", "GITHUB_RUN_ID": "42", "GITHUB_OUTPUT": str(tmp_path / "out")}
    e.pop("GH_STUB_MERGE_FAIL", None)
    return {"tmp": tmp_path, "remote": remote, "env": e, "state": state}


def runner(env, name, data='{"a": 1}\n'):
    """A fresh checkout of the default branch, as a new Actions runner sees it, with new data written."""
    work = env["tmp"] / name
    git(env["tmp"], "clone", "-q", str(env["remote"]), str(work))
    (work / "data" / "master.json").write_text(data)
    return work


def run(env, work, *paths, branch="data/weekly-sync-42", extra=None):
    e = {**env["env"], **(extra or {})}
    return subprocess.run(["bash", str(SCRIPT), branch, "chore(crm): weekly sync", *(paths or ("data",))],
                          cwd=work, env=e, capture_output=True, text=True)


def gh_state(env):
    return json.loads(env["state"].read_text())


def remote_sha(env, branch="data/weekly-sync-42"):
    out = git(env["tmp"], "ls-remote", "--heads", str(env["remote"]), branch)
    return out.split()[0] if out else None


def test_the_script_parses():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_happy_path_pushes_the_branch_opens_a_pr_dispatches_ci_and_queues_auto_merge(env):
    r = run(env, runner(env, "w1"))
    assert r.returncode == 0, r.stderr + r.stdout
    calls = gh_state(env)["calls"]
    assert ["workflow", "run", "python-ci.yml", "--ref", "data/weekly-sync-42"] in calls
    assert ["pr", "merge", "100", "--auto", "--merge"] in calls
    assert remote_sha(env) and (env["tmp"] / "out").read_text().splitlines() == ["branch=data/weekly-sync-42", "pr=100"]


def test_no_data_change_opens_nothing(env):
    work = runner(env, "w1", data="{}\n")
    r = run(env, work)
    assert r.returncode == 0 and "No data changes" in r.stdout
    assert gh_state(env)["calls"] == [] and remote_sha(env) is None


def test_a_file_outside_the_data_paths_never_rides_along(env):
    work = runner(env, "w1")
    (work / "README").write_text("changed\n")
    git(work, "add", "README")
    r = run(env, work)
    assert r.returncode == 3 and "outside the data paths" in r.stdout + r.stderr
    assert remote_sha(env) is None and gh_state(env)["calls"] == []


def test_a_rerun_resumes_the_branch_and_reuses_the_open_pr(env):
    assert run(env, runner(env, "w1")).returncode == 0
    first = remote_sha(env)
    r = run(env, runner(env, "w2"), extra={"GITHUB_RUN_ATTEMPT": "2"})
    assert r.returncode == 0, r.stderr + r.stdout
    assert "Resuming" in r.stdout and "Reusing open PR #100" in r.stdout
    assert remote_sha(env) == first
    assert len(gh_state(env)["prs"]) == 1


def test_a_rerun_with_different_data_replaces_the_branch_under_the_same_pr(env):
    assert run(env, runner(env, "w1")).returncode == 0
    first = remote_sha(env)
    r = run(env, runner(env, "w2", data='{"a": 2}\n'), extra={"GITHUB_RUN_ATTEMPT": "2"})
    assert r.returncode == 0, r.stderr + r.stdout
    assert remote_sha(env) != first and len(gh_state(env)["prs"]) == 1


def test_a_rerun_after_the_pr_merged_does_nothing_more(env):
    assert run(env, runner(env, "w1")).returncode == 0
    s = gh_state(env); s["prs"][0]["state"] = "MERGED"; s["calls"] = []; env["state"].write_text(json.dumps(s))
    r = run(env, runner(env, "w2"))
    assert r.returncode == 0 and "already merged" in r.stdout
    assert [c[:2] for c in gh_state(env)["calls"]] == [["pr", "list"]]


def test_a_rerun_never_reopens_a_pr_the_owner_closed(env):
    assert run(env, runner(env, "w1")).returncode == 0
    s = gh_state(env); s["prs"][0]["state"] = "CLOSED"; env["state"].write_text(json.dumps(s))
    r = run(env, runner(env, "w2"))
    assert r.returncode == 4 and len(gh_state(env)["prs"]) == 1


def test_a_run_whose_pr_cannot_be_queued_fails(env):
    r = run(env, runner(env, "w1"), extra={"GH_STUB_MERGE_FAIL": "1"})
    assert r.returncode == 5 and "will not land" in r.stdout + r.stderr


def test_a_stacked_pr_names_its_dependency(env):
    s = gh_state(env); s["prs"].append({"number": 7, "head": "data/weekly-sync-42", "state": "OPEN", "body": ""})
    env["state"].write_text(json.dumps(s))
    r = run(env, runner(env, "w1"), branch="data/writeback-42",
            extra={"STACKED_ON": "data/weekly-sync-42"})
    assert r.returncode == 0, r.stderr + r.stdout
    body = gh_state(env)["prs"][-1]["body"]
    assert "Stacked on #7 (`data/weekly-sync-42`)" in body and "also carries its commits" in body
