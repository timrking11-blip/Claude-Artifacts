#!/usr/bin/env python3
"""Check evidence ledgers against architecture/schemas/evidence-ledger.schema.json and its integrity rules.

  python3 scripts/validate_ledger.py LEDGER.json [LEDGER.json ...] [--profile full|lean]

Prints every error per file and exits 1 if any file fails, 0 if all pass.
--profile also requires each ledger to declare that profile (a proposal run
needs full). The rules are in crm/ledger.py; the profiles in
docs/research-profiles.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm import ledger  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--profile", choices=ledger.PROFILES, default=None)
    args = ap.parse_args(argv)
    failed = 0
    for path in args.paths:
        try:
            data = ledger.load(path)
        except (OSError, ValueError) as exc:
            print(f"{path}: cannot read: {exc}")
            failed += 1
            continue
        errors = ledger.validate(data)
        if args.profile and ledger.profile_of(data) != args.profile:
            errors.append(f"profile is {ledger.profile_of(data)!r}; {args.profile!r} required")
        if errors:
            failed += 1
            print(f"{path}: {len(errors)} error(s)")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"{path}: OK ({ledger.profile_of(data)} profile, {len(data.get('sources') or [])} sources, "
                  f"{len(data.get('claims') or [])} claims)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
