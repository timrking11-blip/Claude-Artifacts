"""scripts/data_candidate.py: a weekly run proposes a master; only the owner's merge accepts it.

Each test runs the real script against a local bare remote that has a default
branch and a data/store branch (data/master plus data/runs), with a stub `gh`
that keeps PRs and check runs in a JSON file. Pinned here: the accepted
master never moves before the owner's merge, a rejected or refused candidate
leaves it as it was, a re-run never recomputes, an unresolved earlier run
holds the next one, and writeback cannot run before acceptance.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "data_candidate.py"

STUB = r'''#!/usr/bin/env python3
import json, os, sys
state = json.load(open(os.environ["GH_STUB_STATE"]))
args = sys.argv[1:]
if args[:2] == ["pr", "list"]:
    print("\n".join(f"{n} {ref}" for n, ref in state["open"]))
elif args[0] == "api" and "/pulls/" in args[1]:
    pr = state["pulls"].get(args[1].rsplit("/", 1)[1])
    if pr is None:
        sys.exit(1)
    print(json.dumps(pr))
elif args[0] == "api" and "/check-runs" in args[1]:
    sha = args[1].split("/commits/")[1].split("/")[0]
    print(json.dumps({"check_runs": state["checks"].get(sha, [])}))
else:
    sys.exit(2)
'''

RUN = "1001"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def env(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(remote), str(seed))
    (seed / "README").write_text("r\n")
    (seed / "data").mkdir()
    (seed / "data" / "CHANGELOG.md").write_text("# log\n")
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "init")
    git(seed, "push", "-q", "origin", "HEAD:main")
    git(seed, "switch", "-q", "--orphan", "data/store")
    for f in ("README", "data/CHANGELOG.md"):          # git switch --orphan may leave them untracked
        (seed / f).unlink(missing_ok=True)
    (seed / "data" / "master").mkdir(parents=True)
    (seed / "data" / "master" / "contacts.json").write_text('{"v": 0}\n')
    (seed / "data" / "runs").mkdir()
    (seed / "data" / "runs" / "r1.json").write_text("{}\n")
    git(seed, "add", "data")
    git(seed, "commit", "-q", "-m", "store")
    git(seed, "push", "-q", "origin", "HEAD:refs/heads/data/store")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "gh").write_text(STUB)
    (bindir / "gh").chmod(0o755)
    state = tmp_path / "gh.json"
    state.write_text(json.dumps({"open": [], "pulls": {}, "checks": {}}))
    e = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "GH_STUB_STATE": str(state),
         "GITHUB_REPOSITORY": "o/r"}
    for k in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "DATA_STORE_BRANCH", "DATA_STORE_REMOTE"):
        e.pop(k, None)
    return {"tmp": tmp_path, "remote": remote, "env": e, "state": state, "seed": seed}


def checkout(env, name):
    """A fresh checkout of the default branch as actions/checkout makes it: one branch, depth 1, no other objects."""
    work = env["tmp"] / name
    if not work.exists():
        git(env["tmp"], "clone", "-q", "--no-local", "--depth", "1", "--single-branch", "-b", "main",
            f"file://{env['remote']}", str(work))
    return work


def run(env, work, *args):
    out = env["tmp"] / f"out-{os.urandom(4).hex()}"
    r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=work, env={**env["env"], "GITHUB_OUTPUT": str(out)},
                       capture_output=True, text=True)
    r.outputs = dict(l.split("=", 1) for l in out.read_text().splitlines()) if out.exists() else {}
    return r


def gh_set(env, **changes):
    s = json.loads(env["state"].read_text())
    for k, v in changes.items():
        s[k] = v
    env["state"].write_text(json.dumps(s))


def ref(env, branch):
    out = git(env["tmp"], "ls-remote", str(env["remote"]), f"refs/heads/{branch}")
    return out.split()[0] if out else None


def show(env, rev, path):
    return git(env["tmp"], "--git-dir", str(env["remote"]), "show", f"{rev}:{path}")


def record(env, run_id=RUN):
    return json.loads(show(env, "data/candidates", f"runs/{run_id}.json"))


def compute(env, work, master='{"v": 1}\n', run_id=RUN, writeback=False):
    """begin + a merge that writes the master and this run's changelog and run line, then persist."""
    r = run(env, work, "begin", "--run-id", run_id)
    assert r.returncode == 0, r.stdout + r.stderr
    (work / "data" / "master" / "contacts.json").write_text(master)
    (work / "data" / "CHANGELOG.md").write_text(f"# log\nrun {run_id}\n")
    (work / "data" / "runlog").mkdir(exist_ok=True)
    (work / "data" / "runlog" / f"rl_{run_id}.json").write_text("{}\n")
    p = run(env, work, "persist", "--run-id", run_id, "--attempt", "1", "--input-commit", r.outputs["input_commit"],
            *(["--writeback"] if writeback else []))
    assert p.returncode == 0, p.stdout + p.stderr
    return p.outputs["candidate_sha"]


