"""GAP-023: the evidence persistence contract (crm/evidence_store.py) and the gates that rely on it.

Each test names the acceptance item it demonstrates. The Supabase backend is
exercised against a fake HTTP layer only; a real bucket is a separate,
owner-run check (docs/evidence-store.md).
"""

import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from crm import decision  # noqa: E402
from crm import evidence_store as es  # noqa: E402
import push_proposals_to_crm as push  # noqa: E402

NOW = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)
LEDGER = json.loads((ROOT / "tests" / "fixtures" / "evidence_ledger_full.json").read_text(encoding="utf-8"))


def run_folder(tmp_path, ledger=LEDGER, required=True):
    run = tmp_path / "runs" / "run_x"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"request": {"text": "second location"}}))
    (run / "state.json").write_text(json.dumps({"evidence_ledger": {"required": required, "profile": "full"}}))
    (run / "review.json").write_text(json.dumps({"status": "needs_review", "holds": ["confirm the domain"]}))
    (run / "web_research.md").write_text("## Company\nExamples [supported]")
    if ledger is not None:
        (run / "ledger.json").write_text(json.dumps(ledger))
    (run / "run_final.json").write_text("{}")
    return run


def record():
    return {"proposal_id": "prop_x", "run_id": "run_x", "proposal_markdown": "## Engagement summary\nx",
            "review": {"status": "needs_review", "holds": ["confirm the domain"], "text": "HOLD"}}


def persisted(tmp_path, **kw):
    store = es.LocalStore(tmp_path / "store")
    rec = record()
    rec["evidence"] = es.persist_run(store, "run_x", es.collect(run_folder(tmp_path, **kw), rec), NOW, record=rec)
    return store, rec


# 1. Successful persistence and read-back.
def test_persist_writes_files_manifest_and_receipt_and_reads_them_back(tmp_path):
    store, rec = persisted(tmp_path)
    ev = rec["evidence"]
    assert ev["contract"] == es.CONTRACT and ev["run_id"] == "run_x"
    assert store.exists("runs/run_x/manifest.json") and store.exists("runs/run_x/receipt.json")
    receipt = json.loads(store.get("runs/run_x/receipt.json"))
    assert receipt["manifest_sha256"] == ev["manifest_sha256"] and receipt["files_verified"] == 6
    assert store.get("runs/run_x/files/ledger.json") == json.dumps(LEDGER).encode()


def test_raw_derived_and_decision_files_are_kept_apart(tmp_path):
    store, _ = persisted(tmp_path)
    kinds = {f["path"]: f["kind"] for f in json.loads(store.get("runs/run_x/manifest.json"))["files"]}
    assert kinds["web_research.md"] == "raw" and kinds["manifest.json"] == "raw"
    assert kinds["ledger.json"] == "derived" and kinds["state.json"] == "derived"
    assert kinds["review.json"] == "decision" and kinds["proposal_record.json"] == "decision"
    assert "run_final.json" not in kinds


# 2. Manifest and hash verification.
def test_a_stored_run_verifies_and_reuses_the_decision_fingerprint(tmp_path):
    store, rec = persisted(tmp_path)
    assert es.verify_run(store, "run_x", rec["evidence"]["manifest_sha256"]) == []
    files = json.loads(store.get("runs/run_x/manifest.json"))["files"]
    assert rec["evidence"]["inputs_fingerprint"] == decision.fingerprint(
        {f["path"]: f["sha256"] for f in files}, es.CONTRACT, "none", "none")
    assert es.gate_record(rec, store) == []


