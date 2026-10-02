"""The architecture checker: the YAML's schema, and what counts as a regression.

CI fails on a regression and never on an improvement. These tests pin that
line, using fake probes so they do not depend on today's implementation.
"""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_architecture as ca  # noqa: E402


def ok():
    return "fine"


def bad():
    raise ca.ProbeFailed("broken")


def probe(pid, *, kind="unit", scope="core", mnr=False):
    return {"id": pid, "what": "w", "kind": kind, "scope": scope, "target": "t", "must_not_regress": mnr}


def spec(*probes, expected="PARTIAL", requires_runtime=False, rule="every x has a y", standing="normative"):
    return {
        "schema": 1,
        "decisions": [{"id": "ADR-X", "title": "T", "url": "https://www.notion.so/x", "status": "Proposed",
                       "as_of": "2026-10-02"}],
        "invariants": [{"id": "INV-T", "decision": "D", "adr": "ADR-X", "standing": standing, "rule": rule,
                        "expected": expected,
                        "requires_runtime": requires_runtime, "probes": list(probes)}],
    }


# ---------- the real source --------------------------------------------------------------

def test_the_committed_yaml_is_valid_and_has_sixteen_rules():
    s = ca.load()
    assert ca.validate(s) == []
    assert [i["id"] for i in s["invariants"]] == [f"INV-{n:02d}" for n in range(1, 17)]


def test_every_existing_hard_control_holds_offline():
    regressions, _ = ca.verdict(ca.run(ca.load()))
    assert regressions == []


def test_the_committed_markdown_matches_the_yaml():
    s = ca.load()
    assert ca.RENDERED.read_text() == ca.render_md(s, ca.run(s))


# ---------- schema --------------------------------------------------------------------------

def test_a_rule_that_names_implementation_is_refused():
    s = spec(probe("P-1"), rule="crm.runlog.held must hold")
    assert any("names implementation" in e for e in ca.validate(s, {"P-1": ok}))


def test_decisions_live_in_notion_only():
    s = spec(probe("P-1"))
    s["decisions"][0]["url"] = "https://github.com/x/adr.md"
    assert any("Notion" in e for e in ca.validate(s, {"P-1": ok}))


def test_declared_and_implemented_probes_must_agree():
    s = spec(probe("P-1"))
    errors = ca.validate(s, {"P-2": ok})
    assert any("P-1: no probe implementation" in e for e in errors)
    assert any("P-2: implemented but not declared" in e for e in errors)


def test_only_a_written_adr_makes_a_rule_normative():
    s = spec(probe("P-1"))
    s["decisions"][0]["url"] = None
    assert any("not written in Notion; mark it candidate" in e for e in ca.validate(s, {"P-1": ok}))
    s["invariants"][0]["standing"] = "candidate"
    assert ca.validate(s, {"P-1": ok}) == []


def test_a_candidate_is_promoted_once_its_adr_exists():
    s = spec(probe("P-1"), standing="candidate")
    assert any("promote the rule to normative" in e for e in ca.validate(s, {"P-1": ok}))


def test_the_committed_candidates_are_the_rules_whose_adr_is_unwritten():
    s = ca.load()
    unwritten = {d["id"] for d in s["decisions"] if not d.get("url")}
    assert {i["id"] for i in s["invariants"] if i["standing"] == "candidate"} == \
        {i["id"] for i in s["invariants"] if i["adr"] in unwritten} == {"INV-13", "INV-14"}


def test_status_vocabulary_and_duplicates():
    s = spec(probe("P-1"), expected="DONE")
    s["invariants"].append(copy.deepcopy(s["invariants"][0]))
    errors = ca.validate(s, {"P-1": ok})
    assert any("expected must be one of" in e for e in errors)
    assert any("duplicate invariant" in e for e in errors)


# ---------- status and maturity -----------------------------------------------------------

def test_status_follows_core_probes_and_guards_do_not_count():
    [r] = ca.run(spec(probe("A"), probe("B")), probes={"A": ok, "B": ok})
    assert (r.status, r.maturity) == ("ENFORCED", "CODE_EXISTS")
    [r] = ca.run(spec(probe("A"), probe("B")), probes={"A": ok, "B": bad})
    assert r.status == "PARTIAL"
    [r] = ca.run(spec(probe("A"), probe("G", scope="guard")), probes={"A": bad, "G": ok})
    assert (r.status, r.maturity) == ("MISSING", "DESIGNED")


def test_runtime_rules_are_unverified_without_a_dump_and_never_a_regression():
    s = spec(probe("A"), probe("R", kind="runtime", mnr=True), requires_runtime=True)
    [r] = ca.run(s, probes={"A": ok, "R": bad})
    assert r.status == "UNVERIFIED"
    assert ca.verdict([r]) == ([], [])


def test_runtime_probes_run_with_a_dump(tmp_path):
    seen = []
    s = spec(probe("R", kind="runtime"), requires_runtime=True, expected="MISSING")
    [r] = ca.run(s, tmp_path, probes={"R": lambda d: seen.append(d) or "ran"})
    assert seen == [tmp_path] and (r.status, r.maturity) == ("ENFORCED", "EXECUTED")


# ---------- regression vs improvement -------------------------------------------------------

def test_a_failing_must_not_regress_probe_is_a_regression_even_when_status_holds():
    s = spec(probe("A"), probe("M", mnr=True), probe("C"))
    regressions, _ = ca.verdict(ca.run(s, probes={"A": ok, "M": bad, "C": ok}))
    assert regressions and "MUST_NOT_REGRESS" in regressions[0]