def open_pr(env, work, number=7, run_id=RUN, green=True):
    """What open_data_pr.sh does: push the payload on the data branch; then the sync records the PR."""
    branch = f"data/weekly-sync-{run_id}"
    git(work, "switch", "-q", "-C", branch)
    git(work, "add", "-f", "data/CHANGELOG.md", "data/runlog")
    git(work, "commit", "-q", "-m", "data")
    git(work, "push", "-q", "-f", "origin", branch)
    head = git(work, "rev-parse", "HEAD")
    s = json.loads(env["state"].read_text())
    s["open"].append([number, branch])
    s["pulls"][str(number)] = {"number": number, "state": "open", "merged": False,
                               "head": {"ref": branch, "sha": head}}
    if green:
        s["checks"][head] = [{"id": 1, "name": "test", "conclusion": "success"},
                             {"id": 2, "name": "architecture", "conclusion": "success"}]
    env["state"].write_text(json.dumps(s))
    r = run(env, work, "record-pr", "--run-id", run_id, "--pr", str(number), "--head", head,
            "--status", "awaiting_owner_merge")
    assert r.returncode == 0, r.stdout + r.stderr
    return head


def owner_closes(env, number=7, merged=True, head=None):
    s = json.loads(env["state"].read_text())
    s["open"] = [o for o in s["open"] if o[0] != number]
    pr = s["pulls"][str(number)]
    pr["state"], pr["merged"] = "closed", merged
    if head:
        pr["head"]["sha"] = head
    env["state"].write_text(json.dumps(s))


def close(env, number=7):
    """The Promote data workflow: a fresh runner, which has none of the sync runner's objects."""
    return run(env, checkout(env, f"promote-{os.urandom(4).hex()}"), "close", "--pr", str(number))


def accepted_master(env):
    return show(env, "data/store", "data/master/contacts.json")


# --- persist: the accepted master does not move ------------------------------

def test_the_script_parses():
    subprocess.run([sys.executable, "-m", "py_compile", str(SCRIPT)], check=True)


def test_a_run_persists_an_immutable_candidate_and_leaves_data_store_alone(env):
    store = ref(env, "data/store")
    work = checkout(env, "w1")
    sha = compute(env, work)
    assert ref(env, "data/store") == store and accepted_master(env) == '{"v": 0}'
    assert ref(env, f"data/candidate-{RUN}") == sha
    assert git(env["tmp"], "--git-dir", str(env["remote"]), "rev-parse", f"{sha}^") == store
    assert show(env, sha, "data/master/contacts.json") == '{"v": 1}'
    rec = record(env)
    assert rec["state"] == "persisted" and rec["candidate_sha"] == sha and rec["input_commit"] == store
    assert rec["master_changed"] is True and rec["attempt"] == 1


def test_opening_the_data_pr_does_not_advance_data_store(env):
    store = ref(env, "data/store")
    work = checkout(env, "w1")
    compute(env, work)
    head = open_pr(env, work)
    assert ref(env, "data/store") == store
    rec = record(env)
    assert rec["state"] == "awaiting_owner_merge" and rec["pr"] == 7 and rec["pr_head"] == head


