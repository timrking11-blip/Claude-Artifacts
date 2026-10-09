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
