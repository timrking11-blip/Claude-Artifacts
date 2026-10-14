"""The AI Action Contract and decision record (ADR-006, SPEC-003). One rule per test."""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm import decision as dc  # noqa: E402

INPUTS = {"account": "org_8f3a", "run": "run_20261014_x", "evidence": ["SRC-001", "SRC-002"]}
NOW = "2026-10-14T15:00:00Z"


def contract(kind="send", approval="human", **kw):
    return dc.ActionContract(inputs=INPUTS, evidence=("SRC-001",), confidence=0.6,
                             interpretation="The founder asked for a plan; a call is the next step",
                             proposed_action={"kind": kind, "target": "contact:c_12", "summary": "Send the note"},
                             write_scope=("gmail:draft",), approval_requirement=approval, **kw)


def rec(**kw):
    c = kw.pop("contract", contract())
    return dc.record(c, ["org_8f3a"], "policy:v1", "claude-opus-5-5", "prompt:3b9c1e", "Fits archetype GTB", **kw)


def test_contract_carries_every_adr_006_field():
    fields = set(dc.ActionContract.__dataclass_fields__)
    assert {"inputs", "evidence", "confidence", "interpretation", "proposed_action", "write_scope",
            "approval_requirement", "execution_result", "observed_outcome", "contract_version"} <= fields


def test_id_is_opaque_and_fingerprint_is_separate():
    a, b = rec(), rec()
    assert a.id != b.id and a.id.startswith("dec_")
    assert a.fingerprint == b.fingerprint  # same inputs, policy, model, prompt
    other = dc.record(contract(), ["org_8f3a"], "policy:v2", "claude-opus-5-5", "prompt:3b9c1e", "r")
    assert other.fingerprint != a.fingerprint


def test_a_tampered_fingerprint_is_refused():
    r = replace(rec(), fingerprint="fp_0")
    assert any("fingerprint does not match" in e for e in dc.validate(r))


@pytest.mark.parametrize("kind", dc.CONSEQUENTIAL_ACTIONS)
def test_consequential_actions_require_human_approval(kind):
    with pytest.raises(ValueError, match="requires human approval"):
        rec(contract=contract(kind=kind, approval="none"))


def test_routine_action_may_run_without_approval():
    r = rec(contract=contract(kind="note_append", approval="none"), decision="approved", decided_at=NOW)
    assert dc.validate(r) == []


def test_an_approved_consequential_decision_names_its_reviewer_and_time():
    with pytest.raises(ValueError, match="names its reviewer"):
        rec(decision="approved", decided_at=NOW)
    with pytest.raises(ValueError, match="decided_at"):
        rec(decision="approved", reviewer="Timothy King")
    assert rec(decision="approved", reviewer="Timothy King", decided_at=NOW)


def test_execution_needs_approval_and_outcome_needs_execution():
    with pytest.raises(ValueError, match="only for an approved"):
        rec(contract=contract(execution_result={"ok": True}))
    with pytest.raises(ValueError, match="only for an executed"):
        rec(contract=contract(observed_outcome={"reply": True}), decision="approved",
            reviewer="Timothy King", decided_at=NOW)


def test_policy_model_and_prompt_versions_are_required():
    with pytest.raises(ValueError, match="INV-16"):
        dc.record(contract(), ["org_8f3a"], "", "claude-opus-5-5", "prompt:3b9c1e", "r")


def test_unknown_action_kind_and_empty_write_scope_are_refused():
    with pytest.raises(ValueError, match="proposed_action.kind"):
        rec(contract=replace(contract(), proposed_action={"kind": "teleport"}))
    with pytest.raises(ValueError, match="write_scope"):
        rec(contract=replace(contract(), write_scope=()))


def test_the_ledger_is_append_only():
    first = rec()
    ledger = dc.append([], first)
    with pytest.raises(ValueError, match="never written twice"):
        dc.append(ledger, first)
    approved = dc.supersede(first, decision="approved", reviewer="Timothy King", decided_at=NOW)
    assert approved.supersedes == first.id and first.decision == "pending"  # the old record is untouched
    ledger = dc.append(ledger, approved)
    assert dc.current(ledger) == [approved]
    branch = dc.supersede(first, decision="rejected", reviewer="Timothy King", decided_at=NOW)
    with pytest.raises(ValueError, match="already superseded"):
        dc.append(ledger, branch)
    stray = dc.supersede(rec(), decision="deferred", reviewer="Timothy King", decided_at=NOW)
    with pytest.raises(ValueError, match="not in the ledger"):
        dc.append(ledger, stray)


def test_round_trip_to_plain_data():
    d = rec().to_dict()
    assert d["contract"]["proposed_action"]["kind"] == "send" and d["id"].startswith("dec_")