def test_a_candidate_is_never_replaced(env):
    work = checkout(env, "w1")
    sha = compute(env, work)
    (work / "data" / "master" / "contacts.json").write_text('{"v": 99}\n')
    r = run(env, work, "persist", "--run-id", RUN, "--input-commit", ref(env, "data/store"))
    assert r.returncode == 5 and "re-run resumes it" in r.stdout
    assert ref(env, f"data/candidate-{RUN}") == sha


# --- re-run: resume, never recompute -----------------------------------------

def test_a_rerun_resumes_the_candidate_and_never_recomputes(env):
    sha = compute(env, checkout(env, "w1"))
    work = checkout(env, "w2")                      # a new runner for attempt 2
    pre = run(env, work, "preflight", "--run-id", RUN)
    assert pre.returncode == 0 and pre.outputs["resume"] == "true"   # the pulls are skipped
    r = run(env, work, "begin", "--run-id", RUN)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.outputs["resume"] == "true" and r.outputs["done"] == "false" and r.outputs["candidate_sha"] == sha
    # the candidate's files, not a recomputation from the accepted master
    assert (work / "data" / "master" / "contacts.json").read_text() == '{"v": 1}\n'
    assert (work / "data" / "runlog" / f"rl_{RUN}.json").exists()


def test_a_rerun_after_promotion_does_nothing_more(env):
    work = checkout(env, "w1")
    compute(env, work)
    open_pr(env, work)
    owner_closes(env)
    assert close(env).returncode == 0
    store = ref(env, "data/store")
    r = run(env, checkout(env, "w2"), "begin", "--run-id", RUN)
    assert r.outputs["resume"] == "true" and r.outputs["done"] == "true"
    assert ref(env, "data/store") == store


def test_a_rerun_refuses_a_moved_candidate_branch(env):
    compute(env, checkout(env, "w1"))
    git(env["tmp"], "--git-dir", str(env["remote"]), "update-ref", f"refs/heads/data/candidate-{RUN}",
        ref(env, "main"))
    r = run(env, checkout(env, "w2"), "begin", "--run-id", RUN)
    assert r.returncode == 5 and "refusing to resume" in r.stdout


# --- hold: an unresolved earlier run stops the next ----------------------------

def test_an_unresolved_earlier_candidate_holds_the_next_sync(env):
    compute(env, checkout(env, "w1"))
    r = run(env, checkout(env, "w2"), "preflight", "--run-id", "1002")
    assert r.returncode == 3 and "HELD" in r.stdout and f"run {RUN}: candidate persisted, no PR" in r.stdout
    assert "resume" not in r.outputs


def test_an_open_data_pr_from_another_run_holds_the_next_sync(env):
    gh_set(env, open=[[5, "data/writeback-900"]])
    r = run(env, checkout(env, "w1"), "preflight", "--run-id", "1002")
    assert r.returncode == 3 and "PR #5 (data/writeback-900) is open" in r.stdout


def test_a_runs_own_pr_and_unrelated_prs_do_not_hold_it(env):
    gh_set(env, open=[[5, f"data/weekly-sync-{RUN}"], [6, "claude/feature"]])
    r = run(env, checkout(env, "w1"), "preflight", "--run-id", RUN)
    assert r.returncode == 0 and r.outputs["resume"] == "false"


def test_resolved_runs_do_not_hold(env):
    work = checkout(env, "w1")
    compute(env, work)
    open_pr(env, work)
    owner_closes(env, merged=False)
    assert close(env).returncode == 0
    assert run(env, checkout(env, "w2"), "preflight", "--run-id", "1002").returncode == 0


# --- the owner's merge promotes; anything else leaves data/store alone ---------

