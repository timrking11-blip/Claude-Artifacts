"""The AI Action Contract and the decision record (ADR-006, Accepted 14 Oct 2026; SPEC-003).

ADR-006: "Every agent action must use a versioned contract containing inputs,
evidence, confidence, interpretation, proposed action, write scope, approval
requirement, execution result, and observed outcome." `ActionContract` is that
contract, field for field. `DecisionRecord` is what a reviewer's decision on one
contract leaves behind, so the decision can be reproduced and audited (INV-06,
INV-16).

Rules this module enforces (`validate`, `append`):
  - The record's id is opaque and unique. Its fingerprint is separate: a hash of
    the inputs, the policy version, the model and the prompt (or rule) version.
    Two records with equal fingerprints were made from the same inputs under the
    same policy.
  - A consequential action (a send, a spend, a stage change, a bulk create, a
    publication, any write outside the CRM) requires human approval, and an
    approved one names its reviewer and when they decided.
  - An execution result exists only for an approved contract, and an observed
    outcome only for an executed one.
  - The ledger is append-only. A change is a new record that supersedes the old
    one; a record is superseded at most once and never edited.

Pure, like the rest of crm/: no store and no writer. Where records are kept is
the producer's concern under its own rules; nothing here writes to the CRM.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any

CONTRACT_VERSION = "1"
#: Actions that change something a person owns, reach outside the CRM, or cost money (INV-08).
CONSEQUENTIAL_ACTIONS = ("send", "spend", "stage_change", "bulk_create", "publish", "external_write")
#: Actions that only write within a scope an existing control already bounds.
ROUTINE_ACTIONS = ("crm_field_fill", "note_append", "activity_append", "ledger_write", "report")
ACTION_KINDS = CONSEQUENTIAL_ACTIONS + ROUTINE_ACTIONS
APPROVAL_REQUIREMENTS = ("human", "none")
DECISIONS = ("pending", "approved", "rejected", "deferred")


@dataclass(frozen=True)
class ActionContract:
    """ADR-006's contract, one field per item it lists."""

    inputs: dict[str, Any]
    evidence: tuple[str, ...]
    confidence: float | None
    interpretation: str
    proposed_action: dict[str, Any]          # {"kind": one of ACTION_KINDS, "target": ..., "summary": ...}
    write_scope: tuple[str, ...]             # e.g. ("crm:contacts.notes",) or ("apollo:sequence:<id>",)
    approval_requirement: str
    execution_result: dict[str, Any] | None = None
    observed_outcome: dict[str, Any] | None = None
    contract_version: str = CONTRACT_VERSION

    @property
    def consequential(self) -> bool:
        return self.proposed_action.get("kind") in CONSEQUENTIAL_ACTIONS


@dataclass(frozen=True)
class DecisionRecord:
    id: str
    fingerprint: str
    subject_ids: tuple[str, ...]
    contract: ActionContract
    policy_version: str
    model: str                               # model id, or "rule" for a deterministic rule
    prompt_version: str                      # prompt hash, or the rule's version
    rationale: str
    alternatives: tuple[str, ...] = ()
    decision: str = "pending"
    reviewer: str | None = None
    decided_at: str | None = None
    execution_id: str | None = None
    supersedes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), default=list))


def fingerprint(inputs: dict[str, Any], policy_version: str, model: str, prompt_version: str) -> str:
    """H(inputs, policy, model, prompt). Separate from the id, which says nothing about the inputs."""
    blob = json.dumps({"inputs": inputs, "policy": policy_version, "model": model, "prompt": prompt_version},
                      sort_keys=True, separators=(",", ":"), default=str)
    return "fp_" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def new_id() -> str:
    """Opaque and unique: never derived from the inputs."""
    return "dec_" + uuid.uuid4().hex


def record(contract: ActionContract, subject_ids: list[str] | tuple[str, ...], policy_version: str, model: str,
           prompt_version: str, rationale: str, **rest: Any) -> DecisionRecord:
    """A new decision record with its id and fingerprint. Raises ValueError if `validate` would refuse it."""
    rec = DecisionRecord(id=new_id(), fingerprint=fingerprint(contract.inputs, policy_version, model, prompt_version),
                         subject_ids=tuple(subject_ids), contract=contract, policy_version=policy_version, model=model,
                         prompt_version=prompt_version, rationale=rationale,
                         alternatives=tuple(rest.pop("alternatives", ()) or ()), **rest)
    errors = validate(rec)
    if errors:
        raise ValueError("; ".join(errors))
    return rec


