#!/usr/bin/env python3
"""Snapshot a prospect's own website into the repo, from a machine that can reach it.

A composition run's `prepare` fetches the intake domain from the session's
container, and that container's network policy can block the host (it
blocked claridi.ai on 24 Sep 2026, which left that run with a "nothing
found" HOLD). The GitHub runner has open internet, so the
**Site snapshot** workflow runs this script there and commits the text.
`prepare` then falls back to the committed snapshot when its live fetch fails.

Only the intake domain is crawled (the domain lock): the home page, then
same-site links whose paths look like company pages (about, product,
solutions, pricing, customers, team, careers, blog, news, contact), up to
--max-pages. Pages from any other host are never followed.

  python scripts/snapshot_site.py claridi.ai [--max-pages 12]
  python scripts/snapshot_site.py --from-file data/site_snapshots/requests.txt

Writes data/site_snapshots/<domain>/snapshot.json (pages with url, status,
title and text) and snapshot.md (the same text, for a person). Exit 1 if the
home page could not be fetched.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crm.schema import normalize_domain  # noqa: E402

OUT_DIR = ROOT / "data" / "site_snapshots"
UA = "Mozilla/5.0 (compatible; SMI-site-snapshot/1.0)"
PAGE_CHARS = 20_000
INTERESTING = re.compile(
    r"about|company|team|founder|product|platform|solution|how-it-works|feature|pricing|plans|"
    r"customer|case-stud|use-case|career|jobs|blog|news|press|contact|faq|research|method", re.I)


def to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", markup)
    markup = re.sub(r"(?s)<[^>]+>", " ", markup)
    return re.sub(r"\s+", " ", html.unescape(markup)).strip()


def title_of(markup: str) -> str:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", markup)
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if m else ""


def same_site(url: str, domain: str) -> bool:
    host = normalize_domain(urllib.parse.urlsplit(url).netloc) or ""
    return host == domain or host.endswith("." + domain)


def links(markup: str, base: str, domain: str) -> list[str]:
    out: list[str] = []
    for href in re.findall(r"""(?i)href\s*=\s*["']([^"'#]+)""", markup):
        url = urllib.parse.urljoin(base, href.strip())
        if not url.startswith("http") or not same_site(url, domain):
            continue
        url = url.split("?")[0].rstrip("/")
        if url not in out:
            out.append(url)
    return out


def fetch(url: str, timeout: int = 20) -> tuple[int, str, str]:
    """(status, final_url, markup); status 0 on a network error."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read(2_000_000).decode("utf-8", errors="replace") if "html" in ctype or not ctype else ""
            return resp.status, resp.geturl(), body
    except urllib.error.HTTPError as e:
        return e.code, url, ""
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return 0, url, f"__error__{e}"


def snapshot(domain: str, max_pages: int = 12, fetcher=fetch) -> dict:
    domain = normalize_domain(domain) or ""
    if not domain:
        raise ValueError("no domain")
    pages: list[dict] = []
    home_status, home_url, home = 0, "", ""
    for start in (f"https://{domain}/", f"https://www.{domain}/"):
        home_status, home_url, home = fetcher(start)
        if home_status == 200 and home and not home.startswith("__error__"):
            break
    error = home[len("__error__"):] if home.startswith("__error__") else ""
    pages.append({"url": home_url or f"https://{domain}/", "status": home_status, "title": title_of(home),
                  "text": to_text(home)[:PAGE_CHARS] if not error else "", **({"error": error} if error else {})})
    if home_status == 200 and not error:
        queue = [u for u in links(home, home_url, domain) if INTERESTING.search(urllib.parse.urlsplit(u).path)]
        seen = {home_url.rstrip("/")}
        for url in queue:
            if len(pages) >= max_pages:
                break
            if url in seen:
                continue
            seen.add(url)
            status, final, body = fetcher(url)
            if not same_site(final, domain):
                continue  # a redirect off the intake domain is not this company's page
            bad = body.startswith("__error__")
            pages.append({"url": final, "status": status, "title": "" if bad else title_of(body),
                          "text": "" if bad else to_text(body)[:PAGE_CHARS]})
    return {"domain": domain, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fetched_from": "github-actions" if Path("/home/runner").exists() else "local",
            "ok": home_status == 200 and not error, "pages": pages}


def write(snap: dict, out_dir: Path = OUT_DIR) -> Path:
    d = out_dir / snap["domain"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "snapshot.json").write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n")
    md = [f"# Site snapshot — {snap['domain']}", "",
          f"Fetched {snap['fetched_at']} from {snap['fetched_from']}. Home page ok: {snap['ok']}.", ""]
    for p in snap["pages"]:
        md += [f"## {p.get('title') or p['url']}", "", f"<{p['url']}> · HTTP {p['status']}", "",
               p.get("text") or f"(no text{': ' + p['error'] if p.get('error') else ''})", ""]
    (d / "snapshot.md").write_text("\n".join(md))
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("domains", nargs="*")
    ap.add_argument("--from-file", type=Path)
    ap.add_argument("--max-pages", type=int, default=12)
    args = ap.parse_args()
    domains = list(args.domains)
    if args.from_file and args.from_file.exists():
        domains += [ln.split("#")[0].strip() for ln in args.from_file.read_text().splitlines()]
    domains = [d for d in dict.fromkeys(normalize_domain(x) for x in domains) if d]
    if not domains:
        ap.error("give a domain or --from-file")
    failed = 0
    for dom in domains:
        snap = snapshot(dom, args.max_pages)
        path = write(snap)
        print(f"{dom}: {len(snap['pages'])} page(s), home ok={snap['ok']} -> {path.relative_to(ROOT)}")
        failed += 0 if snap["ok"] else 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