# 3. Replay from a fresh process.
def test_replay_from_a_fresh_process(tmp_path):
    _, rec = persisted(tmp_path)
    rec_path = tmp_path / "prop.json"
    rec_path.write_text(json.dumps(rec))
    env = {**os.environ, "EVIDENCE_STORE": f"local:{tmp_path / 'store'}", "PYTHONPATH": str(ROOT)}
    out = subprocess.run([sys.executable, "-m", "crm.evidence_store", "verify", "run_x", "--record", str(rec_path)],
                         cwd=ROOT, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert json.loads(out.stdout)["manifest_sha256"] == rec["evidence"]["manifest_sha256"]


# 4. Altered or missing artifacts are rejected.
def test_an_altered_artifact_is_rejected(tmp_path):
    store, rec = persisted(tmp_path)
    (tmp_path / "store" / "runs/run_x/files/web_research.md").write_text("## Company\nsomething else")
    errors = es.gate_record(rec, store)
    assert any("web_research.md: content does not match" in e for e in errors)


def test_a_missing_artifact_is_rejected(tmp_path):
    store, rec = persisted(tmp_path)
    (tmp_path / "store" / "runs/run_x/files/review.json").unlink()
    assert any("review.json is not in the store" in e for e in es.gate_record(rec, store))


def test_a_replaced_manifest_is_rejected(tmp_path):
    store, rec = persisted(tmp_path)
    path = tmp_path / "store" / "runs/run_x/manifest.json"
    m = json.loads(path.read_text())
    m["files"] = [f for f in m["files"] if f["path"] != "ledger.json"]
    path.write_text(json.dumps(m))
    errors = es.gate_record(rec, store)
    assert any("manifest for run_x has changed" in e for e in errors)


def test_evidence_is_never_overwritten(tmp_path):
    store, _ = persisted(tmp_path)
    store.put("runs/run_x/files/state.json", store.get("runs/run_x/files/state.json"))  # same bytes: no-op
    with pytest.raises(es.EvidenceError, match="never overwritten"):
        store.put("runs/run_x/files/state.json", b"{}")


def test_a_missing_registry_entry_is_rejected(tmp_path):
    store, rec = persisted(tmp_path)
    (tmp_path / "store" / "_registry" / "run_x.json").unlink()
    assert any("no registry entry for the run" in e for e in es.gate_record(rec, store))


def test_a_registry_entry_that_disagrees_with_the_bucket_is_rejected(tmp_path):
    store, rec = persisted(tmp_path)
    path = tmp_path / "store" / "_registry" / "run_x.json"
    row = json.loads(path.read_text())
    row["manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(row))
    assert any("registry entry's manifest hash does not match" in e for e in es.gate_record(rec, store))


# 5. Changed inputs are rejected.
def test_a_record_edited_after_persisting_is_stale(tmp_path):
    store, rec = persisted(tmp_path)
    rec["proposal_markdown"] += "\nan added paragraph"
    assert any("changed since its evidence was persisted" in e for e in es.gate_record(rec, store))


def test_a_record_pointing_at_a_different_fingerprint_is_rejected(tmp_path):
    store, rec = persisted(tmp_path)
    rec["evidence"]["inputs_fingerprint"] = "fp_" + "0" * 64
    assert any("inputs fingerprint does not match" in e for e in es.gate_record(rec, store))


def test_a_rerun_with_changed_inputs_cannot_replace_the_stored_run(tmp_path):
    store, rec = persisted(tmp_path)
    changed = copy.deepcopy(record())
    changed["proposal_markdown"] = "a different draft"
    files = es.collect(tmp_path / "runs" / "run_x", changed)
    with pytest.raises(es.EvidenceError, match="never overwritten"):
        es.persist_run(store, "run_x", files, NOW, record=changed)


# 6. Unregistered sources and invalid claim references are rejected.
def test_a_claim_citing_an_unregistered_source_is_refused_at_persist(tmp_path):
    bad = copy.deepcopy(LEDGER)
    bad["claims"][0]["source_ids"] = ["SRC-999"]
    store = es.LocalStore(tmp_path / "store")
    rec = record()
    with pytest.raises(es.EvidenceError, match="SRC-999, which is not in the source register"):
        es.persist_run(store, "run_x", es.collect(run_folder(tmp_path, ledger=bad), rec), NOW, record=rec)
    assert not store.exists("runs/run_x/receipt.json"), "no receipt, so nothing counts as stored"


def test_a_run_prepared_for_a_ledger_without_one_is_refused(tmp_path):
    store = es.LocalStore(tmp_path / "store")
    rec = record()
    with pytest.raises(es.EvidenceError, match="prepared to file ledger.json"):
        es.persist_run(store, "run_x", es.collect(run_folder(tmp_path, ledger=None), rec), NOW, record=rec)


# 7. The Monday catch-up bypass is closed.
def test_the_catch_up_holds_proposals_without_verified_evidence(tmp_path):
    store, good = persisted(tmp_path)
    legacy = {**record(), "proposal_id": "prop_legacy"}
    tampered = copy.deepcopy(good)
    tampered["proposal_id"] = "prop_tampered"
    kept, held = push.gate_proposals([good, legacy, tampered], store)
    assert [p["proposal_id"] for p in kept] == ["prop_x"]
    assert any(h.startswith("prop_legacy: quarantined: no evidence receipt") for h in held)
    assert any(h.startswith("prop_tampered:") and "changed since" in h for h in held)


def test_the_catch_up_writes_nothing_without_a_store(tmp_path, monkeypatch, capsys):
    proposals = tmp_path / "proposals"
    proposals.mkdir()
    (proposals / "p.json").write_text(json.dumps(record()))
    monkeypatch.delenv("EVIDENCE_STORE", raising=False)
    monkeypatch.setattr(sys, "argv", ["push", "--crm-dump", str(tmp_path / "dump"), "--proposals-dir", str(proposals),
                                      "--out-dir", str(tmp_path / "out"), "--write"])
    assert push.main() == 1
    assert "nothing pushed" in capsys.readouterr().out and not (tmp_path / "out").exists()


def test_a_loaded_proposal_still_verifies(tmp_path):
    """load_proposals adds `_path`; the record digest ignores loader keys."""
    store, rec = persisted(tmp_path)
    d = tmp_path / "proposals"
    d.mkdir()
    (d / "p.json").write_text(json.dumps(rec))
    [loaded] = push.load_proposals(d)
    assert "_path" in loaded and es.gate_record(loaded, store) == []


# 8. Human-approval boundaries are preserved.
def test_persisting_does_not_touch_the_review_or_its_holds(tmp_path):
    _, rec = persisted(tmp_path)
    assert rec["review"] == record()["review"]


# Store selection and the Supabase backend.
def test_no_configuration_means_no_store():
    with pytest.raises(es.EvidenceError, match="no evidence store configured"):
        es.store_from_env({})
    with pytest.raises(es.EvidenceError, match="https"):
        es.store_from_env({"EVIDENCE_STORE": "supabase", "SUPABASE_URL": "http://x"})


def test_the_service_role_key_is_never_enough():
    """Filing runs use the least-privilege writer; an elevated key alone configures nothing."""
    with pytest.raises(es.EvidenceError, match=r"SUPABASE_PUBLISHABLE_KEY \(or SUPABASE_ANON_KEY\), EVIDENCE_WRITER_EMAIL, EVIDENCE_WRITER_PASSWORD not set"):
        es.store_from_env({"EVIDENCE_STORE": "supabase", "SUPABASE_URL": "https://example.supabase.co",
                           "SUPABASE_SERVICE_ROLE_KEY": "elevated"})


def test_manifests_carry_the_retention_date_and_nothing_deletes(tmp_path):
    store, _ = persisted(tmp_path)
    m = json.loads(store.get("runs/run_x/manifest.json"))
    assert m["retain_until"] == "2027-11-01" and es.RETENTION_DAYS == 365
    assert not hasattr(store, "delete") and not hasattr(es.SupabaseStore, "delete")


def test_bad_keys_are_refused(tmp_path):
    store = es.LocalStore(tmp_path)
    for key in ("../x", "/abs", "a//b", "a/./b"):
        with pytest.raises(es.EvidenceError):
            store.put(key, b"x")
    with pytest.raises(es.EvidenceError):
        es.run_prefix("a/b")


class FakeResponse:
    def __init__(self, status, body=b""):
        self.status, self._body = status, body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_bucket(monkeypatch):
    """A fake Storage API: refuses re-upload like x-upsert: false, serves authenticated downloads."""
    import urllib.error
    import urllib.parse
    objects, seen, registry = {}, [], {}

    def urlopen(req, timeout=None):
        seen.append(req)
        if "/auth/v1/token?grant_type=password" in req.full_url:
            creds = json.loads(req.data)
            ok = creds == {"email": "writer@example.com", "password": "writer-pass"} and req.headers.get("Apikey") == "anon"
            if not ok:
                raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, _io(
                    b'{"code":400,"error_code":"invalid_credentials","msg":"Invalid login credentials"}'))
            return FakeResponse(200, b'{"access_token":"writer-jwt"}')
        assert req.headers.get("Authorization") == "Bearer writer-jwt"
        if "/rest/v1/evidence_registry" in req.full_url:
            if req.get_method() == "POST":
                row = json.loads(req.data)
                if row["run_id"] in registry:
                    raise urllib.error.HTTPError(req.full_url, 409, "conflict", {}, _io(b"{}"))
                registry[row["run_id"]] = row
                return FakeResponse(201, b"")
            run_id = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)["run_id"][0][3:]
            return FakeResponse(200, json.dumps([registry[run_id]] if run_id in registry else []).encode())
        path = req.full_url.split("/storage/v1/object/", 1)[1]
        if req.get_method() == "POST":
            key = path.split("/", 1)[1]
            assert req.headers.get("X-upsert") == "false"
            if key in objects:
                raise urllib.error.HTTPError(req.full_url, 400, "exists", {}, _io(b'{"error":"Duplicate"}'))
            objects[key] = req.data
            return FakeResponse(200, b"{}")
        assert path.startswith("authenticated/")
        key = path.split("/", 2)[2]
        if key not in objects:
            raise urllib.error.HTTPError(req.full_url, 400, "not found", {}, _io(b'{"error":"not_found"}'))
        return FakeResponse(200, objects[key])

    monkeypatch.setattr(es.urllib.request, "urlopen", urlopen)
    return objects, seen


