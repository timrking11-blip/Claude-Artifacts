"""Evidence persistence contract (GAP-023): durable, immutable, verifiable run evidence.

A run's evidence is the set of files a decision was made from. This module
stores them outside the repository, in a private store, under a hash manifest,
and checks them again whenever something wants to rely on them. It is the
first piece of the AI-native intelligence layer's shared evidence capability:
any producer (the composition run first) persists through `persist_run`, and
any consumer (the proposal push, a replay, an audit) checks through
`verify_run` and `gate_record`. Nothing here writes to the CRM.

Contract `evidence-store/1`
---------------------------
Keys in the store, all under one run id:

  runs/<run_id>/files/<path>   each evidence file, byte for byte
  runs/<run_id>/manifest.json  the hash manifest (below), written after the files
  runs/<run_id>/receipt.json   the read-back verification receipt, written last

The manifest:

  {contract, run_id, created_at, producer,
   files: [{path, sha256, bytes, kind}],      kind: raw | derived | decision
   inputs_fingerprint,                        crm.decision.fingerprint over {path: sha256}
   record_sha256}                             sha256 of the proposal record, `evidence` and `_` keys removed

Raw observations (what was fetched or read) are kept apart from derived
artifacts (ledgers, state, drafts) and from decision artifacts (the review,
the proposal record), by `kind`.

Rules
-----
- Immutable: `put` refuses a key that already holds different bytes. The same
  bytes again is a no-op, so a retried persist is safe.
- Nothing counts as stored until it has been read back and every hash matched;
  the receipt records that read-back.
- A record relying on a run (`gate_record`) is accepted only when the run's
  manifest matches the record's pointer, every file re-hashes to its manifest
  entry, the inputs fingerprint recomputes, the record itself is unchanged
  since it was persisted, and the run's evidence ledger, when it has one,
  passes crm.ledger.validate.

Backends: LocalStore (a folder; tests and replay) and SupabaseStore (a private
Supabase Storage bucket over its REST API). Credentials come only from the
environment and are never printed. `store_from_env` picks one:

  EVIDENCE_STORE=local:<folder>
  EVIDENCE_STORE=supabase   with SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and
                            EVIDENCE_BUCKET (default "run-evidence")

CLI (replay from a fresh process):

  python3 -m crm.evidence_store verify RUN_ID [--record PROPOSAL.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from . import decision
from . import ledger as evidence_ledger

CONTRACT = "evidence-store/1"
DEFAULT_BUCKET = "run-evidence"

#: Files that are observations of the outside world, kept apart from what was derived from them.
RAW_FILES = frozenset({"web_research.md", "data_sources.md", "web_sources.json", "coverage.json", "manifest.json"})
#: Files that record a decision or its review.
DECISION_FILES = frozenset({"review.json", "founder.json", "proposal_record.json", "cap.json"})
#: Never evidence: what this run itself writes after filing.
EXCLUDED = frozenset({"run_final.json"})


class EvidenceError(Exception):
    """Persisting or verifying evidence failed. The message says what and where."""


class Store(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _check_key(key: str) -> str:
    parts = key.split("/")
    if not key or key.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise EvidenceError(f"bad store key {key!r}")
    return key


class LocalStore:
    """A folder as the store. Immutable in the same way as the real one."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / _check_key(key)

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        if path.exists():
            if path.read_bytes() == data:
                return
            raise EvidenceError(f"{key} already holds different bytes; evidence is never overwritten")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".partial")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise EvidenceError(f"{key} is not in the store")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class SupabaseStore:
    """A private Supabase Storage bucket, over the Storage REST API.

    Uploads send `x-upsert: false`, so the service refuses to replace an
    object; a refused upload is accepted only when the stored bytes match.
    The key is read from the environment by `store_from_env`, held only on the
    instance, and never included in a message.
    """

    def __init__(self, url: str, key: str, bucket: str = DEFAULT_BUCKET, timeout: float = 30.0) -> None:
        if not url.startswith("https://"):
            raise EvidenceError("SUPABASE_URL must be an https:// URL")
        if not key:
            raise EvidenceError("SUPABASE_SERVICE_ROLE_KEY is not set")
        self.base = url.rstrip("/") + "/storage/v1/object"
        self.bucket = bucket
        self.timeout = timeout
        self._headers = {"Authorization": f"Bearer {key}", "apikey": key}

    def _url(self, key: str, authenticated: bool = False) -> str:
        path = urllib.parse.quote(_check_key(key))
        middle = "authenticated/" if authenticated else ""
        return f"{self.base}/{middle}{urllib.parse.quote(self.bucket)}/{path}"

    def _request(self, method: str, url: str, data: bytes | None = None,
                 extra: dict[str, str] | None = None) -> tuple[int, bytes]:
        req = urllib.request.Request(url, data=data, method=method, headers={**self._headers, **(extra or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except urllib.error.URLError as exc:
            raise EvidenceError(f"store unreachable: {exc.reason}") from None

    def put(self, key: str, data: bytes) -> None:
        status, body = self._request("POST", self._url(key), data,
                                     {"Content-Type": "application/octet-stream", "x-upsert": "false"})
        if 200 <= status < 300:
            return
        if status in (400, 409) and self.exists(key):
            if self.get(key) == data:
                return
            raise EvidenceError(f"{key} already holds different bytes; evidence is never overwritten")
        raise EvidenceError(f"upload of {key} failed: HTTP {status} {body[:200]!r}")

    def get(self, key: str) -> bytes:
        status, body = self._request("GET", self._url(key, authenticated=True))
        if status == 200:
            return body
        if status in (400, 404):
            raise EvidenceError(f"{key} is not in the store")
        raise EvidenceError(f"download of {key} failed: HTTP {status}")

    def exists(self, key: str) -> bool:
        status, _ = self._request("GET", self._url(key, authenticated=True))
        return status == 200


def store_from_env(env: dict[str, str] | None = None) -> Store:
    """The configured store. Fails closed: no configuration, no store."""
    env = dict(os.environ if env is None else env)
    spec = env.get("EVIDENCE_STORE", "").strip()
    if spec.startswith("local:"):
        return LocalStore(Path(spec[len("local:"):]))
    if spec == "supabase":
        return SupabaseStore(env.get("SUPABASE_URL", ""), env.get("SUPABASE_SERVICE_ROLE_KEY", ""),
                             env.get("EVIDENCE_BUCKET", DEFAULT_BUCKET))
    raise EvidenceError("no evidence store configured (EVIDENCE_STORE=supabase or local:<folder>); "
                        "a proposal cannot be filed without one")


def run_prefix(run_id: str) -> str:
    if not run_id or "/" in run_id or run_id in (".", ".."):
        raise EvidenceError(f"bad run id {run_id!r}")
    return f"runs/{run_id}"


def kind_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if name in RAW_FILES or path.startswith("pages/"):
        return "raw"
    if name in DECISION_FILES:
        return "decision"
    return "derived"


def _persisted(record: dict[str, Any]) -> dict[str, Any]:
    """The record as persisted: without its `evidence` pointer or loader-added `_` keys."""
    return {k: v for k, v in record.items() if k != "evidence" and not k.startswith("_")}


def record_digest(record: dict[str, Any]) -> str:
    """sha256 of the record as persisted."""
    return sha256(_canonical(_persisted(record)))


def inputs_fingerprint(files: list[dict[str, Any]]) -> str:
    return decision.fingerprint({f["path"]: f["sha256"] for f in files}, CONTRACT, "none", "none")


def collect(run_dir: Path, record: dict[str, Any] | None = None) -> dict[str, bytes]:
    """The run's evidence: every file in the run folder, plus the record when given."""
    files: dict[str, bytes] = {}
    for path in sorted(p for p in Path(run_dir).rglob("*") if p.is_file()):
        rel = path.relative_to(run_dir).as_posix()
        if rel in EXCLUDED or rel.endswith(".partial"):
            continue
        files[rel] = path.read_bytes()
    if record is not None:
        files["proposal_record.json"] = _canonical(_persisted(record))
    if not files:
        raise EvidenceError(f"{run_dir} holds no evidence files")
    return files


def persist_run(store: Store, run_id: str, files: dict[str, bytes], now: datetime,
                producer: str = "composition-run", record: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write files, then the manifest, read everything back, then write the receipt.

    Returns the pointer a record carries in `evidence`. Raises EvidenceError,
    having filed nothing that counts, if any step or any read-back fails.
    """
    prefix = run_prefix(run_id)
    entries = [{"path": p, "sha256": sha256(b), "bytes": len(b), "kind": kind_of(p)} for p, b in sorted(files.items())]
    manifest = {"contract": CONTRACT, "run_id": run_id, "created_at": now.astimezone(timezone.utc).isoformat(),
                "producer": producer, "files": entries, "inputs_fingerprint": inputs_fingerprint(entries),
                "record_sha256": record_digest(record) if record is not None else None}
    for path, data in sorted(files.items()):
        store.put(f"{prefix}/files/{path}", data)
    manifest_bytes = _canonical(manifest)
    store.put(f"{prefix}/manifest.json", manifest_bytes)
    errors = verify_run(store, run_id, expected_manifest_sha256=sha256(manifest_bytes))
    if errors:
        raise EvidenceError("read-back failed: " + " | ".join(errors))
    receipt = {"contract": CONTRACT, "run_id": run_id, "manifest_sha256": sha256(manifest_bytes),
               "verified_at": now.astimezone(timezone.utc).isoformat(), "files_verified": len(entries),
               "checks": ["files re-hashed", "inputs fingerprint recomputed", "evidence ledger validated"]}
    store.put(f"{prefix}/receipt.json", _canonical(receipt))
    return {"contract": CONTRACT, "run_id": run_id, "manifest_key": f"{prefix}/manifest.json",
            "manifest_sha256": receipt["manifest_sha256"], "inputs_fingerprint": manifest["inputs_fingerprint"],
            "receipt_key": f"{prefix}/receipt.json", "verified_at": receipt["verified_at"]}


def load_manifest(store: Store, run_id: str) -> tuple[dict[str, Any], str]:
    raw = store.get(f"{run_prefix(run_id)}/manifest.json")
    try:
        return json.loads(raw), sha256(raw)
    except ValueError:
        raise EvidenceError(f"manifest for {run_id} is not valid JSON") from None


def verify_run(store: Store, run_id: str, expected_manifest_sha256: str | None = None) -> list[str]:
    """Every problem with a stored run; empty when it verifies. Reads only from the store."""
    try:
        manifest, digest = load_manifest(store, run_id)
    except EvidenceError as exc:
        return [str(exc)]
    errors: list[str] = []
    if expected_manifest_sha256 and digest != expected_manifest_sha256:
        errors.append(f"manifest for {run_id} has changed (sha256 {digest[:12]}…, expected "
                      f"{expected_manifest_sha256[:12]}…)")
    if manifest.get("contract") != CONTRACT:
        errors.append(f"manifest contract is {manifest.get('contract')!r}, not {CONTRACT}")
    if manifest.get("run_id") != run_id:
        errors.append(f"manifest names run {manifest.get('run_id')!r}, not {run_id}")
    files = manifest.get("files") or []
    if not files:
        errors.append("manifest lists no files")
    blobs: dict[str, bytes] = {}
    for entry in files:
        key = f"{run_prefix(run_id)}/files/{entry.get('path')}"
        try:
            data = store.get(key)
        except EvidenceError as exc:
            errors.append(str(exc))
            continue
        if sha256(data) != entry.get("sha256"):
            errors.append(f"{entry.get('path')}: content does not match its manifest hash")
        blobs[entry["path"]] = data
    if files and manifest.get("inputs_fingerprint") != inputs_fingerprint(files):
        errors.append("inputs fingerprint does not match the listed files")
    if "ledger.json" in blobs:
        try:
            ledger_errors = evidence_ledger.validate(json.loads(blobs["ledger.json"]))
        except ValueError:
            ledger_errors = ["ledger.json is not valid JSON"]
        errors.extend(f"evidence ledger: {e}" for e in ledger_errors)
    elif _ledger_required(blobs.get("state.json")):
        errors.append("evidence ledger: the run was prepared to file ledger.json, and it is not in the evidence")
    return errors


def _ledger_required(state_bytes: bytes | None) -> bool:
    if not state_bytes:
        return False
    try:
        return bool(((json.loads(state_bytes) or {}).get("evidence_ledger") or {}).get("required"))
    except ValueError:
        return False


def gate_record(record: dict[str, Any], store: Store) -> list[str]:
    """Why a proposal record may not be filed or pushed; empty when its evidence holds.

    Used by the composition run before it emits a CRM batch and by the Monday
    proposal catch-up before it plans one, so both paths apply the same checks.
    """
    ev = record.get("evidence")
    pid = record.get("proposal_id") or "proposal"
    if not ev:
        return [f"{pid}: no evidence receipt (filed before the evidence store, or never persisted)"]
    if ev.get("contract") != CONTRACT:
        return [f"{pid}: evidence contract {ev.get('contract')!r} is not {CONTRACT}"]
    run_id = ev.get("run_id") or ""
    try:
        errors = verify_run(store, run_id, expected_manifest_sha256=ev.get("manifest_sha256"))
        manifest, _ = load_manifest(store, run_id) if not errors else ({}, "")
    except EvidenceError as exc:
        return [f"{pid}: {exc}"]
    if not errors:
        if manifest.get("inputs_fingerprint") != ev.get("inputs_fingerprint"):
            errors.append("the record's inputs fingerprint does not match the stored run")
        if manifest.get("record_sha256") != record_digest(record):
            errors.append("the record has changed since its evidence was persisted (stale or edited)")
        try:
            store.get(ev.get("receipt_key") or f"{run_prefix(run_id)}/receipt.json")
        except EvidenceError:
            errors.append("no read-back receipt for the run")
    return [f"{pid}: {e}" for e in errors]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify stored run evidence from a fresh process.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("run_id")
    v.add_argument("--record", type=Path, default=None, help="a proposal JSON whose evidence pointer to check too")
    args = ap.parse_args(argv)
    try:
        store = store_from_env()
    except EvidenceError as exc:
        print(f"evidence: {exc}")
        return 2
    errors = verify_run(store, args.run_id)
    if args.record:
        errors += gate_record(json.loads(args.record.read_text()), store)
    if errors:
        for e in errors:
            print(f"evidence: {e}")
        return 1
    manifest, digest = load_manifest(store, args.run_id)
    print(json.dumps({"run_id": args.run_id, "manifest_sha256": digest, "files": len(manifest["files"]),
                      "inputs_fingerprint": manifest["inputs_fingerprint"], "verified": True}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
