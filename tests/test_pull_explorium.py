"""The weekly Explorium REST step is match-only (decision D1, 25 Sep 2026).

Enrichment is bought through the Enrichment Broker from the Vibe balance, so
this step must never reach the paid endpoint unless a run names the approved
enrichment job that pays for it.
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm import config  # noqa: E402
from crm.master import save_master  # noqa: E402
from crm.schema import Contact  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("pull_explorium", ROOT / "scripts" / "pull_explorium.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pull_explorium"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run(monkeypatch, tmp_path, *argv):
    mod = _load()
    master = tmp_path / "contacts.json"
    save_master([Contact(contact_id="c_ada", first_name="Ada", email="ada@acme.example", company_name="Acme")], master)
    monkeypatch.setattr(config, "MASTER_CONTACTS", master)
    monkeypatch.setattr(config, "EXPLORIUM_API_KEY", "test-key")
    calls = []

    def fake_post(url, payload, headers=None):
        calls.append(url)
        if url.endswith("/prospects/match"):
            return {"matched_prospects": [{"input": {"email": "ada@acme.example"}, "prospect_id": "p_ada"}]}
        return {"data": [{"prospect_id": "p_ada", "data": {"job_title": "CEO"}}]}

    monkeypatch.setattr(mod, "post_json", fake_post)
    out = tmp_path / "explorium.json"
    monkeypatch.setattr(sys, "argv", ["pull_explorium.py", "--out", str(out), *argv])
    code = mod.main()
    return code, calls, (json.loads(out.read_text()) if out.exists() else None)


def test_default_run_matches_and_never_calls_the_paid_endpoint(monkeypatch, tmp_path):
    code, calls, staged = _run(monkeypatch, tmp_path)
    assert code == 0
    assert all(u.endswith("/prospects/match") for u in calls)
    assert staged["mode"] == "match_only"
    assert staged["contacts"][0]["explorium_prospect_id"] == "p_ada"
    assert staged["contacts"][0]["title"] is None            # nothing enriched, nothing claimed


def test_enrich_without_a_job_refuses_before_any_call(monkeypatch, tmp_path):
    code, calls, staged = _run(monkeypatch, tmp_path, "--enrich")
    assert code == 2 and calls == [] and staged is None


def test_enrich_with_a_named_job_calls_the_paid_endpoint(monkeypatch, tmp_path):
    code, calls, staged = _run(monkeypatch, tmp_path, "--enrich", "--job", "job_20261001_x")
    assert code == 0 and any("bulk_enrich" in u for u in calls)
    assert staged["mode"] == "enrich" and staged["job_id"] == "job_20261001_x"
    assert staged["contacts"][0]["title"] == "CEO"
