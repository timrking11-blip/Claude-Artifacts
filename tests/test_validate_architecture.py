"""scripts/validate_architecture.py: the manifest, ADR files, matrix, invariants and code agree."""

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


va = _load_script("validate_architecture")
SHA = "a" * 40


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(ROOT / "architecture", tmp_path / "architecture")
    (tmp_path / ".github").mkdir()
    shutil.copy(ROOT / ".github" / "CODEOWNERS", tmp_path / ".github" / "CODEOWNERS")
    return tmp_path


def manifest_path(root):
    return root / "architecture" / "architecture-manifest.yaml"


def edit_yaml(path, fn):
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def errors(root):
    r, _ = va.validate(root)
    return r.errors


def adr7(root):
    return next((root / "architecture" / "adr").glob("ADR-007-*.md"))


def make_effective(root, sha=SHA, when="2026-10-12"):
    edit_yaml(manifest_path(root), lambda m: m["authority"].update(
        {"transition": "effective", "effective_commit": sha, "effective_date": when}))
    edit_yaml(root / "architecture" / "system-of-record.yaml", lambda m: next(
        c for c in m["current"] if c["object"] == "architecture decision").update({"store": "repository-architecture"}))
    p = adr7(root)
    p.write_text(p.read_text().replace("Status: Accepted; transition pending merge", "Status: Accepted; effective")
                 .replace("Effective commit: pending", f"Effective commit: {sha}")
                 .replace("Effective date: pending", f"Effective date: {when}"))


def test_the_repository_validates_clean():
    r, want = va.validate(ROOT)
    assert r.errors == []
    assert any("pending merge" in w for w in r.warnings)


def test_an_adr_status_that_disagrees_with_the_index_fails(repo):
    p = next((repo / "architecture" / "adr").glob("ADR-002-*.md"))
    p.write_text(p.read_text().replace("Status: Proposed", "Status: Accepted"))
    assert any("ADR-002" in e and "disagrees" in e for e in errors(repo))


def test_an_unindexed_adr_file_fails(repo):
    (repo / "architecture" / "adr" / "ADR-099-stray.md").write_text("# ADR-099 — Stray\n\nStatus: Proposed\n")
    assert any("ADR-099-stray.md is not indexed" in e for e in errors(repo))


def test_pending_transition_may_not_record_an_effective_commit(repo):
    edit_yaml(manifest_path(repo), lambda m: m["authority"].update({"effective_commit": SHA}))
    assert any("pending, so no effective commit" in e for e in errors(repo))


def test_a_consistent_effective_transition_passes_apart_from_the_digest(repo):
    make_effective(repo)
    errs = [e for e in errors(repo) if "protected_digest" not in e]
    assert errs == []


def test_effective_commit_must_match_and_not_be_backdated(repo):
    make_effective(repo, when="2026-09-30")
    assert any("may not precede the decision" in e for e in errors(repo))
    make_effective(repo)
    p = adr7(repo)
    p.write_text(p.read_text().replace(f"Effective commit: {SHA}", f"Effective commit: {'b' * 40}"))
    assert any("same in the ADR and the manifest" in e for e in errors(repo))


def test_the_architecture_owner_follows_the_transition(repo):
    edit_yaml(repo / "architecture" / "system-of-record.yaml", lambda m: next(
        c for c in m["current"] if c["object"] == "architecture decision").update({"store": "repository-architecture"}))
    assert any("architecture decisions are owned by 'repository-architecture'" in e for e in errors(repo))


def test_field_groups_must_equal_the_code(repo):
    edit_yaml(repo / "architecture" / "system-of-record.yaml",
              lambda m: m["field_groups"]["crm_owned"]["fields"].remove("stage"))
    assert any("field group crm_owned" in e for e in errors(repo))


def test_a_proposed_store_cannot_hold_current_authority(repo):
    def fn(m):
        m["current"].append({"object": "signal", "store": "intelligence-core"})
    edit_yaml(repo / "architecture" / "system-of-record.yaml", fn)
    assert any("owned by a proposed store" in e for e in errors(repo))


def test_one_write_authority_per_current_object(repo):
    def fn(m):
        m["current"].append({"object": "contact", "store": "git-master"})
    edit_yaml(repo / "architecture" / "system-of-record.yaml", fn)
    assert any("more than one write authority" in e for e in errors(repo))


