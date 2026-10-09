"""The weekly sync workflow's own controls, pinned so an edit cannot drop them quietly.

A plain YAML load accepts a duplicated key and keeps the last one, so the
workflows are loaded strictly here first.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
SYNC = ROOT / ".github" / "workflows" / "weekly-crm-sync.yml"


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


def test_the_sync_never_pushes_to_the_default_branch():
    assert "git push" not in SYNC.read_text()
    runs = [s.get("run", "") for job in load(SYNC)["jobs"].values() for s in job["steps"]]
    assert sum("scripts/open_data_pr.sh" in r for r in runs) == 2


def test_every_job_that_reads_a_key_runs_in_the_protected_environment():
    jobs = load(SYNC)["jobs"]
    readers = {name for name, job in jobs.items() if "secrets." in yaml.safe_dump(job)}
    assert readers == {"preflight", "pull-apollo", "pull-explorium", "pull-explorium-serial", "writeback"}
    assert all(jobs[name].get("environment") == "crm-sync" for name in readers)


def test_the_sync_refuses_to_run_from_another_branch():
    steps = load(SYNC)["jobs"]["preflight"]["steps"]
    guard = steps[0]
    assert guard["name"] == "Run only from the default branch"
    assert "github.event.repository.default_branch" in guard["if"] and "exit 1" in guard["run"]
    jobs = load(SYNC)["jobs"]
    assert jobs["pull-apollo"]["needs"] == "preflight" and jobs["pull-explorium"]["needs"] == "preflight"


def test_writeback_names_the_data_pr_it_is_stacked_on():
    wb = load(SYNC)["jobs"]["writeback"]
    assert wb["steps"][0]["with"]["ref"] == "${{ needs.merge.outputs.branch || github.ref }}"
    step = next(s for s in wb["steps"] if s.get("name") == "Open the run line PR")
    assert step["env"]["STACKED_ON"] == "${{ needs.merge.outputs.branch }}"


def test_python_ci_can_be_dispatched_onto_a_data_branch():
    ci = load(ROOT / ".github" / "workflows" / "python-ci.yml")
    assert "workflow_dispatch" in ci[True]  # YAML 1.1 reads the bare key `on` as True
    assert set(ci["jobs"]) >= {"test", "architecture"}


def test_a_missing_key_names_both_places_the_sync_reads_from():
    step = next(s for s in load(SYNC)["jobs"]["preflight"]["steps"] if s["name"] == "Verify the API keys are present")
    assert "crm-sync" in step["run"] and "Secrets and variables -> Actions" in step["run"]
    assert "APOLLO_API_KEY" in step["run"] and "EXPLORIUM_API_KEY" in step["run"]


def test_check_keys_stops_after_the_key_check():
    wf = load(SYNC)
    assert wf[True]["workflow_dispatch"]["inputs"]["check_keys"]["default"] is False
    jobs = wf["jobs"]
    # every pull is skipped in check mode; merge and writeback need a pull, so they skip too
    for name in ("pull-apollo", "pull-explorium", "pull-explorium-serial"):
        assert jobs[name]["if"].startswith("${{ !inputs.check_keys"), name
    assert "needs.pull-apollo.result == 'success'" in jobs["merge"]["if"]
    assert jobs["writeback"]["needs"] == "merge"
    last = jobs["preflight"]["steps"][-1]
    assert last["if"] == "${{ inputs.check_keys }}" and "Nothing pulled or written" in last["run"]
