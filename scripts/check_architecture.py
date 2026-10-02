#!/usr/bin/env python3
"""Check the system against architecture/invariants.yaml.

The YAML is the machine-readable source: one implementation-independent rule
per architecture decision (governed in Notion, indexed by URL under
`decisions`), each with probes that test how far today's code meets it. This
script runs the probes and reports, per rule:

  conformance  ENFORCED | PARTIAL | MISSING | UNVERIFIED
  maturity     DESIGNED | CODE_EXISTS | EXECUTED  (ADR-011's evidence levels;
               this script never claims PRODUCTION_VERIFIED, which needs
               acceptance criteria met over a window and a reviewer)

Conformance comes from the rule's `core` probes: none pass -> MISSING; all
pass -> ENFORCED; some pass -> PARTIAL. A rule marked requires_runtime is
UNVERIFIED unless --crm-dump is given. `guard` probes protect adjacent
controls: they must pass but do not move the status.

Exit 1 only on a regression: a must_not_regress probe fails, a rule ranks
below its `expected` (UNVERIFIED is never compared), the YAML breaks its
schema, or the rendered Markdown is out of date (--check-md). An improvement
prints a note asking for `expected` to be raised and exits 0.

  python3 scripts/check_architecture.py [--crm-dump DIR] [--render-md] [--check-md]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "python" / "agents" / "account-research"))

SOURCE = ROOT / "architecture" / "invariants.yaml"
RENDERED = ROOT / "docs" / "architecture-invariants.md"

STATUSES = ("ENFORCED", "PARTIAL", "MISSING", "UNVERIFIED")
RANK = {"MISSING": 0, "PARTIAL": 1, "ENFORCED": 2}
MATURITY = {"static": "CODE_EXISTS", "unit": "CODE_EXISTS", "runtime": "EXECUTED"}
MATURITY_RANK = {"DESIGNED": 0, "CODE_EXISTS": 1, "EXECUTED": 2}
KINDS = ("static", "unit", "runtime")
SCOPES = ("core", "guard")
STANDINGS = ("normative", "candidate")
#: A rule names concepts, never today's code.
IMPLEMENTATION_NAMES = re.compile(r"\bcrm\.|scripts/|\.py\b|\bdef\s|\bartifact/|_tool\b")
NOW = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- probes ----

class ProbeFailed(Exception):
    pass


def ensure(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFailed(msg)


def absent(module: str, attr: str | None = None) -> str:
    """Static probe for a concept that must exist: fails while it does not."""
    import importlib
    try:
        mod = importlib.import_module(module)
    except ImportError:
        raise ProbeFailed(f"{module} does not exist")
    if attr and not hasattr(mod, attr):
        raise ProbeFailed(f"{module}.{attr} does not exist")
    return f"{module}{'.' + attr if attr else ''} exists"


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        yield


def _proposal_md() -> str:
    from account_research.tools.write_proposal import REQUIRED_SECTIONS
    body = "\n\n".join(f"## {s}\nText about it, not found on the domain." for s in REQUIRED_SECTIONS)
    return "# Acme -- Prequalification Proposal\nPrepared by Strategic Market Insights\n\n" + body


def _record_inputs() -> tuple[dict, dict]:
    state = {"account": {"name": "Acme", "domain": "acme.example"}, "request_text": "Help us plan.",
             "coverage": {}, "web_sources": []}
    manifest = {"request": {"text": "Help us plan.", "requester": {"name": "Ada Lovelace"}},
                "state": {"account": {"domain": "acme.example", "crm_account_id": None}}}
    return state, manifest


def p02a() -> str:
    from dataclasses import fields
    from crm.schema import Provenance
    names = {f.name for f in fields(Provenance)}
    ensure(names <= {"source", "observed_at", "confidence"}, f"provenance carries interpretive fields: {sorted(names)}")
    return f"Provenance fields: {sorted(names)}"


def p04a() -> str:
    from crm.master import merge_all
    from crm.schema import Contact, SOURCE_APOLLO, SOURCE_EXPLORIUM
    base, _ = merge_all([], [Contact(email="ada@example.com", phone="+1-111")], SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, report = merge_all(base, [Contact(email="ada@example.com", phone="+1-222")], SOURCE_EXPLORIUM,
                               "2026-09-02T00:00:00+00:00")
    ensure(merged[0].phone == "+1-111", "the contradicting value overwrote the held one")
    ensure(any(c["field"] == "phone" for c in report.conflicts_held), "the contradiction was not reported")
    return "equal-trust contradiction held and reported"


def _check_run(**over) -> list[str]:
    from crm.guardrails import check_run
    manifest = {"state": {"account": {"domain": "claridi.ai"}}, "data_sources": {"allow_credit_spend": False}}
    args = dict(coverage={}, research_text="", data_sources_text="", proposal_md="not found", cited=[])
    args.update(over)
    return check_run(manifest, **args)


def p04b() -> str:
    problems = _check_run(research_text="see https://clarid.ai/about")
    ensure(any("domain lock" in p for p in problems), "a lookalike domain in research was not refused")
    return "lookalike clarid.ai refused for claridi.ai"


def p05a() -> str:
    import compose_account as compose
    with tempfile.TemporaryDirectory() as d:
        run = Path(d) / "run_x"
        run.mkdir()
        for name, data in (("manifest.json", {}), ("state.json", {}), ("review.json", {}),
                           ("run_final.json", {"proposal_id": "prq_x"})):
            (run / name).write_text(json.dumps(data))
        try:
            with quiet():
                compose.finalize(run, "x", None, [], [], {}, {}, NOW)
        except SystemExit:
            return "second filing of a run refused"
    raise ProbeFailed("a filed run was filed again")


def p05b() -> str:
    import compose_account as compose
    record = {"account": {"name": "Acme", "domain": "acme.example"}, "proposal_id": "prq_new", "run_id": "run_x",
              "proposal_markdown": "# P", "notes_appendix": "", "lead_source": None}
    accounts = {"acc_1": {"name": "Acme", "domain": "acme.example", "notes": "keep this", "activity": []}}
    w = compose.plan_account_write(record, {"state": {"account": {"crm_account_id": None}}}, accounts, [], NOW)
    ensure(w is not None and w["data"]["notes"].startswith("keep this"), "existing notes were not kept as the prefix")
    return "notes appended after the existing text"


def p06a() -> str:
    import compose_account as compose
    state, manifest = _record_inputs()
    md = _proposal_md()
    with quiet():
        a = compose.proposal_record(dict(state), manifest, "run_x", md, {}, [], NOW)["proposal_id"]
        b = compose.proposal_record(dict(state), manifest, "run_x", md, {}, [], NOW)["proposal_id"]
    ensure(a == b, "the same inputs gave different ids")
    return f"deterministic id {a}"


def p06b() -> str:
    import compose_account as compose
    state, manifest = _record_inputs()
    with quiet():
        rec = compose.proposal_record(state, manifest, "run_x", _proposal_md(), {}, [], NOW)
    ensure("fingerprint" in rec and rec["fingerprint"] != rec["proposal_id"], "no fingerprint separate from the id")
    return "fingerprint stored separately"


def p07a() -> str:
    from crm import runlog
    ensure(not runlog.held(runlog.HOLD_OVER) and runlog.held(runlog.HOLD_OVER + 1), "threshold not enforced")
    ensure(not runlog.held(10, allow_created=10) and runlog.held(11, allow_created=10), "allow is not exact-count")
    return f"holds over {runlog.HOLD_OVER}; allows only the exact confirmed count"


def p07b() -> str:
    from crm import broker
    job = broker.new_job("vibe", "enrich", ["a.example"], 10, "2026-09-25T00:00:00Z")
    ensure(broker.approve(job, {}, "owner", "2026-09-25T00:00:00Z")["status"] == "queued", "approved without a budget")
    try:
        broker.settle(job, 10, "2026-09-25T00:00:00Z")
    except ValueError:
        return "unbudgeted job queued; unapproved settle refused"
    raise ProbeFailed("an unapproved job was settled")


def p07c() -> str:
    from crm.review import CONFIRM_BY, with_check
    ensure(CONFIRM_BY in with_check("Something is off."), "a HOLD line without its check")
    return "HOLD lines end with their check"


def p07d() -> str:
    page = (ROOT / "artifact" / "crm-system.html").read_text()
    ensure("trim().length<12" in page and "confirm_check" in page, "the confirm no longer requires a check note")
    return "confirm disabled until a check note of 12+ characters"


#: The bulk-creation hold arrived with the run log (f1ef3a4, 25 Sep 2026 03:52 UTC). A bulk
#: creation applied before then could not have been confirmed; it passes only with a note
#: saying so. After it, a note is never an authorization.
HOLD_CUTOVER = "2026-09-25T03:52:14Z"
#: The CRM page refuses a confirmation whose check note is shorter than this.
MIN_CHECK = 12


def _confirmed(d: dict) -> bool:
    """Structured confirmation: a written check, when, and exactly this count."""
    return (len((d.get("confirm_check") or "").strip()) >= MIN_CHECK and bool(d.get("confirmed_at"))
            and d.get("confirmed_count") == d.get("created"))


def p07e(dump: Path) -> str:
    docs = [json.loads(p.read_text()) for p in (dump / "runlog").glob("*.json")]
    ensure(docs, f"no runlog documents under {dump / 'runlog'}")
    from crm import runlog
    docs = [d.get("data", d) for d in docs]
    # A confirmed hold may be applied by a later run that writes its own entry: the hold names
    # that entry in `applied_by`, and only a fully confirmed hold can authorize it.
    authorized = {(d["applied_by"], d["confirmed_count"]) for d in docs if _confirmed(d) and d.get("applied_by")}
    bad = []
    for d in docs:
        if d.get("confirmed_at") or d.get("confirm_check") or d.get("status") == "confirmed":
            if not _confirmed(d):
                bad.append(d.get("id"))
        elif d.get("status") == "applied" and (d.get("created") or 0) > runlog.HOLD_OVER:
            at = d.get("at") or ""
            legacy = bool(at) and at < HOLD_CUTOVER and bool((d.get("note") or "").strip())
            if not legacy and (d.get("id"), d.get("created")) not in authorized:
                bad.append(d.get("id"))
    ensure(not bad, f"bulk creations without a structured confirmation: {bad}")
    return f"{len(docs)} runlog documents; every applied bulk creation has its confirmation"


def p08b() -> str:
    problems = _check_run(proposal_md="Acme makes widgets.")
    ensure(any("empty means empty" in p for p in problems), "a not-found account was described anyway")
    return "not-found output must say so"


def p08c() -> str:
    problems = _check_run(coverage={"apollo": "ok: enriched"})
    ensure(any("credit spend" in p for p in problems), "unpermitted paid enrichment was not refused")
    return "paid enrichment without permission refused"


def p08d() -> str:
    from crm.crm_sync import assert_not_owned
    try:
        assert_not_owned({"stage": "won"})
    except ValueError:
        return "write to stage refused"
    raise ProbeFailed("a write to a human-owned field passed")


def p08e() -> str:
    from account_research.tools.write_proposal import _MONEY
    ensure(bool(_MONEY.search("About $2,000 per month.")), "a price in a proposal is not caught")
    return "a price in a proposal is refused"


def p09b() -> str:
    import merge_master
    from crm import config, runlog
    from crm.schema import Contact
    saved = {k: getattr(config, k) for k in ("DATA_DIR", "MASTER_CONTACTS", "CHANGELOG", "APOLLO_STAGING",
                                             "EXPLORIUM_STAGING", "LINKEDIN_STAGING")}
    saved_rl, saved_argv = runlog.RUNLOG_DIR, sys.argv
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        try:
            config.DATA_DIR, config.MASTER_CONTACTS, config.CHANGELOG = t, t / "master" / "contacts.json", t / "CHANGELOG.md"
            config.APOLLO_STAGING, config.EXPLORIUM_STAGING = t / "staging" / "apollo.json", t / "staging" / "explorium.json"
            config.LINKEDIN_STAGING, runlog.RUNLOG_DIR = t / "staging" / "linkedin.json", t / "runlog"
            (t / "staging").mkdir(parents=True)
            people = [Contact(first_name=f"P{i}", last_name="New", email=f"p{i}@new.example", apollo_contact_id=f"ap{i}",
                              sources=["apollo"]).to_dict() for i in range(runlog.HOLD_OVER + 1)]
            config.APOLLO_STAGING.write_text(json.dumps({"observed_at": "2026-09-28T06:00:00Z", "contacts": people}))
            sys.argv = ["merge_master.py"]
            with quiet():
                rc = merge_master.main()
            ensure(rc == 0 and not config.MASTER_CONTACTS.exists(), "a held merge wrote master")
        finally:
            for k, v in saved.items():
                setattr(config, k, v)
            runlog.RUNLOG_DIR, sys.argv = saved_rl, saved_argv
    return f"{runlog.HOLD_OVER + 1} new contacts: master not written"


def p10a() -> str:
    from crm.crm_sync import pinned
    ensure(pinned({"_version": 4}, {"op": "update"}).get("if_version") == 4, "a known version was not pinned")
    return "write pinned to the version read"


def p10b() -> str:
    from crm.schema import Contact
    from crm.master import save_master
    from validate_sync import Report, check_master
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "contacts.json"
        save_master([Contact(contact_id="c1", apollo_contact_id="ap1", sources=["apollo"]),
                     Contact(contact_id="c2", apollo_contact_id="ap1", sources=["apollo"])], path)
        report = Report()
        with quiet():
            check_master(report, path)
    ensure(not report.ok, "a duplicate identity passed validation")
    return "duplicate apollo id fails validation"


def p11a() -> str:
    from crm.activity import TYPES
    from crm.crm_sync import PROPOSAL_STATUSES
    ensure({"reply", "meeting"} <= set(TYPES) and {"accepted", "declined"} <= set(PROPOSAL_STATUSES), "outcome kinds missing")
    return "replies, meetings and proposal outcomes are recordable"


def p11b() -> str:
    import inspect
    from crm.activity import row
    ensure("action_ref" in inspect.signature(row).parameters, "outcomes carry no action reference")
    return "outcomes reference their action"


def p12a() -> str:
    from crm.activity import scorecard
    docs = {"c1": {"activity": [{"type": "email", "direction": "out", "ts": "2026-09-25"},
                                {"type": "reply", "direction": "in", "ts": "2026-09-26"}]}}
    card = scorecard(docs)
    ensure(card["first_touches"] == 1 and card["replies"] == 1, f"scorecard not computed from rows: {card}")
    return "scorecard computed from activity rows"


def p14b() -> str:
    from crm.broker import budget_check
    ensure(not budget_check({}, "vibe", 10).ok, "spend allowed with no balance read")
    ensure(not budget_check({"providers": {"vibe": {"balance": 100}}}, "vibe", 10).ok, "spend allowed with no floor")
    return "spend fails closed"


def p15a() -> str:
    from crm.master import merge_all
    from crm.schema import Contact, SOURCE_APOLLO
    master, _ = merge_all([], [Contact(first_name="Ada", email="ada@example.com", title="CEO")], SOURCE_APOLLO,
                          "2026-09-01T00:00:00+00:00")
    prov = master[0].provenance
    ensure(all(prov.get(f, {}).get("source") == SOURCE_APOLLO and prov[f].get("observed_at")
               for f in ("email", "title")), f"fields without provenance: {prov}")
    return "every merged field names its source and time"


def p15b(dump: Path) -> str:
    from crm.crm_sync import load_crm_dump
    docs = load_crm_dump(dump)
    ensure(docs, f"no contacts under {dump / 'contacts'}")
    bad = [k for k, d in docs.items() if not d.get("provenance") or not d.get("master_id")]
    ensure(not bad, f"{len(bad)} CRM contact(s) without provenance or master key: {bad[:5]}")
    return f"{len(docs)} CRM contacts carry provenance and a master key"


def p16a() -> str:
    import compose_account as compose
    state, manifest = _record_inputs()
    with quiet():
        rec = compose.proposal_record(state, manifest, "run_x", _proposal_md(), {}, [], NOW)
    ensure(bool(rec.get("model")), "no model on the record")
    return f"model recorded ({rec['model']})"


def p16b() -> str:
    import compose_account as compose
    state, manifest = _record_inputs()
    with quiet():
        rec = compose.proposal_record(state, manifest, "run_x", _proposal_md(), {}, [], NOW)
    missing = [k for k in ("prompt_hash", "policy_version", "code_version") if k not in rec]
    ensure(not missing, f"missing {missing}")
    return "audit fields present"


PROBES: dict[str, Callable[..., str]] = {
    "P-01a": lambda: absent("crm.signal", "Signal"),
    "P-02a": p02a, "P-02b": lambda: absent("crm.evidence", "Evidence"),
    "P-03a": lambda: absent("crm.hypothesis", "Hypothesis"),
    "P-04a": p04a, "P-04b": p04b, "P-04c": lambda: absent("crm.evidence", "Evidence"),
    "P-05a": p05a, "P-05b": p05b, "P-05c": lambda: absent("crm.snapshot", "StateSnapshot"),
    "P-06a": p06a, "P-06b": p06b,
    "P-07a": p07a, "P-07b": p07b, "P-07c": p07c, "P-07d": p07d, "P-07e": p07e,
    "P-07f": lambda: absent("crm.authorization", "ActionAuthorization"),
    "P-08a": p04b, "P-08b": p08b, "P-08c": p08c, "P-08d": p08d, "P-08e": p08e,
    "P-08f": lambda: absent("crm.policy", "PolicyGate"),
    "P-09a": p07b, "P-09b": p09b, "P-09c": lambda: absent("crm.executor", "execute"),
    "P-10a": p10a, "P-10b": p10b, "P-10c": lambda: absent("crm.executor", "POSTCONDITIONS"),
    "P-11a": p11a, "P-11b": p11b,
    "P-12a": p12a, "P-12b": lambda: absent("crm.evaluation", "Evaluation"),
    "P-13a": lambda: absent("crm.calibration"),
    "P-14a": lambda: absent("crm.research_planner"), "P-14b": p14b,
    "P-15a": p15a, "P-15b": p15b, "P-15c": lambda: absent("crm.provenance", "ProvenanceEdge"),
    "P-16a": p16a, "P-16b": p16b,
}


# ---------------------------------------------------------------- engine ----

@dataclass
class ProbeResult:
    id: str
    kind: str
    scope: str
    mnr: bool
    outcome: str          # pass | fail | skipped
    evidence: str


@dataclass
class RuleResult:
    id: str
    decision: str
    adr: str
    expected: str
    status: str
    maturity: str
    standing: str = "normative"
    probes: list[ProbeResult] = field(default_factory=list)


def load(path: Path = SOURCE) -> dict[str, Any]:
    import yaml
    return yaml.safe_load(path.read_text())


def validate(spec: dict[str, Any], probes: dict[str, Callable] | None = None) -> list[str]:
    probes = PROBES if probes is None else probes
    errors = []
    if spec.get("schema") != 1:
        errors.append("schema must be 1")
    adrs = {d["id"]: d for d in spec.get("decisions") or []}
    for d in adrs.values():
        if d.get("url") and "notion" not in d["url"]:
            errors.append(f"{d['id']}: decisions are governed in Notion; url must be a Notion link")
    seen, probe_ids = set(), set()
    for inv in spec.get("invariants") or []:
        iid = inv.get("id")
        if iid in seen:
            errors.append(f"duplicate invariant {iid}")
        seen.add(iid)
        for key in ("decision", "adr", "standing", "rule", "expected", "requires_runtime", "probes"):
            if key not in inv:
                errors.append(f"{iid}: missing {key}")
        if inv.get("adr") not in adrs:
            errors.append(f"{iid}: adr {inv.get('adr')} is not in decisions")
        elif inv.get("standing") not in STANDINGS:
            errors.append(f"{iid}: standing must be one of {list(STANDINGS)}")
        # Notion governs: only a written ADR makes a rule normative, and a written one makes it so.
        elif inv["standing"] == "normative" and not adrs[inv["adr"]].get("url"):
            errors.append(f"{iid}: normative, but {inv['adr']} is not written in Notion; mark it candidate")
        elif inv["standing"] == "candidate" and adrs[inv["adr"]].get("url"):
            errors.append(f"{iid}: {inv['adr']} now exists in Notion; promote the rule to normative")
        if inv.get("expected") not in RANK:
            errors.append(f"{iid}: expected must be one of {list(RANK)}")
        if IMPLEMENTATION_NAMES.search(inv.get("rule") or ""):
            errors.append(f"{iid}: the rule names implementation; move it to a probe target")
        for p in inv.get("probes") or []:
            pid = p.get("id")
            if pid in probe_ids:
                errors.append(f"duplicate probe {pid}")
            probe_ids.add(pid)
            if p.get("kind") not in KINDS or p.get("scope") not in SCOPES:
                errors.append(f"{pid}: kind must be {KINDS}, scope {SCOPES}")
            if pid not in probes:
                errors.append(f"{pid}: no probe implementation")
    for pid in probes:
        if pid not in probe_ids:
            errors.append(f"{pid}: implemented but not declared in the YAML")
    return errors


def run(spec: dict[str, Any], crm_dump: Path | None = None,
        probes: dict[str, Callable] | None = None) -> list[RuleResult]:
    probes = PROBES if probes is None else probes
    results = []
    for inv in spec["invariants"]:
        rr = RuleResult(inv["id"], inv["decision"], inv["adr"], inv["expected"], "", "DESIGNED", inv["standing"])
        for p in inv["probes"]:
            pr = ProbeResult(p["id"], p["kind"], p["scope"], bool(p.get("must_not_regress")), "skipped", "")
            if p["kind"] == "runtime" and crm_dump is None:
                pr.evidence = "needs --crm-dump"
            else:
                try:
                    fn = probes[p["id"]]
                    pr.evidence = fn(crm_dump) if p["kind"] == "runtime" else fn()
                    pr.outcome = "pass"
                except ProbeFailed as e:
                    pr.outcome, pr.evidence = "fail", str(e)
                except Exception as e:  # a probe that crashes is a failed probe, said plainly
                    pr.outcome, pr.evidence = "fail", f"{type(e).__name__}: {e}"
            rr.probes.append(pr)
        core = [p for p in rr.probes if p.scope == "core"]
        ran = [p for p in core if p.outcome != "skipped"]
        passed = [p for p in ran if p.outcome == "pass"]
        if inv.get("requires_runtime") and crm_dump is None:
            rr.status = "UNVERIFIED"
        elif not passed:
            rr.status = "MISSING"
        elif len(passed) == len(core):
            rr.status = "ENFORCED"
        else:
            rr.status = "PARTIAL"
        for p in core:  # guards protect adjacent controls; they say nothing about this rule's maturity
            if p.outcome == "pass" and MATURITY_RANK[MATURITY[p.kind]] > MATURITY_RANK[rr.maturity]:
                rr.maturity = MATURITY[p.kind]
        results.append(rr)
    return results


def verdict(results: list[RuleResult]) -> tuple[list[str], list[str]]:
    """(regressions, improvements)."""
    regressions, improvements = [], []
    for r in results:
        for p in r.probes:
            if p.mnr and p.outcome == "fail":
                regressions.append(f"{r.id} {p.id} MUST_NOT_REGRESS failed: {p.evidence}")
        if r.status in RANK and r.standing == "normative":  # a candidate is reported, not held to a line
            if RANK[r.status] < RANK[r.expected]:
                regressions.append(f"{r.id} is {r.status}, below its expected {r.expected}")
            elif RANK[r.status] > RANK[r.expected]:
                improvements.append(f"{r.id} is {r.status}, above its expected {r.expected}: raise `expected`")
    return regressions, improvements


# -------------------------------------------------------------- markdown ----

def render_md(spec: dict[str, Any], results: list[RuleResult]) -> str:
    adrs = {d["id"]: d for d in spec["decisions"]}
    by_id = {r.id: r for r in results}
    out = ["# Architecture invariants", "",
           "Rendered by `scripts/check_architecture.py --render-md` from `architecture/invariants.yaml`; "
           "CI fails when this file and the YAML disagree. Do not edit by hand.", "",
           "Decisions are governed in Notion; the repository holds their executable form. Conformance is "
           "ENFORCED, PARTIAL, MISSING, or UNVERIFIED (needs `--crm-dump`). Maturity uses ADR-011's "
           "evidence levels; this check never claims PRODUCTION_VERIFIED. Status below is the offline run.", "",
           "A normative rule's ADR is written in Notion and CI holds it at its expected status. A candidate "
           "rule is a design target whose ADR is not written yet: it is reported, never held to a line; its "
           "MUST_NOT_REGRESS probes still fail CI, because they protect controls that exist today.", "",
           "## Governing decisions", "", "| ADR | Title | Status (as of) |", "|---|---|---|"]
    for d in spec["decisions"]:
        title = f"[{d['title']}]({d['url']})" if d.get("url") else d["title"]
        out.append(f"| {d['id']} | {title} | {d['status']} ({d['as_of']}) |")
    out += ["", "## Invariants", "", "| ID | Decision | ADR | Standing | Rule | Expected | Offline | Maturity |",
            "|---|---|---|---|---|---|---|---|"]
    for inv in spec["invariants"]:
        r = by_id[inv["id"]]
        rule = " ".join(inv["rule"].split()).replace("|", "\\|")
        out.append(f"| {inv['id']} | {inv['decision']} | {inv['adr']} | {inv['standing']} | {rule} | {inv['expected']} "
                   f"| {r.status} | {r.maturity} |")
    out += ["", "## Probes", "", "MNR = MUST_NOT_REGRESS: an existing hard control that CI never lets weaken.", "",
            "| Probe | Rule | Kind | Scope | MNR | What it checks | Target today |", "|---|---|---|---|---|---|---|"]
    for inv in spec["invariants"]:
        for p in inv["probes"]:
            out.append(f"| {p['id']} | {inv['id']} | {p['kind']} | {p['scope']} | {'yes' if p.get('must_not_regress') else ''} "
                       f"| {p['what']} | `{p['target']}` |")
    out += ["", "## Gaps to ENFORCED", ""]
    for inv in spec["invariants"]:
        for g in inv.get("gaps") or []:
            out.append(f"- **{inv['id']}** ({adrs[inv['adr']]['id']}): {g}")
    return "\n".join(out) + "\n"


def report(results: list[RuleResult]) -> str:
    lines = []
    for r in results:
        held = f"expected {r.expected:<8}" if r.standing == "normative" else "candidate        "
        lines.append(f"{r.id}  {r.status:<10} {r.maturity:<11} {held} {r.decision} ({r.adr})")
        for p in r.probes:
            mark = {"pass": "ok  ", "fail": "FAIL", "skipped": "--  "}[p.outcome]
            lines.append(f"    {mark} {p.id} {p.kind:<7}{' MNR' if p.mnr else '    '}  {p.evidence}")
    counts = {s: sum(r.status == s for r in results) for s in STATUSES}
    lines.append("totals: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crm-dump", type=Path, default=None, help="ArtifactData dump with contacts/ and runlog/")
    ap.add_argument("--render-md", action="store_true", help="write docs/architecture-invariants.md")
    ap.add_argument("--check-md", action="store_true", help="fail when the rendered Markdown is out of date")
    args = ap.parse_args(argv)

    spec = load()
    errors = validate(spec)
    if errors:
        print("SCHEMA\n  " + "\n  ".join(errors))
        return 1
    results = run(spec, args.crm_dump)
    print(report(results))
    regressions, improvements = verdict(results)

    offline = results if args.crm_dump is None else run(spec, None)
    md = render_md(spec, offline)
    if args.render_md:
        RENDERED.write_text(md)
        print(f"wrote {RENDERED.name}")
    if args.check_md and (not RENDERED.exists() or RENDERED.read_text() != md):
        regressions.append(f"{RENDERED.name} is out of date: run --render-md")
    for i in improvements:
        print("IMPROVED  " + i)
    for r in regressions:
        print("REGRESSION  " + r)
    print("OK: no regressions" if not regressions else f"FAILED: {len(regressions)} regression(s)")
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