def test_cap_in_the_manifest_must_equal_the_code(repo):
    edit_yaml(manifest_path(repo), lambda m: m["composition"].update({"monthly_cap": 10}))
    assert any("composition.monthly_cap" in e for e in errors(repo))


def test_a_governed_writer_is_never_routed_to_sonnet(repo):
    def fn(m):
        next(r for r in m["routines"] if r.get("governed_writer") and r["model"] != "session")["model"] = "claude-sonnet-5-5"
    edit_yaml(manifest_path(repo), fn)
    assert any("governed writer is routed" in e for e in errors(repo))


def test_production_verified_needs_criteria_and_a_reviewer(repo):
    edit_yaml(manifest_path(repo), lambda m: m["capabilities"][0].update({"implementation_state": "PRODUCTION_VERIFIED"}))
    assert any("PRODUCTION_VERIFIED needs" in e for e in errors(repo))


def test_a_capability_status_must_match_its_adr(repo):
    def fn(m):
        next(c for c in m["capabilities"] if c.get("decision") == "ADR-012")["decision_status"] = "Accepted"
    edit_yaml(manifest_path(repo), fn)
    assert any("but ADR-012 is Proposed" in e for e in errors(repo))


def test_a_missing_gap_fails(repo):
    edit_yaml(manifest_path(repo), lambda m: m["capabilities"][0].update({"gap": "GAP-999"}))
    assert any("GAP-999" in e for e in errors(repo))


def test_invariant_decision_statuses_must_agree(repo):
    edit_yaml(repo / "architecture" / "invariants.yaml",
              lambda m: next(d for d in m["decisions"] if d["id"] == "ADR-006").update({"status": "Accepted"}))
    assert any("invariants.yaml: ADR-006" in e for e in errors(repo))


def test_personal_emails_and_infrastructure_ids_are_refused(repo):
    (repo / "architecture" / "audits" / "note.md").write_text("contact someone@example.org\nprojects/my-gcp-project-1\n")
    errs = errors(repo)
    assert any("email address" in e for e in errs) and any("infrastructure identifier" in e for e in errs)


def test_the_digest_detects_an_unregenerated_change_and_update_fixes_it(repo):
    assert not any("protected_digest" in e for e in errors(repo))
    edit_yaml(repo / "architecture" / "system-of-record.yaml", lambda m: m["accepted_target"].pop())
    assert any("protected_digest is stale" in e for e in errors(repo))
    assert va.main(["--root", str(repo), "--update-digest"]) == 0
    assert errors(repo) == []


def test_a_normative_invariant_needs_an_accepted_adr(repo):
    edit_yaml(repo / "architecture" / "invariants.yaml",
              lambda m: next(i for i in m["invariants"] if i["adr"] == "ADR-012").update({"standing": "normative"}))
    assert any("normative but ADR-012 is not Accepted" in e for e in errors(repo))


def _codeowners(repo, text=None, append=None):
    p = repo / ".github" / "CODEOWNERS"
    if text is not None:
        p.write_text(text)
    if append:
        p.write_text(p.read_text() + append)
    return p


def test_codeowners_must_cover_the_enforcement_paths(repo):
    p = _codeowners(repo)
    p.write_text("\n".join(l for l in p.read_text().splitlines() if not l.startswith("tests/")) + "\n")
    assert any("tests/ is not owned by @timrking11-blip" in e for e in errors(repo))


def test_an_ownerless_entry_does_not_count_as_owned(repo):
    p = _codeowners(repo)
    p.write_text(p.read_text().replace("tests/ @timrking11-blip", "tests/"))
    assert any("tests/ is not owned by @timrking11-blip (effective owners: none)" in e for e in errors(repo))


@pytest.mark.parametrize("later", [
    "/tests/\n",                              # a later ownerless rule removes ownership
    "tests/\n",
    "/.github/\n",                            # ...including from CODEOWNERS and the workflows
    "tests/ @someone-else\n",                 # a later rule hands it to someone else
])
def test_a_later_rule_that_removes_or_moves_ownership_fails(repo, later):
    _codeowners(repo, append=later)
    assert any("is not owned by @timrking11-blip" in e for e in errors(repo))


def test_a_later_rule_that_restores_ownership_passes(repo):
    _codeowners(repo, append="/tests/\ntests/ @timrking11-blip\n")
    assert errors(repo) == []