def _io(b):
    import io
    return io.BytesIO(b)


def test_supabase_backend_persists_reads_back_and_refuses_overwrites(tmp_path, monkeypatch):
    objects, seen = fake_bucket(monkeypatch)
    store = es.store_from_env({"EVIDENCE_STORE": "supabase", "SUPABASE_URL": "https://example.supabase.co",
                               "SUPABASE_ANON_KEY": "anon", "EVIDENCE_WRITER_EMAIL": "writer@example.com",
                               "EVIDENCE_WRITER_PASSWORD": "writer-pass", "EVIDENCE_BUCKET": "run-evidence"})
    rec = record()
    rec["evidence"] = es.persist_run(store, "run_x", es.collect(run_folder(tmp_path), rec), NOW, record=rec)
    assert es.gate_record(rec, store) == []
    assert "runs/run_x/receipt.json" in objects
    row = store.lookup("run_x")
    assert row["manifest_sha256"] == rec["evidence"]["manifest_sha256"] and row["retain_until"] == "2027-11-01"
    assert all("/run-evidence/" in r.full_url for r in seen if "/storage/" in r.full_url)
    with pytest.raises(es.EvidenceError) as exc:
        store.put("runs/run_x/files/state.json", b"{}")
    assert "never overwritten" in str(exc.value) and "writer-pass" not in str(exc.value)