def _ts_ok(value: str | None) -> bool:
    if not value:
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def validate(rec: DecisionRecord) -> list[str]:
    c, errors = rec.contract, []
    if c.contract_version != CONTRACT_VERSION:
        errors.append(f"contract_version {c.contract_version!r} is not {CONTRACT_VERSION!r}")
    kind = c.proposed_action.get("kind")
    if kind not in ACTION_KINDS:
        errors.append(f"proposed_action.kind {kind!r} not in {ACTION_KINDS}")
    if c.approval_requirement not in APPROVAL_REQUIREMENTS:
        errors.append(f"approval_requirement {c.approval_requirement!r} not in {APPROVAL_REQUIREMENTS}")
    if c.consequential and c.approval_requirement != "human":
        errors.append(f"a {kind} is consequential and requires human approval")
    if not c.write_scope:
        errors.append("write_scope is required: name what the action may write, even if it is a report")
    if c.confidence is not None and not (isinstance(c.confidence, (int, float)) and 0 <= c.confidence <= 1):
        errors.append("confidence must be between 0 and 1")
    if not rec.subject_ids:
        errors.append("subject_ids is required (stored keys of the records the decision is about)")
    if not (rec.policy_version and rec.model and rec.prompt_version):
        errors.append("policy_version, model and prompt_version are required (INV-16)")
    if rec.fingerprint != fingerprint(c.inputs, rec.policy_version, rec.model, rec.prompt_version):
        errors.append("fingerprint does not match the inputs, policy, model and prompt")
    if rec.id == rec.fingerprint or not rec.id.startswith("dec_"):
        errors.append("id must be opaque (dec_…) and separate from the fingerprint")
    if rec.decision not in DECISIONS:
        errors.append(f"decision {rec.decision!r} not in {DECISIONS}")
    if rec.decision != "pending":
        if not _ts_ok(rec.decided_at):
            errors.append("a decided record needs decided_at with a time zone")
        if c.approval_requirement == "human" and not rec.reviewer:
            errors.append("a decision that requires human approval names its reviewer")
    if c.execution_result is not None and rec.decision != "approved":
        errors.append("an execution result exists only for an approved contract")
    if c.observed_outcome is not None and c.execution_result is None:
        errors.append("an observed outcome exists only for an executed action")
    return errors


def supersede(old: DecisionRecord, **changes: Any) -> DecisionRecord:
    """A new record that replaces `old`. `old` is not touched."""
    contract = changes.pop("contract", old.contract)
    base = replace(old, contract=contract, supersedes=old.id, **changes)
    new = replace(base, id=new_id(), fingerprint=fingerprint(contract.inputs, base.policy_version, base.model,
                                                             base.prompt_version))
    errors = validate(new)
    if errors:
        raise ValueError("; ".join(errors))
    return new


def append(ledger: list[DecisionRecord], rec: DecisionRecord) -> list[DecisionRecord]:
    """Append-only: a new list with `rec` at the end. Refuses duplicates and a second supersession."""
    errors = validate(rec)
    if errors:
        raise ValueError("; ".join(errors))
    ids = {r.id for r in ledger}
    if rec.id in ids:
        raise ValueError(f"{rec.id} is already in the ledger; a record is never written twice")
    if rec.supersedes is not None:
        if rec.supersedes not in ids:
            raise ValueError(f"{rec.id} supersedes {rec.supersedes}, which is not in the ledger")
        if any(r.supersedes == rec.supersedes for r in ledger):
            raise ValueError(f"{rec.supersedes} is already superseded; supersede the newer record instead")
    return [*ledger, rec]


def current(ledger: list[DecisionRecord]) -> list[DecisionRecord]:
    """The records nothing supersedes."""
    replaced = {r.supersedes for r in ledger if r.supersedes}
    return [r for r in ledger if r.id not in replaced]