@pytest.mark.parametrize("line,covered", [
    ("data/ @timrking11-blip\n", "data/runlog/"),
    ("runlog/ @timrking11-blip\n", "data/runlog/"),    # a bare directory name matches at any depth
    ("/data/master/ @timrking11-blip\n", "data/master/"),
])
def test_automated_data_paths_stay_outside_owner_review(repo, line, covered):
    _codeowners(repo, append=line)
    assert any(f"CODEOWNERS covers {covered}" in e for e in errors(repo))


@pytest.mark.parametrize("line", ["* @timrking11-blip\n", "CLAUDE.md @timrking11-blip\n", "docs/*.md @timrking11-blip\n"])
def test_patterns_that_cannot_be_evaluated_exactly_are_refused(repo, line):
    _codeowners(repo, append=line)
    assert any("so ownership is checkable" in e for e in errors(repo))


def test_owner_tokens_must_be_github_handles(repo):
    _codeowners(repo, append="tests/ timrking11-blip\n")
    assert any("must be an @user" in e for e in errors(repo))


def test_owners_for_follows_github_precedence():
    rules = va.codeowners_rules("scripts/ @a\n/scripts/x.py\nlib/ @b # trailing comment\n/a/b/ @c\n")
    assert va.owners_for("scripts/y.py", rules) == ["@a"]
    assert va.owners_for("scripts/x.py", rules) == []
    assert va.owners_for("src/lib/z.py", rules) == ["@b"]
    assert va.owners_for("x/a/b/z", rules) == []          # a middle slash anchors the pattern to the root
    assert va.owners_for("a/b/z", rules) == ["@c"]


def test_the_weekly_sync_data_pr_paths_are_not_code_owned():
    """The paths the workflow hands scripts/open_data_pr.sh are all outside CODEOWNERS."""
    import re
    wf = (ROOT / ".github" / "workflows" / "weekly-crm-sync.yml").read_text()
    paths = set()
    for block in re.findall(r"scripts/open_data_pr\.sh .*?\n(?:.*\n){2}", wf):
        paths.update(t for t in block.split() if t.startswith("data/") and "${{" not in t)
    assert paths >= {"data/master", "data/CHANGELOG.md", "data/runlog"}
    rules = va.codeowners_rules((ROOT / ".github" / "CODEOWNERS").read_text())
    assert not any(va.owners_for(p, rules) or va.owners_for(p + "/x", rules) for p in paths)


def test_a_later_rule_on_one_file_cannot_strip_the_checker_of_its_owner(repo):
    _codeowners(repo, append="/scripts/check_architecture.py\n")
    assert any("scripts/check_architecture.py is not owned by @timrking11-blip" in e for e in errors(repo))


def test_a_later_rule_cannot_give_one_data_file_an_owner(repo):
    _codeowners(repo, append="/data/master/contacts.json @someone\n")
    assert any("CODEOWNERS covers data/master/contacts.json" in e for e in errors(repo))


def test_files_beneath_a_tree_are_checked_through_bare_directory_rules(repo):
    (repo / "scripts" / "vendor").mkdir(parents=True)
    (repo / "scripts" / "vendor" / "tool.py").write_text("")
    (repo / "data" / "runs" / "run_x").mkdir(parents=True)
    (repo / "data" / "runs" / "run_x" / "manifest.json").write_text("{}")
    _codeowners(repo, append="vendor/\nrun_x/ @someone\n")
    errs = errors(repo)
    assert any("scripts/vendor/tool.py is not owned" in e for e in errs)
    assert any("CODEOWNERS covers data/runs/run_x/manifest.json" in e for e in errs)


def test_the_committed_tree_has_every_file_owned_and_no_data_file_owned():
    rules = va.codeowners_rules((ROOT / ".github" / "CODEOWNERS").read_text())
    files = va.repository_files(ROOT)
    # data/master and data/runs left the tree in #26; data/runlog and data/proposals remain.
    assert any(f.startswith("data/") for f in files) and any(f.startswith("scripts/") for f in files)
    assert all("@timrking11-blip" in va.owners_for(f, rules) for f in files if f.startswith(("scripts/", "crm/", ".github/")))
    assert not any(va.owners_for(f, rules) for f in files if f.startswith("data/"))
