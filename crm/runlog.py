"""One line per run, where the owner looks, and a hold on large creations.

Every run that creates or modifies records writes one entry to the CRM
System's `runlog` collection. The CRM page shows the latest entries in a
"Last runs" strip at the top, and the morning brief lists them. A changelog
alone is not enough: on 21 Sep 2026 the data layer's changelog said "apollo:
15 created" in plain text, nobody read it, and the 15 were duplicates.

The gate: a run that would create more than HOLD_OVER records does not
commit them. It writes a `held` entry naming the records and the one check
that confirms them (see CLAUDE.md: a HOLD clears only after an independent
check), and the records wait until the owner confirms that exact count.

Entries are plain JSON documents, written by the scripts here (as files under
data/runlog/, or into a composition run's CRM batch) and by the routines that
have no repo checkout (to the same shape, straight into the CRM).

CLI, for routine sessions:

  python3 -m crm.runlog entry --run NAME --created N --updated N
        [--name TEXT]... [--check TEXT] [--on-confirm TEXT] [--out FILE]
      Print (or write) one entry. Status is `held` when created > HOLD_OVER.

  python3 -m crm.runlog pending --posted DIR [--out FILE]
      ArtifactData batch entries (op "set", collection "runlog") for every
      data/runlog/*.json not yet among the documents saved in DIR (a
      `list` of the CRM's runlog collection with out_dir).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

#: A run that would create more than this many records holds instead of committing.
HOLD_OVER = 5
#: Collection in the CRM System's database.
COLLECTION = "runlog"
#: Committed entries from runs that have no CRM access of their own (GitHub Actions).
RUNLOG_DIR = config.DATA_DIR / "runlog"
#: How many created names an entry carries; the rest are counted.
MAX_NAMES = 25

STATUS_APPLIED = "applied"
STATUS_HELD = "held"


def _iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def entry_id(run: str, now: datetime) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", run.lower()).strip("-")[:40] or "run"
    return "rl_" + now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + slug


def held(created: int, allow_created: int | None = None) -> bool:
    """True when the run must hold. Confirming means allowing exactly this count."""
    return created > HOLD_OVER and allow_created != created


def line(run: str, detail: str, status: str, created: int) -> str:
    """The one line: 'Weekly sync · apollo 15 created, 52 unchanged · HELD (15 created, over 5)'."""
    tail = f"HELD ({created} created, over {HOLD_OVER})" if status == STATUS_HELD else "applied"
    return f"{run} · {detail} · {tail}" if detail else f"{run} · {tail}"


def entry(run: str, detail: str, created: int, updated: int, now: datetime, *,
          created_names: list[str] | None = None, check: str | None = None,
          on_confirm: str | None = None, allow_created: int | None = None,
          status: str | None = None) -> dict[str, Any]:
    """One runlog document. `status` defaults from the gate."""
    status = status or (STATUS_HELD if held(created, allow_created) else STATUS_APPLIED)
    names = [n for n in (created_names or []) if n]
    doc: dict[str, Any] = {
        "id": entry_id(run, now), "run": run, "at": _iso(now), "status": status,
        "created": created, "updated": updated, "detail": detail,
        "line": line(run, detail, status, created), "threshold": HOLD_OVER,
        "created_names": names[:MAX_NAMES], "created_more": max(0, len(names) - MAX_NAMES),
    }
    if status == STATUS_HELD:
        doc["check"] = check or "open the source and confirm each record above is new, not a duplicate of one already there."
        doc["on_confirm"] = on_confirm or "Tell Claude which check you did and what it showed; the run then applies exactly this count."
    return doc


def write_file(doc: dict[str, Any], directory: Path | None = None) -> Path:
    directory = directory or RUNLOG_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{doc['id']}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return path


def pending(posted_dir: Path | None, directory: Path | None = None) -> list[dict[str, Any]]:
    """Batch `set` entries for committed runlog files the CRM does not have yet."""
    directory = directory or RUNLOG_DIR
    posted: set[str] = set()
    if posted_dir and posted_dir.exists():
        posted = {p.stem for p in posted_dir.rglob("*.json")}
    out = []
    for path in sorted(directory.glob("rl_*.json")) if directory.exists() else []:
        if path.stem not in posted:
            out.append({"op": "set", "collection": COLLECTION, "doc_id": path.stem, "file_path": str(path)})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("entry")
    e.add_argument("--run", required=True)
    e.add_argument("--detail", default="")
    e.add_argument("--created", type=int, default=0)
    e.add_argument("--updated", type=int, default=0)
    e.add_argument("--name", action="append", default=[], help="a created record's name; repeatable")
    e.add_argument("--check", default=None)
    e.add_argument("--on-confirm", default=None)
    e.add_argument("--allow-created", type=int, default=None)
    e.add_argument("--out", type=Path, default=None)
    p = sub.add_parser("pending")
    p.add_argument("--posted", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.cmd == "entry":
        detail = args.detail or f"{args.created} created, {args.updated} updated"
        doc = entry(args.run, detail, args.created, args.updated, datetime.now(timezone.utc),
                    created_names=args.name, check=args.check, on_confirm=args.on_confirm,
                    allow_created=args.allow_created)
        text = json.dumps(doc, indent=2, ensure_ascii=False)
    else:
        text = json.dumps(pending(args.posted), indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
