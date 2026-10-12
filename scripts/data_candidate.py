#!/usr/bin/env python3
"""The weekly sync's candidate lifecycle: a run proposes a master, the owner accepts it.

`data/store` holds the accepted master only. A weekly run never writes it.
Instead it persists an immutable candidate and opens a data PR, and the
owner's merge of that PR is what promotes the candidate (decided 12 Oct 2026):

  accepted master -> compute -> validate -> candidate persisted -> data PR +
  exact-head CI -> OWNER MERGE -> promote -> accepted master -> optional Apollo
  writeback -> CRM reconciliation (the Monday enrichment push)

Git holds all of it, beside the data branch:

- `data/candidate-<run_id>`: one commit, created once and never moved. Its
  parent is the data/store commit the run started from; its tree is what the
  run produced (data/master, data/CHANGELOG.md, data/runlog).
- `data/candidates`: the ledger, one `runs/<run_id>.json` per weekly run with
  run_id, attempt, input commit and master tree, candidate SHA and master
  tree, PR number, branch and head SHA, state and history. Every write is a
  compare-and-swap push.

States: persisted and awaiting_owner_merge are unresolved, and a new weekly
run HOLDS while any other run's candidate (or any other weekly or writeback
data PR) is unresolved. promoted, rejected, no_change, stale and
promotion_refused are final; only promoted changes data/store.

Commands (each run from a checkout of the default branch):
  preflight --run-id R    HOLD (exit 3) on another unresolved run; resume=true if R has a candidate
  begin --run-id R        restore the accepted master, or R's candidate (a re-run never recomputes)
  persist --run-id R --attempt A --input-commit C [--writeback]
  record-pr --run-id R --pr N --head SHA --status awaiting_owner_merge|merged
  close --pr N            the PR closed: merged -> promote (exact head, green CI, CAS); else reject
  reject --run-id R       reject a candidate whose PR never opened or is closed
  writeback-gate --run-id R   exit 9 unless R is promoted and data/store holds its master
  mark-writeback --run-id R --result success|failure|cancelled|skipped
  status --run-id R | --pr N  the three states: master, data PR, CRM reconciliation

Environment: GITHUB_REPOSITORY and GH_TOKEN for `gh`; DATA_STORE_REMOTE
(default origin); GITHUB_OUTPUT and GITHUB_STEP_SUMMARY when present.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REMOTE = os.environ.get("DATA_STORE_REMOTE", "origin")
STORE = os.environ.get("DATA_STORE_BRANCH", "data/store")
LEDGER = "data/candidates"
CANDIDATE = "data/candidate-{}"
MASTER = "data/master"
PAYLOAD = ("data/CHANGELOG.md", "data/runlog")
UNRESOLVED = ("persisted", "awaiting_owner_merge")
FINAL = ("promoted", "rejected", "no_change", "stale", "promotion_refused")
DATA_PR = re.compile(r"^data/(weekly-sync|writeback)-(\d+)$")
REQUIRED_CHECKS = ("test", "architecture")
BOT = {"GIT_AUTHOR_NAME": "crm-sync[bot]", "GIT_AUTHOR_EMAIL": "crm-sync[bot]@users.noreply.github.com",
       "GIT_COMMITTER_NAME": "crm-sync[bot]", "GIT_COMMITTER_EMAIL": "crm-sync[bot]@users.noreply.github.com"}


class Stop(Exception):
    """Ends the command with an exit code and a message, after nothing further was written."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


# --- git and gh ------------------------------------------------------------

