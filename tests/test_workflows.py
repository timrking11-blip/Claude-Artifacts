"""The weekly sync workflow's own controls, pinned so an edit cannot drop them quietly.

A plain YAML load accepts a duplicated key and keeps the last one, so the
workflows are loaded strictly here first.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
SYNC = ROOT / ".github" / "workflows" / "weekly-crm-sync.yml"
PROMOTE = ROOT / ".github" / "workflows" / "data-promote.yml"
CI = ROOT / ".github" / "workflows" / "python-ci.yml"


class StrictLoader(yaml.SafeLoader):
    pass


def _no_duplicates(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise yaml.constructor.ConstructorError(None, None, f"duplicate keys {sorted(map(str, dupes))}", node.start_mark)
    return loader.construct_mapping(node, deep)


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


def load(path):
    return yaml.load(path.read_text(), Loader=StrictLoader)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflows_have_no_duplicate_keys(path):
    load(path)


def runs_of(job):
    return [s.get("run", "") for s in job["steps"]]


def test_the_sync_never_pushes_to_the_default_branch():
    assert "git push" not in SYNC.read_text()
    runs = [r for job in load(SYNC)["jobs"].values() for r in runs_of(job)]
    assert sum("scripts/open_data_pr.sh" in r for r in runs) == 1


def test_nothing_automated_merges_a_pr():
    # Data PRs wait for the owner's merge (decided 10 Oct 2026; no auto-merge).
    for path in [*WORKFLOWS, *sorted((ROOT / "scripts").glob("*.sh")), *sorted((ROOT / "scripts").glob("*.py"))]:
        text = path.read_text()
        assert "gh pr merge" not in text and "merge_pull_request" not in text, path.name
        assert not re.search(r"pulls/[^\s]*/merge\b", text), path.name


def test_keys_come_from_repository_secrets_only():
    # Private on GitHub Free: no environment secrets, so no job may depend on one.
    jobs = load(SYNC)["jobs"]
    readers = {name for name, job in jobs.items() if "secrets." in yaml.safe_dump(job)}
    assert readers == {"preflight", "pull-apollo", "pull-explorium", "pull-explorium-serial"}
    assert not any("environment" in job for job in jobs.values())
    jobs = load(PROMOTE)["jobs"]
    assert {name for name, job in jobs.items() if "secrets." in yaml.safe_dump(job)} == {"writeback"}
    assert not any("environment" in job for job in jobs.values())


def test_the_sync_refuses_to_run_from_another_branch():
    steps = load(SYNC)["jobs"]["preflight"]["steps"]
    guard = steps[0]
    assert guard["name"] == "Run only from the default branch"
    assert "github.event.repository.default_branch" in guard["if"] and "exit 1" in guard["run"]
    jobs = load(SYNC)["jobs"]
    assert jobs["pull-apollo"]["needs"] == "preflight" and jobs["pull-explorium"]["needs"] == "preflight"


def test_writeback_runs_only_after_the_owners_merge_promoted_the_candidate():
    assert "writeback" not in load(SYNC)["jobs"]
    jobs = load(PROMOTE)["jobs"]
    wb = jobs["writeback"]
    assert wb["needs"] == "promote" and wb["if"] == "${{ needs.promote.outputs.writeback == 'true' }}"
    runs = runs_of(wb)
    gate = next(i for i, r in enumerate(runs) if "data_candidate.py writeback-gate" in r)
    push = next(i for i, r in enumerate(runs) if "push_apollo.py --apply" in r)
    assert gate < push and "if" not in wb["steps"][gate]       # the gate always runs, and before the push
    assert "STACKED_ON" not in PROMOTE.read_text()


def test_promotion_runs_on_the_owners_merge_and_never_checks_out_the_pr():
    wf = load(PROMOTE)
    assert wf[True]["pull_request_target"]["types"] == ["closed"]
    assert wf["concurrency"] == {"group": "crm-sync", "cancel-in-progress": False}
    assert load(SYNC)["concurrency"]["group"] == "crm-sync"
    for job in wf["jobs"].values():
        for step in job["steps"]:
            if step.get("uses", "").startswith("actions/checkout"):
                assert step["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    promote = wf["jobs"]["promote"]
    assert "data/weekly-sync-" in promote["if"] and "head.repo.full_name == github.repository" in promote["if"]
    assert promote["steps"][0]["name"] == "Run only from the default branch"
    assert any("data_candidate.py close" in r for r in runs_of(promote))


def test_an_unresolved_earlier_run_holds_the_sync_before_anything_is_pulled():
    jobs = load(SYNC)["jobs"]
    hold = next(s for s in jobs["preflight"]["steps"] if s.get("id") == "hold")
    assert "data_candidate.py preflight" in hold["run"] and "continue-on-error" not in hold
    assert jobs["preflight"]["outputs"]["resume"] == "${{ steps.hold.outputs.resume }}"
    for name in ("pull-apollo", "pull-explorium"):
        assert jobs[name]["needs"] == "preflight" and "needs.preflight.outputs.resume != 'true'" in jobs[name]["if"]
    assert jobs["pull-explorium-serial"]["needs"] == "pull-apollo"
    assert "needs.preflight.result == 'success'" in jobs["merge"]["if"]


def test_a_rerun_resumes_its_candidate_and_never_recomputes():
    steps = {s.get("name") or s.get("uses"): s for s in load(SYNC)["jobs"]["merge"]["steps"]}
    for name in ("actions/download-artifact@v4", "Merge", "Persist the candidate"):
        assert steps[name]["if"] == "${{ steps.begin.outputs.resume != 'true' }}", name
    for name in ("Open the data PR", "Record the PR on the candidate"):
        assert steps[name]["if"] == "${{ steps.begin.outputs.done != 'true' }}", name


def test_the_sync_never_writes_data_store_and_persists_before_its_pr():
    text = SYNC.read_text()
    assert "data_store.sh save" not in text
    runs = runs_of(load(SYNC)["jobs"]["merge"])
    order = [next(i for i, r in enumerate(runs) if key in r) for key in
             ("data_candidate.py begin", "merge_master.py", "validate_sync.py", "data_candidate.py persist",
              "open_data_pr.sh", "data_candidate.py record-pr", "data_candidate.py status")]
    assert order == sorted(order)
    assert all("data/master" not in r for r in runs if "open_data_pr.sh" in r)


def test_python_ci_can_be_dispatched_onto_a_data_branch():
    ci = load(CI)
    assert "workflow_dispatch" in ci[True]  # YAML 1.1 reads the bare key `on` as True
    assert set(ci["jobs"]) >= {"test", "architecture"}


def test_python_ci_fails_unless_it_checked_out_the_expected_sha():
    ci = load(CI)
    assert "expected_sha" in ci[True]["workflow_dispatch"]["inputs"]
    for name in ("test", "architecture"):
        steps = ci["jobs"][name]["steps"]
        assert steps[0]["uses"] == "actions/checkout@v4" and "with" not in steps[0]
        check = steps[1]
        assert check["if"] == "${{ inputs.expected_sha }}" and check["env"]["EXPECTED_SHA"] == "${{ inputs.expected_sha }}"
        assert "git rev-parse HEAD" in check["run"] and '"$GITHUB_SHA" != "$EXPECTED_SHA"' in check["run"]
        assert "exit 1" in check["run"]
    assert 'expected_sha="$head"' in (ROOT / "scripts" / "open_data_pr.sh").read_text()


def test_a_missing_key_says_where_to_add_it():
    step = next(s for s in load(SYNC)["jobs"]["preflight"]["steps"] if s["name"] == "Verify the API keys are present")
    assert "New repository secret" in step["run"] and "Secrets and variables -> Actions" in step["run"]
    assert "APOLLO_API_KEY" in step["run"] and "EXPLORIUM_API_KEY" in step["run"]


def test_check_keys_stops_after_the_key_check():
    wf = load(SYNC)
    assert wf[True]["workflow_dispatch"]["inputs"]["check_keys"]["default"] is False
    jobs = wf["jobs"]
    # every pull is skipped in check mode; merge and writeback need a pull, so they skip too
    for name in ("pull-apollo", "pull-explorium", "pull-explorium-serial"):
        assert jobs[name]["if"].startswith("${{ !inputs.check_keys"), name
    assert "needs.pull-apollo.result == 'success'" in jobs["merge"]["if"] and "!inputs.check_keys" in jobs["merge"]["if"]
    hold = next(s for s in jobs["preflight"]["steps"] if s.get("id") == "hold")
    assert hold["if"] == "${{ !inputs.check_keys }}"
    last = jobs["preflight"]["steps"][-1]
    assert last["if"] == "${{ inputs.check_keys }}" and "Nothing pulled or written" in last["run"]


def test_codeql_skips_while_the_repository_is_private():
    jobs = load(ROOT / ".github" / "workflows" / "codeql.yml")["jobs"]
    assert jobs["analyze"]["needs"] == "visibility"
    # runs only on an explicit "false": an unreadable visibility skips rather than fails
    assert jobs["analyze"]["if"] == "${{ needs.visibility.outputs.private == 'false' }}"
    assert "gh api" in jobs["visibility"]["steps"][0]["run"] and ".private" in jobs["visibility"]["steps"][0]["run"]


def test_every_job_that_reads_the_master_restores_it_first():
    for path, name, restore in ((SYNC, "pull-explorium", "scripts/data_store.sh restore data/master"),
                                (SYNC, "merge", "python scripts/data_candidate.py begin"),
                                (PROMOTE, "writeback", "python scripts/data_candidate.py writeback-gate")):
        runs = runs_of(load(path)["jobs"][name])
        first = next(i for i, r in enumerate(runs) if r.startswith(restore))
        reads = [i for i, r in enumerate(runs) if r.startswith("python scripts/") and not r.startswith(restore)]
        assert reads and first < min(reads), name


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_that_runs_pytest_installs_pyyaml_first(path):
    # Several test modules import yaml when pytest collects them, so a job that
    # runs pytest without PyYAML fails before any test runs (the weekly sync's
    # merge job did until 10 Oct 2026). Commands are read in order across steps.
    for name, job in (load(path).get("jobs") or {}).items():
        commands = [c.strip() for s in job.get("steps") or [] for c in s.get("run", "").split("&&")]
        runs_pytest = [i for i, c in enumerate(commands)
                       if not c.startswith("pip ") and re.search(r"(^|\s)(python -m )?pytest\b", c)]
        if not runs_pytest:
            continue
        installs = [i for i, c in enumerate(commands) if c.startswith("pip install") and "pyyaml" in c.split()]
        assert installs and min(installs) < min(runs_pytest), f"{path.name}: job {name} runs pytest before installing pyyaml"
