"""crm/costs.py and scripts/cost_report.py: prices, month boundaries, cap counting, retries, confirmations."""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm import costs, runlog  # noqa: E402

OCT = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def make_run(runs, run_id, composed_at=None):
    d = runs / run_id
    d.mkdir(parents=True)
    run = {"run_id": run_id}
    if composed_at:
        run["composed_at"] = composed_at
    (d / "manifest.json").write_text(json.dumps({"run": run}))
    return d


def comp_line(at, run_id=None, status="applied", note=None):
    doc = {"id": f"rl_{at}", "run": costs.COMPOSITION_RUN, "at": at, "status": status, "created": 0, "updated": 1,
           "detail": "Example: proposal prq_x"}
    if run_id:
        doc["run_id"] = run_id
    if note:
        doc["note"] = note
    return doc


def confirmed_cap(run_id, at="2026-10-09T14:00:00Z", **over):
    doc = costs.cap_entry(run_id, 5, utc(at))
    doc.update({"status": "confirmed", "confirmed_at": "2026-10-09T14:30:00Z", "confirmed_count": 0,
                "confirm_check": "opened the Intake page; new account request"})
    doc.update(over)
    return doc


# ---------------------------------------------------------------- prices ----

def test_prices_come_from_the_manifest_and_estimate_at_list_rates():
    manifest = costs.load_manifest()
    table = costs.prices(manifest)
    assert manifest["cost_basis"]["as_of"] and manifest["cost_basis"]["sources"]
    assert costs.estimate_usd("claude-opus-5-5", {"input": 1_000_000, "output": 1_000_000}, table) == 24.0
    assert costs.estimate_usd("claude-opus-5-5", {"input": 1_000_000, "output": 1_000_000}, table, batch=True) == 12.0
    assert costs.estimate_usd("claude-sonnet-5-5", {"cache_read": 10_000_000}, table) == 1.0
    assert table["claude-opus-5"]["cache_read"] > table["claude-opus-5-5"]["cache_read"]


def test_estimate_refuses_unknown_models_and_fields():
    table = costs.prices(costs.load_manifest())
    with pytest.raises(KeyError):
        costs.estimate_usd("claude-unknown", {"input": 1}, table)
    with pytest.raises(ValueError):
        costs.estimate_usd("claude-opus-5-5", {"tokens": 1}, table)


# ------------------------------------------------------- month boundaries ----

@pytest.mark.parametrize("ts,month", [
    ("2026-10-01T03:59:59Z", "2026-09"),   # 23:59 EDT on 30 Sep
    ("2026-10-01T04:00:00Z", "2026-10"),
    ("2026-12-01T04:59:59Z", "2026-11"),   # EST after the November change
    ("2026-12-01T05:00:00Z", "2026-12"),
    ("2027-01-01T04:30:00Z", "2026-12"),   # New Year's Eve in New York
])
def test_month_is_the_new_york_calendar_month(ts, month):
    assert costs.month_of(utc(ts)) == month


def test_naive_times_are_read_as_utc():
    assert costs.month_of(datetime(2026, 10, 1, 3, 0)) == "2026-09"


# ---------------------------------------------------------------- counting ----

def test_counts_runs_in_this_month_only(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs, "run_a", "2026-10-02T15:00:00Z")
    make_run(runs, "run_b", "2026-09-30T23:00:00Z")          # 19:00 EDT on 30 Sep: September
    make_run(runs, "run_20261003_c")                          # dated by its id
    make_run(runs, "run_20260915_d")
    make_run(runs, "custom")                                  # undated: counted, conservatively
    (runs / "held_only").mkdir()                              # a held run writes no manifest
    seen = costs.counted_runs(OCT, runs)
    assert set(seen) == {"run_a", "run_20261003_c", "custom"}
    assert "undated" in seen["custom"]


def test_runlog_lines_count_and_dedupe_with_run_dirs(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs, "run_a", "2026-10-02T15:00:00Z")
    docs = [
        comp_line("2026-10-02T16:00:00Z", run_id="run_a"),                     # same run as the directory
        comp_line("2026-10-03T16:00:00Z", note="Recorded from data/runs/run_x"),  # run id from the note
        comp_line("2026-10-04T16:00:00Z"),                                     # no run id: keyed by entry id
        comp_line("2026-09-20T16:00:00Z", run_id="run_sep"),                   # last month
        comp_line("2026-10-05T16:00:00Z", run_id="run_h", status="held"),      # not applied
        {**costs.cap_entry("run_z", 5, OCT)},                                  # a cap hold is not a run
    ]
    seen = costs.counted_runs(OCT, runs, docs)
    assert set(seen) == {"run_a", "run_x", "rl_2026-10-04T16:00:00Z"}
    assert seen["run_a"] == "data/runs"


# --------------------------------------------------------------------- cap ----

