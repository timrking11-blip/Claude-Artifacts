#!/usr/bin/env python3
"""Cost report (ADR-008): price basis, routine routing, the composition cap, estimates.

Reads architecture/architecture-manifest.yaml. Prints:
  - the dated API list prices and where they were read;
  - each routine's model, its list price and whether the model is legacy;
  - this month's composition runs against the cap (data/runs and, with
    --crm-dump, the CRM runlog);
  - with --usage FILE, an API-list estimate for token usage
    ([{"model": ..., "input": n, "cache_read": n, ...}, ...]).

Everything here is an estimate at API list prices. Sessions and routines bill
against the owner's plan first, then usage credits at standard API rates; the
plan side is not modelled. No actual spend or receipt is read or printed.

  python3 scripts/cost_report.py [--crm-dump DIR] [--runs-dir DIR] [--usage FILE]
                                 [--now ISO] [--json] [--manifest FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm import config, costs, runlog  # noqa: E402
from crm.crm_sync import load_crm_dump  # noqa: E402


def report(manifest: dict[str, Any], now: datetime, runs_dir: Path | None,
           runlog_docs: list[dict[str, Any]], usage: list[dict[str, Any]] | None) -> dict[str, Any]:
    basis = manifest["cost_basis"]
    table = costs.prices(manifest)
    legacy = set(basis.get("legacy_models") or [])
    routines = []
    for r in manifest.get("routines") or []:
        model = r.get("model")
        priced = model in table
        routines.append({"name": r["name"], "model": model, "binding": r.get("binding"),
                         "governed_writer": bool(r.get("governed_writer")),
                         "usd_per_mtok": table.get(model) if priced else None,
                         "legacy": model in legacy,
                         "basis": "API list (estimate)" if priced else "the bound session's model; not priced here"})
    seen = costs.counted_runs(now, runs_dir, runlog_docs)
    comp = manifest["composition"]
    out: dict[str, Any] = {
        "as_of": basis["as_of"], "kind": basis["kind"], "sources": basis["sources"], "note": basis["note"],
        "routines": routines,
        "composition": {"month": costs.month_of(now), "timezone": comp["month_timezone"], "cap": comp["monthly_cap"],
                        "runs": len(seen), "counted": seen,
                        "next_run_holds": len(seen) >= comp["monthly_cap"]},
    }
    if usage is not None:
        rows = [{"model": u["model"], "usd": costs.estimate_usd(u["model"], {k: v for k, v in u.items() if k != "model"},
                                                                table)} for u in usage]
        out["estimate"] = {"rows": rows, "usd": round(sum(r["usd"] for r in rows), 4),
                           "basis": "API list prices; an upper bound where plan usage covers the work"}
    return out


def render(r: dict[str, Any]) -> str:
    lines = [f"Cost basis as of {r['as_of']} ({r['kind']}). Sources: " + ", ".join(r["sources"]),
             "", "Routines:"]
    for x in r["routines"]:
        price = x["usd_per_mtok"]
        rate = f"in ${price['input']}/out ${price['output']} per MTok, cache read ${price['cache_read']}" if price else x["basis"]
        flags = [f for f, on in (("governed writer", x["governed_writer"]), ("LEGACY MODEL", x["legacy"])) if on]
        lines.append(f"  {x['name']}: {x['model']} ({rate})" + (f" [{', '.join(flags)}]" if flags else ""))
    c = r["composition"]
    lines += ["", f"Composition runs in {c['month']} ({c['timezone']}): {c['runs']} of {c['cap']}"
              + (" -- the next run holds for the owner's confirmation" if c["next_run_holds"] else "")]
    for key, where in sorted(c["counted"].items()):
        lines.append(f"  {key}  ({where})")
    if "estimate" in r:
        lines += ["", f"Estimate: ${r['estimate']['usd']:.4f} ({r['estimate']['basis']})"]
    lines += ["", "Estimates only: plan-included usage and actual spend are not modelled here."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=costs.MANIFEST)
    ap.add_argument("--runs-dir", type=Path, default=config.RUNS_DIR)
    ap.add_argument("--crm-dump", type=Path, default=None, help="dump with runlog/ (adds CRM-recorded runs)")
    ap.add_argument("--usage", type=Path, default=None)
    ap.add_argument("--now", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    docs = ([{"id": k, **d} for k, d in load_crm_dump(args.crm_dump, runlog.COLLECTION).items()]
            if args.crm_dump else [])
    usage = json.loads(args.usage.read_text()) if args.usage else None
    r = report(costs.load_manifest(args.manifest), now, args.runs_dir, docs, usage)
    print(json.dumps(r, indent=2, default=str) if args.json else render(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