def test_falling_below_expected_is_a_regression():
    regressions, _ = ca.verdict(ca.run(spec(probe("A")), probes={"A": bad}))
    assert regressions == ["INV-T is MISSING, below its expected PARTIAL"]


def test_a_candidate_is_never_held_to_expected_but_its_hard_controls_are():
    s = spec(probe("A"), probe("M", scope="guard", mnr=True), standing="candidate")
    assert ca.verdict(ca.run(s, probes={"A": bad, "M": ok})) == ([], [])
    regressions, _ = ca.verdict(ca.run(s, probes={"A": bad, "M": bad}))
    assert len(regressions) == 1 and "MUST_NOT_REGRESS" in regressions[0]


def test_an_improvement_is_reported_not_failed():
    regressions, improvements = ca.verdict(ca.run(spec(probe("A"), expected="MISSING"), probes={"A": ok}))
    assert regressions == [] and "raise `expected`" in improvements[0]


def test_main_exits_1_on_a_must_not_regress_failure(monkeypatch, capsys):
    monkeypatch.setattr(ca, "load", lambda: spec(probe("M", mnr=True)))
    monkeypatch.setattr(ca, "PROBES", {"M": bad})
    assert ca.main([]) == 1
    assert "REGRESSION  INV-T M MUST_NOT_REGRESS failed" in capsys.readouterr().out


def test_repository_probes_do_not_depend_on_the_working_directory(monkeypatch, tmp_path):
    """Repository evidence resolves from the checker's own location; only --crm-dump is caller-relative."""
    monkeypatch.chdir(tmp_path)
    assert ca.PROBES["P-07d"]() == "confirm disabled until a check note of 12+ characters"
    results = ca.run(ca.load())
    assert ca.verdict(results)[0] == []
    assert [r.status for r in results] == [r.status for r in _OFFLINE]


_OFFLINE = ca.run(ca.load())


def test_check_md_fails_when_the_markdown_is_stale(monkeypatch, tmp_path):
    stale = tmp_path / "inv.md"
    stale.write_text("old\n")
    monkeypatch.setattr(ca, "RENDERED", stale)
    assert ca.main(["--check-md"]) == 1
    assert ca.main(["--render-md", "--check-md"]) == 0


# ---------- the runtime HITL probe -----------------------------------------------------------

def _dump(tmp_path, *docs):
    d = tmp_path / "runlog"
    d.mkdir()
    for doc in docs:
        (d / f"{doc['id']}.json").write_text(json.dumps(doc))
    return tmp_path


def test_a_bulk_creation_applied_without_a_check_fails(tmp_path):
    dump = _dump(tmp_path, {"id": "rl_b", "status": "applied", "created": 10})
    with pytest.raises(ca.ProbeFailed):
        ca.p07e(dump)


def test_a_bulk_creation_applied_by_a_confirmed_hold_passes(tmp_path):
    dump = _dump(tmp_path,
                 {"id": "rl_a", "status": "applied", "created": 10, "confirm_check": "Checked Apollo: all 10 new",
                  "confirmed_count": 10, "confirmed_at": "2026-09-28T14:00:00Z", "applied_by": "rl_b"},
                 {"id": "rl_b", "status": "applied", "created": 10})
    assert "every applied bulk creation" in ca.p07e(dump)


def test_a_confirmation_for_a_different_count_does_not_authorize(tmp_path):
    dump = _dump(tmp_path,
                 {"id": "rl_a", "status": "applied", "created": 10, "confirm_check": "Checked Apollo: all 10 new",
                  "confirmed_count": 10, "confirmed_at": "2026-09-28T14:00:00Z", "applied_by": "rl_b"},
                 {"id": "rl_b", "status": "applied", "created": 12})
    with pytest.raises(ca.ProbeFailed):
        ca.p07e(dump)


def test_a_note_never_authorizes_a_bulk_creation_after_the_hold_existed(tmp_path):
    dump = _dump(tmp_path, {"id": "rl_n", "at": "2026-10-01T06:00:00Z", "status": "applied", "created": 10,
                            "note": "looked fine"})
    with pytest.raises(ca.ProbeFailed):
        ca.p07e(dump)


def test_a_bulk_creation_from_before_the_hold_passes_with_a_note(tmp_path):
    dump = _dump(tmp_path, {"id": "rl_l", "at": "2026-09-21T06:05:45Z", "status": "applied", "created": 15,
                            "note": "Recorded from the changelog; the hold did not exist yet."})
    assert "every applied bulk creation" in ca.p07e(dump)


@pytest.mark.parametrize("hold", [
    {"confirm_check": "Checked Apollo: all 10 new", "confirmed_count": 10},                # no confirmed_at
    {"confirm_check": "ok", "confirmed_count": 10, "confirmed_at": "2026-09-28T14:00:00Z"},  # no real check
])
def test_only_a_structured_confirmation_can_authorize_another_run(tmp_path, hold):
    dump = _dump(tmp_path, {"id": "rl_a", "status": "applied", "created": 10, "applied_by": "rl_b", **hold},
                 {"id": "rl_b", "at": "2026-09-28T14:46:53Z", "status": "applied", "created": 10})
    with pytest.raises(ca.ProbeFailed, match="rl_a.*rl_b|rl_b.*rl_a"):
        ca.p07e(dump)


def test_an_undated_run_is_never_legacy(tmp_path):
    dump = _dump(tmp_path, {"id": "rl_u", "status": "applied", "created": 10, "note": "old run"})
    with pytest.raises(ca.ProbeFailed):
        ca.p07e(dump)