def five_runs(tmp_path):
    runs = tmp_path / "runs"
    for i in range(5):
        make_run(runs, f"run_{i}", f"2026-10-0{i + 1}T15:00:00Z")
    return runs


def test_under_the_cap_runs(tmp_path):
    runs = tmp_path / "runs"
    for i in range(4):
        make_run(runs, f"run_{i}", "2026-10-02T15:00:00Z")
    out = costs.cap_check("run_new", OCT, runs)
    assert out["status"] == costs.CAP_OK and out["count"] == 4 and out["cap"] == 5


def test_the_sixth_run_holds_with_an_entry_for_the_crm(tmp_path):
    out = costs.cap_check("run_new", OCT, five_runs(tmp_path))
    assert out["status"] == costs.CAP_HELD and out["count"] == 5
    entry = out["entry"]
    assert entry["status"] == runlog.STATUS_HELD and entry["run"] == costs.CAP_RUN and entry["run_id"] == "run_new"
    assert entry["check"] and "HELD" in entry["line"]


def test_a_retry_of_a_counted_run_is_not_held(tmp_path):
    out = costs.cap_check("run_4", OCT, five_runs(tmp_path))
    assert out["status"] == costs.CAP_RETRY and out["count"] == 4


def test_a_new_month_starts_at_zero(tmp_path):
    runs = five_runs(tmp_path)
    nov = utc("2026-11-01T04:00:00Z")                        # midnight EDT, 1 Nov
    assert costs.cap_check("run_new", nov, runs)["status"] == costs.CAP_OK


def test_a_confirmed_cap_entry_lets_the_run_proceed(tmp_path):
    out = costs.cap_check("run_new", OCT, five_runs(tmp_path), [confirmed_cap("run_new")],
                          confirmation=confirmed_cap("run_new")["id"])
    assert out["status"] == costs.CAP_CONFIRMED and out["confirm_check"]


@pytest.mark.parametrize("doc,why", [
    (None, "not in the CRM runlog"),
    ({"status": "held", "confirmed_at": None, "confirm_check": None}, "not confirmed"),
    ({"confirm_check": "ok"}, "not confirmed"),                         # too short to be a check
    ({"run_id": "run_other"}, "not the cap entry"),
    ({"run": costs.COMPOSITION_RUN}, "not the cap entry"),
    ({"confirmed_count": 3}, "not confirmed"),
])
def test_a_confirmation_that_does_not_hold_up_is_refused(tmp_path, doc, why):
    base = confirmed_cap("run_new")
    docs = [] if doc is None else [{**base, **doc}]
    with pytest.raises(costs.CapError, match=why):
        costs.cap_check("run_new", OCT, five_runs(tmp_path), docs, confirmation=base["id"])


def test_a_confirmation_from_last_month_is_refused(tmp_path):
    old = confirmed_cap("run_new", at="2026-09-30T12:00:00Z")
    with pytest.raises(costs.CapError, match="another month"):
        costs.cap_check("run_new", OCT, five_runs(tmp_path), [old], confirmation=old["id"])


def test_runlog_confirmed_is_structural():
    doc = confirmed_cap("run_new")
    assert runlog.confirmed(doc)
    assert not runlog.confirmed({**doc, "status": "held"})
    assert not runlog.confirmed({**doc, "confirm_check": "short"})
    assert not runlog.confirmed({**doc, "confirmed_at": ""})


# --------------------------------------------------------------- the report ----

def test_cost_report_counts_runs_and_estimates(tmp_path, capsys):
    report = _load_script("cost_report")
    runs = five_runs(tmp_path)
    dump = tmp_path / "dump" / "runlog"
    dump.mkdir(parents=True)
    (dump / "rl_1.json").write_text(json.dumps(comp_line("2026-10-06T15:00:00Z", run_id="run_crm_only")))
    usage = tmp_path / "usage.json"
    usage.write_text(json.dumps([{"model": "claude-sonnet-5-5", "input": 1_000_000, "output": 100_000}]))
    rc = report.main(["--runs-dir", str(runs), "--crm-dump", str(tmp_path / "dump"), "--usage", str(usage),
                      "--now", "2026-10-09T15:00:00Z", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["composition"]["runs"] == 6 and out["composition"]["next_run_holds"] is True
    assert out["estimate"]["usd"] == 3.0
    site = next(r for r in out["routines"] if r["name"] == "Daily site check")
    assert site["legacy"] is True
    assert all(r["basis"] for r in out["routines"])


def test_cost_report_text_says_it_is_an_estimate(tmp_path, capsys):
    report = _load_script("cost_report")
    assert report.main(["--runs-dir", str(tmp_path / "none"), "--now", "2026-10-09T15:00:00Z"]) == 0
    text = capsys.readouterr().out
    assert "Estimates only" in text and "0 of 5" in text
