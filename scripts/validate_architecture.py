#!/usr/bin/env python3
"""Validate architecture/: manifest, ADR files, system-of-record matrix, invariants and code agree.

Checks (each failure is an error unless marked warning):
  decisions    every ADR file is indexed and every index row has its file;
               the file's Status line matches the index; accepted ADRs carry a
               Decided date; the invariants' decision statuses agree, and a
               normative invariant's ADR is Accepted
  authority    ADR-007's transition: while pending, its status reads
               "Accepted; transition pending merge" and no effective commit
               is set; once effective, the status, commit and date agree in
               the ADR and the manifest, the date is not before the decision,
               and (when git is available) the commit is in this history
  matrix       store ids are manifest systems; each current object appears
               once; nothing proposed holds current authority; the current
               owner of architecture decisions follows the transition; field
               groups equal the code constants they name
  code         composition cap, month time zone, bulk-create threshold and
               confirm-note minimum equal crm.costs / crm.runlog; routine
               models are priced (warning when legacy); a governed writer is
               never routed to a Sonnet- or Haiku-class model (ADR-008)
  capabilities four separate facts from a fixed vocabulary; the decision
               status matches the ADR; PRODUCTION_VERIFIED needs criteria
               and a reviewer; every gap reference exists in gaps/README.md
  codeowners   .github/CODEOWNERS covers every path in controls.code_owned_paths
               (enforcement code, tests, docs, artifact pages, itself) and none
               in controls.data_paths_not_code_owned
  hygiene      no personal email addresses or infrastructure identifiers in
               architecture/ (this repository is public)
  digest       protected_digest equals SHA-256 over the authority block, the
               decisions index and system-of-record.yaml

The digest detects a protected section that changed without the digest being
regenerated. It does not authenticate the owner: anyone who can edit the
files can run --update-digest. Nor is CODEOWNERS an approval. Claude's pull
requests are authored by the owner's account, and GitHub never counts an
author's approval; see architecture/README.md, Approval and identity.

  python3 scripts/validate_architecture.py [--update-digest] [--root DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DECISION_STATUSES = ("Proposed", "Accepted", "Superseded", "Deferred", "Not written", "n/a")
IMPLEMENTATION_STATES = ("none", "DESIGNED", "CODE_EXISTS", "CONFIGURED", "EXECUTED", "PRODUCTION_VERIFIED", "RETIRED")
DEPLOYMENTS = ("none", "branch", "default-branch", "routine", "artifact", "external", "github-actions")
TRANSITIONS = ("pending_merge", "effective")
ADR7_PENDING = "Accepted; transition pending merge"
ADR7_EFFECTIVE = "Accepted; effective"
SHA = re.compile(r"^[0-9a-f]{40}$")
LIGHT_MODELS = re.compile(r"sonnet|haiku", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
INFRA = (re.compile(r"\bprojects/[a-z][a-z0-9-]{5,29}\b"), re.compile(r"\b\d{12}\b"),
         re.compile(r"TF_(CLOUD_ORGANIZATION|WORKSPACE)\s*[:=]\s*\S+"))


class Result:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _yaml(path: Path) -> Any:
    import yaml
    return yaml.safe_load(path.read_text())


def _field(text: str, name: str) -> str | None:
    m = re.search(rf"^{re.escape(name)}:\s*(.+?)\s*$", text, re.M)
    return m.group(1) if m else None


def digest(manifest: dict[str, Any], matrix: dict[str, Any]) -> str:
    """SHA-256 over the protected sections, canonical JSON (dates as ISO strings)."""
    payload = {"authority": manifest.get("authority"), "decisions": manifest.get("decisions"),
               "system_of_record": matrix}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- checks ----

def check_decisions(arch: Path, manifest: dict[str, Any], invariants: dict[str, Any] | None, r: Result) -> dict[str, dict]:
    rows = manifest.get("decisions") or []
    by_id: dict[str, dict] = {}
    for d in rows:
        if d["id"] in by_id:
            r.err(f"decisions: {d['id']} listed twice")
        by_id[d["id"]] = d
        if d.get("status") not in DECISION_STATUSES:
            r.err(f"decisions: {d['id']} status {d.get('status')!r} not in {DECISION_STATUSES}")
        f = d.get("file")
        if not f:
            if d.get("status") != "Not written":
                r.err(f"decisions: {d['id']} has no file but is {d.get('status')}")
            continue
        path = arch / f
        if not path.exists():
            r.err(f"decisions: {d['id']} file {f} does not exist")
            continue
        text = path.read_text()
        if not text.startswith(f"# {d['id']} "):
            r.err(f"{f}: first line must be '# {d['id']} — …'")
        status = _field(text, "Status") or ""
        if status.split(";")[0].strip() != d["status"]:
            r.err(f"{f}: Status {status!r} disagrees with the manifest ({d['status']})")
        if d["status"] == "Accepted":
            decided = _field(text, "Decided")
            if not decided or str(d.get("decided")) != decided:
                r.err(f"{f}: an accepted ADR needs 'Decided: {d.get('decided')}' matching the manifest")
    for path in sorted((arch / "adr").glob("ADR-*.md")):
        aid = path.name[:7]
        if aid not in by_id or by_id[aid].get("file") != f"adr/{path.name}":
            r.err(f"adr/{path.name} is not indexed under decisions")
    for d in (invariants or {}).get("decisions") or []:
        row = by_id.get(d["id"])
        if row is None:
            r.err(f"invariants.yaml: {d['id']} is not in the manifest's decisions")
        elif not str(d.get("status", "")).startswith(row["status"]):
            r.err(f"invariants.yaml: {d['id']} status {d.get('status')!r} disagrees with the manifest ({row['status']})")
    for inv in (invariants or {}).get("invariants") or []:
        row = by_id.get(inv.get("adr"))
        if inv.get("standing") == "normative" and (row is None or row["status"] != "Accepted"):
            r.err(f"invariants.yaml: {inv['id']} is normative but {inv.get('adr')} is not Accepted "
                  "(a URL or a filed proposal confers no policy standing)")
    return by_id


def _in_history(sha: str, root: Path) -> bool | None:
    try:
        out = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", sha, "HEAD"],
                             capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode in (0, 1):
        return out.returncode == 0
    return None


def check_authority(arch: Path, root: Path, manifest: dict[str, Any], decisions: dict[str, dict], r: Result) -> None:
    a = manifest.get("authority") or {}
    t = a.get("transition")
    if t not in TRANSITIONS:
        r.err(f"authority.transition {t!r} not in {TRANSITIONS}")
        return
    row = decisions.get(a.get("decision") or "")
    if not row or row.get("status") != "Accepted" or a.get("decision_status") != "Accepted":
        r.err("authority: its decision must be an Accepted ADR in the index")
        return
    text = (arch / row["file"]).read_text()
    status, commit, when = _field(text, "Status"), _field(text, "Effective commit"), _field(text, "Effective date")
    if t == "pending_merge":
        if status != ADR7_PENDING:
            r.err(f"{row['file']}: while pending, Status must read {ADR7_PENDING!r}")
        if a.get("effective_commit") or a.get("effective_date") or commit != "pending" or when != "pending":
            r.err("authority: pending, so no effective commit or date may be recorded anywhere")
        r.warn("authority: ADR-007's transition is pending merge; Notion remains the effective authority")
        return
    if status != ADR7_EFFECTIVE:
        r.err(f"{row['file']}: once effective, Status must read {ADR7_EFFECTIVE!r}")
    sha, eff = str(a.get("effective_commit") or ""), str(a.get("effective_date") or "")
    if not SHA.match(sha) or commit != sha:
        r.err("authority: effective_commit must be a full commit SHA, the same in the ADR and the manifest")
    try:
        if date.fromisoformat(eff) < date.fromisoformat(str(row.get("decided"))) or when != eff:
            r.err("authority: effective_date must match the ADR and may not precede the decision")
    except ValueError:
        r.err("authority: effective_date must be an ISO date")
    if SHA.match(sha):
        found = _in_history(sha, root)
        if found is False:
            r.err(f"authority: effective commit {sha[:12]} is not in this branch's history")
        elif found is None:
            r.warn("authority: git unavailable; effective commit not checked against history")


def check_matrix(manifest: dict[str, Any], matrix: dict[str, Any], r: Result) -> None:
    systems = {s["id"] for s in manifest.get("systems") or []}
    proposed_stores = {s["id"] for s in manifest.get("systems") or [] if s.get("stage") == "proposed"}
    seen: set[str] = set()
    for tier in ("current", "accepted_target", "proposed"):
        for row in matrix.get(tier) or []:
            if row.get("store") not in systems:
                r.err(f"system-of-record {tier}: {row.get('object')!r} store {row.get('store')!r} is not a manifest system")
            for pr in row.get("projections") or []:
                if pr.get("store") not in systems:
                    r.err(f"system-of-record: projection store {pr.get('store')!r} is not a manifest system")
            if tier != "proposed" and row.get("store") in proposed_stores:
                r.err(f"system-of-record {tier}: {row['object']!r} is owned by a proposed store")
            if tier == "current":
                if row["object"] in seen:
                    r.err(f"system-of-record current: {row['object']!r} has more than one write authority")
                seen.add(row["object"])
    a = manifest.get("authority") or {}
    want = a.get("until_effective") if a.get("transition") == "pending_merge" else a.get("after_effective")
    owner = next((c["store"] for c in matrix.get("current") or [] if c["object"] == "architecture decision"), None)
    if owner != want:
        r.err(f"system-of-record: architecture decisions are owned by {owner!r}; the transition says {want!r}")
    from crm import crm_sync
    for name, group in (matrix.get("field_groups") or {}).items():
        mod, _, attr = group["code"].rpartition(".")
        if mod != "crm.crm_sync" or not hasattr(crm_sync, attr):
            r.err(f"field group {name}: {group['code']} does not exist")
            continue
        value = getattr(crm_sync, attr)
        code = {value} if isinstance(value, str) else set(value)
        if code != set(group["fields"]):
            r.err(f"field group {name}: matrix {sorted(group['fields'])} != code {sorted(code)}")


def check_code(manifest: dict[str, Any], r: Result) -> None:
    from crm import costs, runlog
    comp, ctl = manifest.get("composition") or {}, manifest.get("controls") or {}
    for label, have, want in (("composition.monthly_cap", comp.get("monthly_cap"), costs.COMPOSITION_MONTHLY_CAP),
                              ("composition.month_timezone", comp.get("month_timezone"), costs.MONTH_TZ),
                              ("controls.bulk_create_hold_over", ctl.get("bulk_create_hold_over"), runlog.HOLD_OVER),
                              ("controls.min_confirm_check", ctl.get("min_confirm_check"), runlog.MIN_CHECK)):
        if have != want:
            r.err(f"{label} is {have!r} in the manifest but {want!r} in code")
    basis = manifest.get("cost_basis") or {}
    table = basis.get("usd_per_mtok") or {}
    if not basis.get("as_of") or not basis.get("sources"):
        r.err("cost_basis needs as_of and sources")
    for model, row in table.items():
        missing = set(costs.PRICE_FIELDS) - set(row or {})
        if missing:
            r.err(f"cost_basis {model}: missing {sorted(missing)}")
    legacy = set(basis.get("legacy_models") or [])
    for rt in manifest.get("routines") or []:
        model = rt.get("model")
        if model == "session":
            continue
        if model not in table:
            r.err(f"routine {rt['name']}: model {model!r} has no list price in cost_basis")
        elif model in legacy:
            r.warn(f"routine {rt['name']}: runs on legacy model {model}")
        if rt.get("governed_writer") and LIGHT_MODELS.search(str(model)):
            r.err(f"routine {rt['name']}: a governed writer is routed to {model} (ADR-008 keeps them on Opus-class)")


def check_capabilities(arch: Path, manifest: dict[str, Any], matrix: dict[str, Any],
                       decisions: dict[str, dict], r: Result) -> None:
    gaps_text = (arch / "gaps" / "README.md").read_text() if (arch / "gaps" / "README.md").exists() else ""
    gaps = set(re.findall(r"^## (GAP-\d{3})\b", gaps_text, re.M))
    ids: set[str] = set()
    for c in manifest.get("capabilities") or []:
        cid = c.get("id")
        if cid in ids:
            r.err(f"capability {cid} listed twice")
        ids.add(cid)
        for key, vocab in (("decision_status", DECISION_STATUSES), ("implementation_state", IMPLEMENTATION_STATES),
                           ("deployment", DEPLOYMENTS)):
            if c.get(key) not in vocab:
                r.err(f"capability {cid}: {key} {c.get(key)!r} not in {vocab}")
        if not isinstance(c.get("evidence"), list):
            r.err(f"capability {cid}: evidence must be a list (empty when there is none)")
        dec = c.get("decision")
        if dec and dec != "n/a":
            row = decisions.get(dec)
            if row is None:
                r.err(f"capability {cid}: decision {dec} is not indexed")
            elif row["status"] != c.get("decision_status"):
                r.err(f"capability {cid}: decision_status {c.get('decision_status')} but {dec} is {row['status']}")
        if c.get("implementation_state") == "PRODUCTION_VERIFIED" and not (c.get("criteria") and c.get("verified_by")):
            r.err(f"capability {cid}: PRODUCTION_VERIFIED needs written criteria and a reviewer (verified_by)")
        if c.get("gap") and c["gap"] not in gaps:
            r.err(f"capability {cid}: {c['gap']} is not in gaps/README.md")
    text = (arch / "system-of-record.yaml").read_text() + (arch / "target-state.md").read_text()
    for ref in sorted(set(re.findall(r"\bGAP-\d{3}\b", text)) - gaps):
        r.err(f"{ref} is referenced but not in gaps/README.md")


def codeowners_patterns(text: str) -> list[str]:
    return [line.split()[0] for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def code_owned(path: str, patterns: list[str]) -> bool:
    """Whether a repository path is covered. Only directory (`x/`) and rooted file (`/x`) patterns are used."""
    for pat in patterns:
        if pat.endswith("/") and (path == pat or path.startswith(pat.lstrip("/"))):
            return True
        if pat.startswith("/") and path == pat[1:]:
            return True
    return False


def check_codeowners(root: Path, manifest: dict[str, Any], r: Result) -> None:
    path = root / ".github" / "CODEOWNERS"
    ctl = manifest.get("controls") or {}
    if not path.exists():
        r.err(".github/CODEOWNERS is missing")
        return
    patterns = codeowners_patterns(path.read_text())
    for pat in patterns:
        if any(ch in pat for ch in "*?[") or not (pat.endswith("/") or pat.startswith("/")):
            r.err(f"CODEOWNERS pattern {pat!r}: use a directory (x/) or rooted file (/x) so coverage is checkable")
    for want in ctl.get("code_owned_paths") or []:
        if not code_owned(want, patterns):
            r.err(f"CODEOWNERS does not cover {want}")
    for data in ctl.get("data_paths_not_code_owned") or []:
        if code_owned(data, patterns):
            r.err(f"CODEOWNERS covers {data}; automated data pull requests must stay outside owner review")


def check_hygiene(arch: Path, r: Result) -> None:
    for path in sorted(p for p in arch.rglob("*") if p.is_file() and p.suffix in (".md", ".yaml", ".yml")):
        text = path.read_text()
        for m in EMAIL.finditer(text):
            if not m.group(0).startswith("noreply@"):
                r.err(f"{path.relative_to(arch.parent)}: email address {m.group(0)!r} in a public repository")
        for pat in INFRA:
            m = pat.search(text)
            if m:
                r.err(f"{path.relative_to(arch.parent)}: looks like an infrastructure identifier: {m.group(0)!r}")


def check_digest(manifest: dict[str, Any], matrix: dict[str, Any], r: Result) -> str:
    want = digest(manifest, matrix)
    have = str(manifest.get("protected_digest") or "")
    if have != want:
        r.err("protected_digest is stale: a protected section (authority, decisions, system-of-record.yaml) "
              "changed. Regenerate with --update-digest in the same pull request; the owner accepts it by merging")
    return want


def validate(root: Path = ROOT) -> tuple[Result, str]:
    arch = root / "architecture"
    r = Result()
    manifest = _yaml(arch / "architecture-manifest.yaml")
    matrix = _yaml(arch / "system-of-record.yaml")
    inv_path = arch / "invariants.yaml"
    invariants = _yaml(inv_path) if inv_path.exists() else None
    decisions = check_decisions(arch, manifest, invariants, r)
    check_authority(arch, root, manifest, decisions, r)
    check_matrix(manifest, matrix, r)
    check_code(manifest, r)
    check_capabilities(arch, manifest, matrix, decisions, r)
    check_codeowners(root, manifest, r)
    check_hygiene(arch, r)
    want = check_digest(manifest, matrix, r)
    return r, want


def update_digest(root: Path, value: str) -> None:
    path = root / "architecture" / "architecture-manifest.yaml"
    text = path.read_text()
    new, n = re.subn(r"^protected_digest:.*$", f"protected_digest: {value}", text, flags=re.M)
    if n != 1:
        raise SystemExit("architecture-manifest.yaml needs exactly one protected_digest line")
    path.write_text(new)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--update-digest", action="store_true", help="rewrite protected_digest, then validate")
    args = ap.parse_args(argv)
    if args.update_digest:
        _, want = validate(args.root)
        update_digest(args.root, want)
    r, _ = validate(args.root)
    for w in r.warnings:
        print(f"warning: {w}")
    for e in r.errors:
        print(f"ERROR: {e}")
    print(f"{len(r.errors)} error(s), {len(r.warnings)} warning(s)")
    return 1 if r.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