def test_the_owners_merge_promotes_exactly_the_candidate(env):
    work = checkout(env, "w1")
    sha = compute(env, work)
    open_pr(env, work)
    owner_closes(env)
    r = close(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.outputs["writeback"] == "false" and r.outputs["run_id"] == RUN
    assert accepted_master(env) == '{"v": 1}'
    assert show(env, "data/store", "data/runs/r1.json") == "{}"          # the rest of data/store kept
    rec = record(env)
    assert rec["state"] == "promoted" and rec["accepted_commit"] == ref(env, "data/store")
    tree = git(env["tmp"], "--git-dir", str(env["remote"]), "rev-parse", "data/store:data/master")
    assert tree == rec["candidate_master_tree"] == git(env["tmp"], "--git-dir", str(env["remote"]),
                                                       "rev-parse", f"{sha}:data/master")


def test_promotion_is_idempotent(env):
    work = checkout(env, "w1")
    compute(env, work)
    open_pr(env, work)
    owner_closes(env)
    assert close(env).returncode == 0
    store = ref(env, "data/store")
    r = close(env)
    assert r.returncode == 0 and "already promoted" in r.stdout and ref(env, "data/store") == store


def test_a_rejected_candidate_does_not_change_the_accepted_master(env):
    store = ref(env, "data/store")
    work = checkout(env, "w1")
    compute(env, work)
    open_pr(env, work)
    owner_closes(env, merged=False)
    r = close(env)
    assert r.returncode == 0 and "rejected" in r.stdout
    assert ref(env, "data/store") == store and accepted_master(env) == '{"v": 0}'
    assert record(env)["state"] == "rejected"


def test_an_open_pr_promotes_nothing(env):
    store = ref(env, "data/store")
    work = checkout(env, "w1")
    compute(env, work)
    open_pr(env, work)
    r = close(env)
    assert r.returncode == 6 and ref(env, "data/store") == store


def test_a_merge_of_a_different_head_is_refused(env):
    store = ref(env, "data/store")
    work = checkout(env, "w1")
    compute(env, work)
    open_pr(env, work)
    owner_closes(env, head="f" * 40)
    r = close(env)
    assert r.returncode == 10 and "not the recorded head" in r.stdout
    assert ref(env, "data/store") == store and record(env)["state"] == "promotion_refused"


def test_a_merge_without_green_ci_on_the_exact_head_is_refused(env):
    store = ref(env, "data/store")
    work = checkout(env, "w1")
    compute(env, work)
    head = open_pr(env, work, green=False)
    gh_set(env, checks={head: [{"id": 1, "name": "test", "conclusion": "success"},
                               {"id": 2, "name": "architecture", "conclusion": "failure"}]})
    owner_closes(env)
    r = close(env)
    assert r.returncode == 10 and "architecture failure" in r.stdout
    assert ref(env, "data/store") == store


def test_a_merge_the_sync_never_recorded_is_refused(env):
    store = ref(env, "data/store")
    work = checkout(env, "w1")
    compute(env, work)                                # PR creation or CI dispatch failed: no record-pr
    branch = f"data/weekly-sync-{RUN}"
    gh_set(env, pulls={"7": {"number": 7, "state": "closed", "merged": True, "head": {"ref": branch, "sha": "a" * 40}}})
    r = close(env)
    assert r.returncode == 10 and ref(env, "data/store") == store


def test_a_moved_accepted_master_makes_the_candidate_stale_not_promoted(env):
    work = checkout(env, "w1")
    compute(env, work)
    open_pr(env, work)
    seed = env["seed"]                                 # someone else changed the accepted master
    (seed / "data" / "master" / "contacts.json").write_text('{"v": 5}\n')
    git(seed, "commit", "-qam", "other")
    git(seed, "push", "-q", "origin", "HEAD:refs/heads/data/store")
    owner_closes(env)
    r = close(env)
    assert r.returncode == 8 and accepted_master(env) == '{"v": 5}' and record(env)["state"] == "stale"


def test_promotion_keeps_composition_data_written_meanwhile(env):
    work = checkout(env, "w1")
    compute(env, work)
    open_pr(env, work)
    seed = env["seed"]
    (seed / "data" / "runs" / "r2.json").write_text("{}\n")
    git(seed, "add", "data/runs")
    git(seed, "commit", "-qm", "composition run")
    git(seed, "push", "-q", "origin", "HEAD:refs/heads/data/store")
    owner_closes(env)
    assert close(env).returncode == 0
    assert accepted_master(env) == '{"v": 1}' and show(env, "data/store", "data/runs/r2.json") == "{}"


def test_a_pr_head_with_other_data_than_the_candidate_is_not_recorded(env):
    work = checkout(env, "w1")
    compute(env, work)
    (work / "data" / "CHANGELOG.md").write_text("tampered\n")
    branch = f"data/weekly-sync-{RUN}"
    git(work, "switch", "-q", "-C", branch)
    git(work, "add", "-f", "data/CHANGELOG.md", "data/runlog")
    git(work, "commit", "-q", "-m", "data")
    r = run(env, work, "record-pr", "--run-id", RUN, "--pr", "7", "--head", git(work, "rev-parse", "HEAD"),
            "--status", "awaiting_owner_merge")
    assert r.returncode == 7 and record(env)["state"] == "persisted"


def test_no_data_change_and_no_pr_resolves_without_touching_data_store(env):
    store = ref(env, "data/store")
    work = checkout(env, "w1")
    compute(env, work, master='{"v": 0}\n')
    assert run(env, work, "record-pr", "--run-id", RUN).returncode == 0
    assert record(env)["state"] == "no_change" and ref(env, "data/store") == store


def test_a_changed_master_without_a_pr_fails(env):
    work = checkout(env, "w1")
    compute(env, work)
    r = run(env, work, "record-pr", "--run-id", RUN)
    assert r.returncode == 6 and record(env)["state"] == "persisted"


def test_the_owner_can_reject_a_candidate_with_no_pr_but_not_one_with_an_open_pr(env):
    work = checkout(env, "w1")
    compute(env, work)
    assert run(env, work, "reject", "--run-id", RUN).returncode == 0
    assert record(env)["state"] == "rejected"
    compute(env, work, run_id="1002")
    git(work, "switch", "-q", "main")
    open_pr(env, work, number=8, run_id="1002")
    r = run(env, work, "reject", "--run-id", "1002")
    assert r.returncode == 6 and "close it instead" in r.stdout


# --- writeback only after acceptance --------------------------------------------

def test_writeback_cannot_run_before_acceptance(env):
    work = checkout(env, "w1")
    compute(env, work, writeback=True)
    r = run(env, work, "writeback-gate", "--run-id", RUN)
    assert r.returncode == 9 and "only after the owner's merge" in r.stdout
    open_pr(env, work)
    assert run(env, work, "writeback-gate", "--run-id", RUN).returncode == 9
    owner_closes(env)
    c = close(env)
    assert c.returncode == 0 and c.outputs["writeback"] == "true"
    w = checkout(env, "w2")
    assert run(env, w, "writeback-gate", "--run-id", RUN).returncode == 0
    assert (w / "data" / "master" / "contacts.json").read_text() == '{"v": 1}\n'
    assert run(env, w, "mark-writeback", "--run-id", RUN, "--result", "success").returncode == 0
    assert record(env)["writeback"] == "done" and record(env)["state"] == "promoted"


def test_a_rejected_candidate_never_writes_back(env):
    work = checkout(env, "w1")
    compute(env, work, writeback=True)
    open_pr(env, work)
    owner_closes(env, merged=False)
    c = close(env)
    assert c.outputs["writeback"] == "false"
    assert run(env, work, "writeback-gate", "--run-id", RUN).returncode == 9


# --- the three states -------------------------------------------------------------

def test_status_reports_master_data_pr_and_crm_reconciliation_separately(env):
    work = checkout(env, "w1")
    compute(env, work)
    open_pr(env, work)
    r = run(env, work, "status", "--run-id", RUN)
    assert "**master:**" in r.stdout and "unchanged" in r.stdout and "awaiting the owner's merge" in r.stdout
    assert "**data PR:** #7" in r.stdout and "expected_sha" in r.stdout
    assert "**CRM reconciliation:** not started" in r.stdout
    owner_closes(env)
    close(env)
    r = run(env, work, "status", "--pr", "7")
    assert "promoted" in r.stdout and "merged by the owner" in r.stdout and "CRM reconciliation:** pending" in r.stdout