def git(*args: str, stdin: str | None = None, env: dict | None = None, check: bool = True) -> str:
    r = subprocess.run(["git", *args], input=stdin, capture_output=True, text=True,
                       env={**os.environ, **BOT, **(env or {})})
    if check and r.returncode:
        raise Stop(1, f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def fetch(branch: str) -> str | None:
    """The remote branch's head, freshly fetched; None if it does not exist."""
    r = subprocess.run(["git", "fetch", "-q", REMOTE, f"+refs/heads/{branch}:refs/remotes/{REMOTE}/{branch}"],
                       capture_output=True, text=True)
    if r.returncode:
        return None
    return git("rev-parse", f"refs/remotes/{REMOTE}/{branch}")


def tree(rev: str, path: str) -> str | None:
    return git("rev-parse", "-q", "--verify", f"{rev}:{path}", check=False) or None


def push(sha: str, branch: str, expect: str | None) -> bool:
    """Compare-and-swap: move `branch` to `sha` only if it is still at `expect` (None: absent)."""
    r = subprocess.run(["git", "push", "-q", f"--force-with-lease=refs/heads/{branch}:{expect or ''}",
                        REMOTE, f"{sha}:refs/heads/{branch}"], capture_output=True, text=True)
    return r.returncode == 0


def commit(tree_sha: str, parent: str | None, message: str) -> str:
    return git("commit-tree", tree_sha, *(["-p", parent] if parent else []), "-m", message)


def index_env() -> dict:
    fd, path = tempfile.mkstemp(prefix="candidate-index-")
    os.close(fd)
    os.unlink(path)
    return {"GIT_INDEX_FILE": path}


def gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode:
        raise Stop(1, f"gh {' '.join(args[:3])} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def repo() -> str:
    return os.environ["GITHUB_REPOSITORY"]


def pull(number: int) -> dict:
    return json.loads(gh("api", f"repos/{repo()}/pulls/{number}"))


def open_data_prs() -> list[tuple[int, str]]:
    out = gh("pr", "list", "--state", "open", "--limit", "200", "--json", "number,headRefName",
             "--jq", '.[] | "\\(.number) \\(.headRefName)"')
    prs = [line.split(" ", 1) for line in out.splitlines() if line.strip()]
    return [(int(n), ref) for n, ref in prs if DATA_PR.match(ref)]


def checks_green(sha: str) -> tuple[bool, str]:
    """The latest `test` and `architecture` check runs on exactly this commit both succeeded."""
    runs = json.loads(gh("api", f"repos/{repo()}/commits/{sha}/check-runs?per_page=100")).get("check_runs", [])
    latest: dict[str, dict] = {}
    for run in runs:
        if run.get("name") in REQUIRED_CHECKS and run.get("id", 0) >= latest.get(run["name"], {}).get("id", -1):
            latest[run["name"]] = run
    seen = {n: (latest[n].get("conclusion") if n in latest else "missing") for n in REQUIRED_CHECKS}
    return all(v == "success" for v in seen.values()), ", ".join(f"{n} {v}" for n, v in seen.items())


# --- outputs ---------------------------------------------------------------

def output(**values) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    for k, v in values.items():
        v = "" if v is None else str(v).lower() if isinstance(v, bool) else str(v)
        print(f"{k}={v}")
        if path:
            with open(path, "a") as fh:
                fh.write(f"{k}={v}\n")


def summary(text: str) -> None:
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as fh:
            fh.write(text + "\n")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- the ledger ------------------------------------------------------------

def ledger() -> tuple[str | None, dict[str, dict]]:
    head = fetch(LEDGER)
    if not head:
        return None, {}
    records = {}
    for name in git("ls-tree", "--name-only", f"{head}:runs").splitlines():
        if name.endswith(".json"):
            records[name[:-5]] = json.loads(git("cat-file", "blob", f"{head}:runs/{name}"))
    return head, records


def write(run_id: str, change, note: str = "") -> dict:
    """Apply `change(record or None) -> record` and push it; re-read and retry on a concurrent write."""
    for _ in range(3):
        head, records = ledger()
        rec = change(records.get(run_id))
        rec.setdefault("history", []).append({"state": rec["state"], "at": now(), "note": note})
        blob = git("hash-object", "-w", "--stdin", stdin=json.dumps(rec, indent=2, sort_keys=True) + "\n")
        env = index_env()
        if head:
            git("read-tree", head, env=env)
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},runs/{run_id}.json", env=env)
        new = commit(git("write-tree", env=env), head, f"candidate {run_id}: {rec['state']}")
        if push(new, LEDGER, head):
            return rec
    raise Stop(5, f"could not write the ledger ({LEDGER}) after 3 attempts")


def transition(run_id: str, state: str, note: str = "", **fields) -> dict:
    def change(rec):
        if rec is None:
            raise Stop(6, f"no candidate is recorded for run {run_id}")
        return {**rec, **fields, "state": state}
    return write(run_id, change, note)


def restore(rev: str, paths) -> None:
    """Replace each path in the working tree with its copy at `rev`. Nothing is staged."""
    for p in paths:
        if not tree(rev, p):
            continue
        subprocess.run(["rm", "-rf", "--", p], check=True)
        archive = subprocess.run(["git", "archive", rev, "--", p], capture_output=True, check=True)
        subprocess.run(["tar", "-x"], input=archive.stdout, check=True)


# --- commands --------------------------------------------------------------

def cmd_preflight(a) -> int:
    _, records = ledger()
    blockers = [f"run {rid}: candidate {rec['state']}" + (f", PR #{rec['pr']}" if rec.get("pr") else ", no PR")
                for rid, rec in sorted(records.items()) if rid != a.run_id and rec["state"] in UNRESOLVED]
    blockers += [f"PR #{n} ({ref}) is open" for n, ref in open_data_prs() if DATA_PR.match(ref).group(2) != a.run_id]
    if blockers:
        summary("### Weekly sync HELD: an earlier data run is unresolved\n\n"
                + "\n".join(f"- {b}" for b in blockers)
                + "\n\nNothing was pulled or written. Resolve it first: merge its data PR (promotes the candidate) "
                  "or close it (rejects it). A candidate with no PR: re-run that workflow run to resume it, or "
                  "reject it from the Promote data workflow. Then run the sync again.")
        print("::error::Weekly sync held: " + "; ".join(blockers))
        return 3
    resume = a.run_id in records
    output(resume=resume)
    if resume:
        print(f"Run {a.run_id} already has candidate {records[a.run_id]['candidate_sha']} "
              f"({records[a.run_id]['state']}): this attempt resumes it and pulls nothing.")
    return 0


def cmd_begin(a) -> int:
    _, records = ledger()
    rec = records.get(a.run_id)
    if rec is None:
        store = fetch(STORE)
        if not store:
            raise Stop(4, f"{REMOTE} has no branch {STORE}")
        master = tree(store, MASTER)
        if not master:
            raise Stop(3, f"{MASTER} is not on {STORE}")
        restore(store, [MASTER])
        print(f"Computing from the accepted master: {STORE} {store[:12]}, {MASTER} tree {master[:12]}.")
        output(resume=False, done=False, input_commit=store, input_tree=master)
        return 0
    try:
        candidate(rec)
    except Stop as stop:
        raise Stop(5, f"{stop}; refusing to resume")
    done = rec["state"] not in UNRESOLVED
    if not done:
        restore(rec["candidate_sha"], (MASTER, *PAYLOAD))
        if worktree_tree(MASTER) != rec["candidate_master_tree"]:
            raise Stop(5, f"the restored {MASTER} does not match candidate {rec['candidate_sha']}")
    print(f"Resuming run {a.run_id}: candidate {rec['candidate_sha'][:12]} is {rec['state']}; nothing is recomputed.")
    output(resume=True, done=done, input_commit=rec["input_commit"], input_tree=rec["input_master_tree"],
           candidate_sha=rec["candidate_sha"])
    return 0


def _staged(*paths: str) -> dict:
    """A throwaway index holding only `paths` from the working tree (data/ is gitignored, hence -f)."""
    env = index_env()
    git("add", "-f", "--", *paths, env=env)
    return env


def worktree_tree(path: str) -> str:
    """The git tree hash of `path` as it stands in the working tree."""
    return git("rev-parse", f"{git('write-tree', env=_staged(path))}:{path}")


def cmd_persist(a) -> int:
    _, records = ledger()
    if a.run_id in records:
        raise Stop(5, f"run {a.run_id} already has a candidate ({records[a.run_id]['state']}); a re-run resumes it")
    if not Path(MASTER).exists():
        raise Stop(3, f"{MASTER} does not exist here; nothing to persist")
    input_tree = tree(a.input_commit, MASTER)
    if not input_tree:
        raise Stop(3, f"{a.input_commit} has no {MASTER}")
    env = _staged(MASTER, *[p for p in PAYLOAD if Path(p).exists()])
    root = git("write-tree", env=env)
    master_tree = git("rev-parse", f"{root}:{MASTER}")
    branch = CANDIDATE.format(a.run_id)
    sha = commit(root, a.input_commit,
                 f"candidate for weekly sync run {a.run_id} (attempt {a.attempt})\n\n"
                 f"input {STORE} {a.input_commit}, {MASTER} tree {input_tree}\n"
                 f"candidate {MASTER} tree {master_tree}")
    if not push(sha, branch, None):
        existing = fetch(branch)
        # an earlier attempt pushed it, then stopped before the ledger write
        if not existing or git("rev-parse", f"{existing}^{{tree}}") != root:
            raise Stop(5, f"{branch} already exists with other content; a candidate is never replaced")
        sha = existing
    rec = write(a.run_id, lambda _: {
        "run_id": a.run_id, "attempt": int(a.attempt), "kind": "weekly-sync",
        "input_commit": a.input_commit, "input_master_tree": input_tree,
        "candidate_branch": branch, "candidate_sha": sha, "candidate_master_tree": master_tree,
        "master_changed": master_tree != input_tree,
        "pr": None, "pr_branch": None, "pr_head": None, "accepted_commit": None,
        "writeback": "requested" if a.writeback else "not_requested",
        "state": "persisted"}, note=f"attempt {a.attempt}")
    print(f"Candidate persisted: {branch} {sha[:12]} (master {'changed' if rec['master_changed'] else 'unchanged'}). "
          f"{STORE} is not touched until the owner merges the data PR.")
    output(candidate_sha=sha, candidate_branch=branch, master_changed=rec["master_changed"])
    return 0


def cmd_record_pr(a) -> int:
    _, records = ledger()
    rec = records.get(a.run_id)
    if rec is None or rec["state"] not in UNRESOLVED:
        raise Stop(6, f"run {a.run_id} has no unresolved candidate to attach a PR to")
    if not a.pr:
        if rec["master_changed"]:
            raise Stop(6, f"the master changed but no data PR was opened for run {a.run_id}")
        transition(a.run_id, "no_change", "no data changes, no PR; the accepted master stands")
        return 0
    sha = candidate(rec)
    for p in PAYLOAD:
        if tree(a.head, p) != tree(sha, p):
            raise Stop(7, f"PR head {a.head} carries a different {p} from candidate {rec['candidate_sha']}")
    fields = {"pr": int(a.pr), "pr_branch": f"data/weekly-sync-{a.run_id}", "pr_head": a.head}
    if a.status == "merged":
        transition(a.run_id, rec["state"], "PR already merged; promotion is the Promote data workflow's", **fields)
        print(f"::warning::PR #{a.pr} is already merged; the Promote data workflow promotes the candidate.")
        return 0
    transition(a.run_id, "awaiting_owner_merge", f"PR #{a.pr}, CI dispatched on {a.head}", **fields)
    return 0


def candidate(rec: dict) -> str:
    """Fetch the run's candidate (a fresh runner lacks its objects) and check it is the recorded one."""
    if fetch(rec["candidate_branch"]) != rec["candidate_sha"]:
        raise Stop(5, f"{rec['candidate_branch']} does not point at the recorded candidate {rec['candidate_sha']}")
    return rec["candidate_sha"]


def promote(rec: dict) -> str:
    """Compare-and-swap data/store's master from the run's input tree to its candidate tree."""
    candidate(rec)
    for _ in range(3):
        store = fetch(STORE)
        if not store:
            raise Stop(4, f"{REMOTE} has no branch {STORE}")
        current = tree(store, MASTER)
        if current == rec["candidate_master_tree"]:
            return store
        if current != rec["input_master_tree"]:
            raise Stop(8, "stale")
        env = index_env()
        git("read-tree", store, env=env)
        git("rm", "-r", "-q", "-f", "--cached", "--", MASTER, env=env)
        git("read-tree", f"--prefix={MASTER}/", rec["candidate_master_tree"], env=env)
        new = commit(git("write-tree", env=env), store,
                     f"accept weekly sync run {rec['run_id']}: PR #{rec['pr']} merged\n\n"
                     f"candidate {rec['candidate_sha']}, {MASTER} tree {rec['candidate_master_tree']}")
        if push(new, STORE, store):
            return new
    raise Stop(5, f"could not move {STORE} after 3 attempts")


def cmd_close(a) -> int:
    pr = pull(a.pr)
    m = re.match(r"^data/weekly-sync-(\d+)$", pr["head"]["ref"])
    if not m:
        print(f"PR #{a.pr} ({pr['head']['ref']}) is not a weekly sync data PR; nothing to promote.")
        output(promoted=False, writeback=False)
        return 0
    run_id = m.group(1)
    output(run_id=run_id)
    _, records = ledger()
    rec = records.get(run_id)
    if rec is None:
        raise Stop(6, f"no candidate is recorded for run {run_id}; nothing is promoted")
    if rec["state"] == "promoted":
        print(f"Run {run_id} is already promoted ({STORE} {rec['accepted_commit']}).")
        output(promoted=True, writeback=rec["writeback"] == "requested")
        return 0
    if rec["state"] not in UNRESOLVED:
        raise Stop(6, f"run {run_id} is {rec['state']}; it cannot be promoted")
    if pr["state"] == "open":
        raise Stop(6, f"PR #{a.pr} is still open; only its merge promotes the candidate")
    if not pr.get("merged"):
        transition(run_id, "rejected", f"PR #{a.pr} closed without merging", pr=int(a.pr))
        print(f"PR #{a.pr} closed unmerged: candidate {rec['candidate_sha'][:12]} rejected; {STORE} unchanged.")
        output(promoted=False, writeback=False)
        return 0

    head = pr["head"]["sha"]
    reason = None
    if rec["state"] != "awaiting_owner_merge" or not rec.get("pr_head"):
        reason = "the sync never recorded this PR's head and CI dispatch"
    elif head != rec["pr_head"]:
        reason = f"the merged head {head} is not the recorded head {rec['pr_head']}"
    else:
        green, seen = checks_green(head)
        if not green:
            reason = f"CI on {head} was not green ({seen})"
    if reason:
        transition(run_id, "promotion_refused", reason, pr=int(a.pr))
        raise Stop(10, f"PR #{a.pr} merged, but {reason}: candidate not promoted; {STORE} unchanged")
    try:
        accepted = promote(rec)
    except Stop as stop:
        if str(stop) != "stale":
            raise
        transition(run_id, "stale", "the accepted master moved since this run started", pr=int(a.pr))
        raise Stop(8, f"the accepted master moved since run {run_id} started: candidate not promoted; "
                      f"{STORE} unchanged. The next weekly sync recomputes from the accepted master.")
    rec = transition(run_id, "promoted", f"PR #{a.pr} merged by the owner", pr=int(a.pr), accepted_commit=accepted)
    print(f"Promoted: {STORE} {accepted[:12]} now holds candidate {rec['candidate_sha'][:12]}'s master.")
    output(promoted=True, writeback=rec["writeback"] == "requested")
    return 0


def cmd_reject(a) -> int:
    _, records = ledger()
    rec = records.get(a.run_id)
    if rec is None or rec["state"] not in UNRESOLVED:
        raise Stop(6, f"run {a.run_id} has no unresolved candidate")
    if rec.get("pr"):
        state = pull(rec["pr"])
        if state["state"] == "open" or state.get("merged"):
            raise Stop(6, f"PR #{rec['pr']} is {'merged' if state.get('merged') else 'open'}; close it instead "
                          "(closing rejects the candidate)")
    transition(a.run_id, "rejected", "rejected by the owner's dispatch")
    print(f"Run {a.run_id}'s candidate rejected; {STORE} unchanged.")
    return 0


def cmd_writeback_gate(a) -> int:
    _, records = ledger()
    rec = records.get(a.run_id)
    if rec is None or rec["state"] != "promoted":
        raise Stop(9, f"run {a.run_id} is {rec['state'] if rec else 'unknown'}: "
                      "Apollo writeback runs only after the owner's merge promoted the candidate")
    store = fetch(STORE)
    if not store or tree(store, MASTER) != rec["candidate_master_tree"]:
        raise Stop(9, f"{STORE} no longer holds run {a.run_id}'s accepted master; writeback refused")
    restore(store, [MASTER])
    print(f"Writing back from the accepted master ({STORE} {store[:12]}).")
    return 0


def cmd_mark_writeback(a) -> int:
    transition(a.run_id, "promoted", f"writeback {a.result}",
               writeback="done" if a.result == "success" else f"failed ({a.result})")
    return 0


def cmd_status(a) -> int:
    run_id = a.run_id
    if a.pr:
        m = DATA_PR.match(pull(a.pr)["head"]["ref"])
        run_id = m.group(2) if m else None
    _, records = ledger()
    rec = records.get(run_id or "")
    store = fetch(STORE)
    accepted = tree(store, MASTER) if store else None
    acc = f"accepted {MASTER} tree {accepted[:12] if accepted else 'none'} ({STORE} {store[:12] if store else 'missing'})"
    if rec is None:
        summary(f"### Data run {run_id or '?'}\n\n- **master:** {acc}; no candidate recorded\n"
                "- **data PR:** none\n- **CRM reconciliation:** not started")
        return 0
    cand = f"candidate {rec['candidate_sha'][:12]} ({'changes' if rec['master_changed'] else 'no change to'} the master)"
    master = {
        "promoted": f"{acc}; {cand} promoted",
        "persisted": f"{acc}, unchanged; {cand} persisted, awaiting its data PR",
        "awaiting_owner_merge": f"{acc}, unchanged; {cand} awaiting the owner's merge",
    }.get(rec["state"], f"{acc}, unchanged; {cand} {rec['state'].replace('_', ' ')}")
    pr = (f"#{rec['pr']} ({rec['pr_branch']}), head {rec['pr_head'][:12]}" if rec.get("pr_head")
          else f"#{rec['pr']}" if rec.get("pr") else "none opened")
    pr += {"awaiting_owner_merge": ", open: Python CI dispatched with expected_sha = head; the owner merges",
           "promoted": ", merged by the owner", "rejected": ", closed: rejected"}.get(rec["state"], "")
    if rec["state"] == "promoted":
        crm = "pending: the Monday enrichment push reconciles the CRM from the accepted master"
        if rec["writeback"] != "not_requested":
            crm += f"; Apollo writeback {rec['writeback']}"
    else:
        crm = "not started: it runs only from an accepted master"
    summary(f"### Data run {run_id}\n\n- **master:** {master}\n- **data PR:** {pr}\n- **CRM reconciliation:** {crm}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("preflight", "begin", "reject", "writeback-gate"):
        sub.add_parser(name).add_argument("--run-id", required=True)
    p = sub.add_parser("persist")
    p.add_argument("--run-id", required=True)
    p.add_argument("--attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    p.add_argument("--input-commit", required=True)
    p.add_argument("--writeback", action="store_true")
    p = sub.add_parser("record-pr")
    p.add_argument("--run-id", required=True)
    p.add_argument("--pr", default="")
    p.add_argument("--head", default="")
    p.add_argument("--status", default="", choices=["", "awaiting_owner_merge", "merged"])
    sub.add_parser("close").add_argument("--pr", required=True, type=int)
    p = sub.add_parser("mark-writeback")
    p.add_argument("--run-id", required=True)
    p.add_argument("--result", required=True)
    p = sub.add_parser("status")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-id")
    g.add_argument("--pr", type=int)
    a = ap.parse_args(argv)
    try:
        return globals()["cmd_" + a.cmd.replace("-", "_")](a)
    except Stop as stop:
        print(f"::error::{stop}")
        return stop.code


if __name__ == "__main__":
    sys.exit(main())
