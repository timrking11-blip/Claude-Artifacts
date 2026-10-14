"""The evidence ledger (docs/research-profiles.md): one schema, two profiles, four integrity rules."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm import ledger as lg  # noqa: E402

FULL = json.loads((ROOT / "tests" / "fixtures" / "evidence_ledger_full.json").read_text(encoding="utf-8"))
LEAN = json.loads((ROOT / "tests" / "fixtures" / "evidence_ledger_lean.json").read_text(encoding="utf-8"))
DRAFT_SCHEMA = ROOT / "drafts" / "research-design-agents" / "schemas" / "ledger.schema.json"


def _cli():
    spec = importlib.util.spec_from_file_location("validate_ledger", ROOT / "scripts" / "validate_ledger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def edited(base, fn):
    d = copy.deepcopy(base)
    fn(d)
    return d


def test_the_examples_pass():
    assert lg.validate(FULL) == []
    assert lg.validate(LEAN) == []


def test_there_is_one_schema():
    """The research-design plugin staged in drafts/ carries a byte-identical copy until it moves out."""
    assert DRAFT_SCHEMA.read_bytes() == lg.SCHEMA_PATH.read_bytes()


def test_required_fields_come_from_the_schema():
    s = json.loads(lg.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert lg.required("lean")["sources"] == s["properties"]["sources"]["items"]["required"]
    assert lg.required("full")["sources"] == s["allOf"][0]["then"]["properties"]["sources"]["items"]["required"]
    assert "search_log" in lg.required("full")["ledger"] and "search_log" not in lg.required("lean")["ledger"]


# ---- the three rules the owner named, in both profiles ----

@pytest.mark.parametrize("base", [FULL, LEAN], ids=["full", "lean"])
def test_every_claim_cites_an_existing_source(base):
    bad = edited(base, lambda d: d["claims"][0].update(source_ids=["SRC-404"]))
    assert any("cites SRC-404, which is not in the source register" in e for e in lg.validate(bad))


@pytest.mark.parametrize("base", [FULL, LEAN], ids=["full", "lean"])
def test_every_quote_has_its_locator(base):
    bad = edited(base, lambda d: d["sources"][0].update(quote="We are hiring", locator=""))
    assert any("a quote needs its locator" in e for e in lg.validate(bad))
    quoted_excerpt = edited(base, lambda d: (d["sources"][0].pop("quote", None),
                                             d["sources"][0].update(excerpt='"We are hiring"', locator="")))
    assert any("a quote needs its locator" in e for e in lg.validate(quoted_excerpt))


@pytest.mark.parametrize("base", [FULL, LEAN], ids=["full", "lean"])
def test_every_source_has_an_access_date(base):
    for value in (None, "", "last week"):
        bad = edited(base, lambda d: d["sources"][0].update(accessed=value))
        assert any("needs an access date" in e for e in lg.validate(bad)), value


# ---- the rest of the integrity rules ----

def test_a_fact_rests_on_a_reviewed_source():
    bad = edited(FULL, lambda d: d["claims"][0].update(source_ids=["SRC-002"]))  # SRC-002 is a listing only
    assert any("a FACT needs a reviewed source" in e for e in lg.validate(bad))
    uncited = edited(FULL, lambda d: d["claims"][0].update(source_ids=[]))
    assert any("a FACT cites at least one source" in e for e in lg.validate(uncited))


def test_an_inference_may_rest_on_unreviewed_sources():
    assert lg.validate(FULL) == [] and FULL["claims"][1]["status"] == "INFERENCE"


def test_ids_are_unique_and_well_formed():
    dup = edited(FULL, lambda d: d["sources"].append(copy.deepcopy(d["sources"][0])))
    assert any("SRC-001: listed twice" in e for e in lg.validate(dup))
    odd = edited(FULL, lambda d: d["claims"][0].update(id="C1"))
    assert any("id must look like CLAIM-001" in e for e in lg.validate(odd))


def test_contradictions_and_supersessions_point_at_real_records():
    bad = edited(FULL, lambda d: (d["contradictions"].append(
        {"id": "CONTRA-001", "claim_ids": ["CLAIM-009"], "source_ids": ["SRC-009"], "note": "n", "status": "open"}),
        d["claims"][0].update(superseded_by="CLAIM-077")))
    errors = lg.validate(bad)
    assert any("names CLAIM-009" in e for e in errors) and any("names SRC-009" in e for e in errors)
    assert any("superseded_by CLAIM-077" in e for e in errors)


def test_enums_are_enforced():
    bad = edited(FULL, lambda d: d["claims"][0].update(confidence="certain"))
    assert any("confidence 'certain'" in e for e in lg.validate(bad))


# ---- profiles ----

def test_full_profile_needs_brief_search_log_and_source_detail():
    bad = edited(FULL, lambda d: (d.pop("brief"), d.pop("search_log"), d["sources"][0].pop("issuer")))
    errors = lg.validate(bad)
    assert "full profile: the ledger needs `brief`" in errors and "full profile: the ledger needs `search_log`" in errors
    assert "source SRC-001: missing issuer" in errors


def test_an_unlabelled_ledger_is_read_as_full():
    unlabelled = edited(LEAN, lambda d: d.pop("profile"))
    assert lg.profile_of(unlabelled) == "full"
    assert any("the ledger needs `brief`" in e for e in lg.validate(unlabelled))


def test_lean_needs_only_sources_and_claims():
    assert set(lg.required("lean")["ledger"]) == {"sources", "claims"}


def test_reviewed_false_is_a_value_not_a_gap():
    errors = lg.validate(edited(LEAN, lambda d: d["sources"][0].update(reviewed=False)))
    assert errors == ["claim CLAIM-001: a FACT needs a reviewed source, not only a search snippet"]


# ---- ADR-012 view ----

def test_objects_are_adr_012_shapes():
    kinds = {o["type"] for o in lg.objects(FULL)}
    assert kinds == {"Observation", "Claim", "Hypothesis", "Evidence"}
    withc = edited(FULL, lambda d: d["contradictions"].append(
        {"id": "CONTRA-001", "claim_ids": ["CLAIM-002"], "source_ids": ["SRC-002"], "note": "n", "status": "open"}))
    objs = lg.objects(withc)
    assert any(o["type"] == "Contradiction" for o in objs)
    assert any(o.get("stance") == "contradicts" for o in objs)


# ---- CLI ----

def test_cli_exit_codes(tmp_path, capsys):
    cli = _cli()
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(FULL))
    bad.write_text(json.dumps(edited(FULL, lambda d: d["claims"][0].update(source_ids=["SRC-404"]))))
    assert cli.main([str(good)]) == 0
    assert cli.main([str(good), str(bad)]) == 1
    assert "SRC-404" in capsys.readouterr().out
    lean = tmp_path / "lean.json"
    lean.write_text(json.dumps(LEAN))
    assert cli.main([str(lean), "--profile", "full"]) == 1