def test_a_failed_writer_sign_in_configures_no_store(monkeypatch):
    fake_bucket(monkeypatch)
    with pytest.raises(es.EvidenceError, match=r"sign-in failed: HTTP 400 \(invalid_credentials\)") as exc:
        es.store_from_env({"EVIDENCE_STORE": "supabase", "SUPABASE_URL": "https://example.supabase.co",
                           "SUPABASE_ANON_KEY": "anon", "EVIDENCE_WRITER_EMAIL": "writer@example.com",
                           "EVIDENCE_WRITER_PASSWORD": "wrong"})
    assert "wrong" not in str(exc.value)


def test_a_sign_in_error_shows_only_a_bare_error_code(monkeypatch):
    """Supabase's reason is shown only when it is a snake_case code, so no request text is echoed."""
    import urllib.error

    def urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, _io(b'{"error_code":"bad pass: hunter2"}'))

    monkeypatch.setattr(es.urllib.request, "urlopen", urlopen)
    with pytest.raises(es.EvidenceError) as exc:
        es.store_from_env({"EVIDENCE_STORE": "supabase", "SUPABASE_URL": "https://example.supabase.co",
                           "SUPABASE_ANON_KEY": "anon", "EVIDENCE_WRITER_EMAIL": "writer@example.com",
                           "EVIDENCE_WRITER_PASSWORD": "hunter2"})
    assert str(exc.value) == "evidence writer sign-in failed: HTTP 400"
