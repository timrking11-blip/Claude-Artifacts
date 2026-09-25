"""crm/runlog.py and the weekly merge's hold: one line per run, and no silent bulk creation."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from crm import runlog  # noqa: E402

NOW = datetime(2026, 9, 21, 6, 5, 45, tzinfo=timezone.utc)


def test_threshold_and_exact_confirmation():
    assert runlog.HOLD_OVER == 5
    assert not runlog.held(5) and runlog.held(6)
    assert not runlog.held(15, allow_created=15), "confirming means allowing exactly this count"
    assert runlog.held(16, allow_created=15), "a different count holds again"


def test_sep_21_would_have_held():
    names = [f"Person {i} (Co {i})" for i in range(15)]
    doc = runlog.entry("Weekly sync", "apollo 15 created, 0 updated, 52 unchanged", 15, 0, NOW, created_names=names)
    assert doc["status"] == "held" and doc["id"] == "rl_20260921T060545_weekly-sync"
    assert doc["line"] == "Weekly sync · apollo 15 created, 0 updated, 52 unchanged · HELD (15 created, over 5)"
    assert doc["created_names"] == names and doc["check"] and doc["on_confirm"]


def test_applied_line_and_name_cap():
    doc = runlog.entry("Composition run", "Acme: proposal prq_x, account created", 1, 0, NOW, created_names=["Acme"])
    assert doc["status"] == "applied" and doc["line"].endswith("· applied") and "check" not in doc
    many = runlog.entry("Weekly sync", "", 40, 0, NOW, created_names=[f"n{i}" for i in range(40)])
    assert len(many["created_names"]) == runlog.MAX_NAMES and many["created_more"] == 15


def test_pending_posts_only_what_the_crm_lacks(tmp_path):
    rl, posted = tmp_path / "runlog", tmp_path / "posted" / "runlog"
    posted.mkdir(parents=True)
    a = runlog.write_file(runlog.entry("Weekly sync", "", 1, 0, NOW), rl)
    b = runlog.write_file(runlog.entry("Apollo writeback", "", 0, 3, datetime(2026, 9, 28, tzinfo=timezone.utc)), rl)
    (posted / a.name).write_text("{}")
    out = runlog.pending(tmp_path / "posted", rl)
    assert [e["doc_id"] for e in out] == [b.stem] and out[0]["collection"] == "runlog" and out[0]["op"] == "set"


def test_cli_entry(capsys):
    assert runlog.main(["entry", "--run", "Apollo ⇄ CRM sync", "--created", "7", "--name", "A", "--name", "B"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["status"] == "held" and doc["created_names"] == ["A", "B"]


def _staged(tmp_path, monkeypatch, n_new):
    """A master of one contact and an Apollo staging file with n_new new people."""
    import merge_master
    from crm import config
    from crm.schema import Contact
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "MASTER_CONTACTS", tmp_path / "master" / "contacts.json")
    monkeypatch.setattr(config, "CHANGELOG", tmp_path / "CHANGELOG.md")
    monkeypatch.setattr(config, "APOLLO_STAGING", tmp_path / "staging" / "apollo.json")
    monkeypatch.setattr(config, "EXPLORIUM_STAGING", tmp_path / "staging" / "explorium.json")
    monkeypatch.setattr(config, "LINKEDIN_STAGING", tmp_path / "staging" / "linkedin.json")
    monkeypatch.setattr(runlog, "RUNLOG_DIR", tmp_path / "runlog")
    (tmp_path / "staging").mkdir(parents=True)
    people = [Contact(first_name=f"P{i}", last_name="New", email=f"p{i}@new.example", company_name="NewCo",
                      apollo_contact_id=f"ap{i}", sources=["apollo"]).to_dict() for i in range(n_new)]
    (tmp_path / "staging" / "apollo.json").write_text(json.dumps({"observed_at": "2026-09-21T06:00:00Z",
                                                                  "contacts": people}))
    return merge_master


def _run(merge_master, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["merge_master.py", *args])
    return merge_master.main()


def test_merge_holds_over_threshold_and_writes_no_master(tmp_path, monkeypatch):
    mm = _staged(tmp_path, monkeypatch, 15)
    monkeypatch.delenv("ALLOW_CREATED", raising=False)
    assert _run(mm, monkeypatch) == 0
    assert not (tmp_path / "master" / "contacts.json").exists(), "a held run does not write master"
    [line] = [json.loads(p.read_text()) for p in (tmp_path / "runlog").glob("rl_*.json")]
    assert line["status"] == "held" and line["created"] == 15 and "P0 New (NewCo)" in line["created_names"]
    assert "allow_created = 15" in line["on_confirm"]
    assert "HELD" in (tmp_path / "CHANGELOG.md").read_text()


def test_merge_applies_the_confirmed_count_only(tmp_path, monkeypatch):
    mm = _staged(tmp_path, monkeypatch, 15)
    assert _run(mm, monkeypatch, "--allow-created", "14") == 0
    assert not (tmp_path / "master" / "contacts.json").exists(), "14 confirmed, 15 created: still held"
    assert _run(mm, monkeypatch, "--allow-created", "15") == 0
    assert (tmp_path / "master" / "contacts.json").exists()
    statuses = sorted(json.loads(p.read_text())["status"] for p in (tmp_path / "runlog").glob("rl_*.json"))
    assert "applied" in statuses


def test_merge_under_threshold_applies_with_a_line(tmp_path, monkeypatch):
    mm = _staged(tmp_path, monkeypatch, 3)
    monkeypatch.delenv("ALLOW_CREATED", raising=False)
    assert _run(mm, monkeypatch) == 0
    assert (tmp_path / "master" / "contacts.json").exists()
    [line] = [json.loads(p.read_text()) for p in (tmp_path / "runlog").glob("rl_*.json")]
    assert line["status"] == "applied" and line["line"].startswith("Weekly sync · apollo 3 created")
