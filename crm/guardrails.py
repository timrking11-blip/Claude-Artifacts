"""Guardrails that keep a composition run inside the intake form.

The intake form names one domain. Everything the run reads, spends and cites
is judged against it here, deterministically, so the session that runs the
agents has no room to take liberties:

  - Domain lock: a similarly named company at another domain is never the
    prospect. Any such host in the research, the data-source findings or the
    proposal's citations refuses the run.
  - Credit spend: Apollo organization enrich and Vibe Prospecting enrichment
    cost credits. They run only when the intake form ticked "allow credit
    spend", and only for the intake domain.
  - Empty means empty: when nothing was found on the intake domain, the
    proposal is a not-found note. It may cite the intake domain and primary
    macroeconomic sources, nothing else, and it must say "not found".

Pure functions; tested in tests/test_guardrails.py.
"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlparse

from .schema import normalize_domain

#: Hosts a not-found proposal may still cite for its "Why now" section:
#: government TLDs, and these institutions' own domains and their subdomains.
PRIMARY_MACRO_TLDS = (".gov", ".mil")
PRIMARY_MACRO_DOMAINS = (
    "fed.us", "federalreserve.org", "stlouisfed.org", "kansascityfed.org", "newyorkfed.org",
    "clevelandfed.org", "atlantafed.org", "richmondfed.org", "dallasfed.org", "chicagofed.org",
    "bostonfed.org", "philadelphiafed.org", "minneapolisfed.org", "sanfranciscofed.org",
    "bis.org", "imf.org", "worldbank.org", "oecd.org", "ecb.europa.eu",
)

_URL = re.compile(r"https?://[^\s)\]>\"']+")
_TLD_2 = {"co", "com", "org", "net", "gov", "edu", "ac"}


def host_of(url: str) -> str:
    try:
        host = urlparse(url.strip()).netloc.lower()
    except ValueError:
        return ""
    return host.split("@")[-1].split(":")[0].removeprefix("www.")


def registrable_label(host: str) -> str:
    """'www.clarid.ai' -> 'clarid'; 'news.example.co.uk' -> 'example'."""
    parts = [p for p in host.lower().removeprefix("www.").split(".") if p]
    if len(parts) < 2:
        return parts[0] if parts else ""
    if len(parts) >= 3 and parts[-2] in _TLD_2 and len(parts[-1]) == 2:
        return parts[-3]
    return parts[-2]


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def on_intake_domain(host: str, intake_domain: str) -> bool:
    host, intake = host.lower().removeprefix("www."), (intake_domain or "").lower().removeprefix("www.")
    return bool(intake) and (host == intake or host.endswith("." + intake))


def is_lookalike(host: str, intake_domain: str) -> bool:
    """A different domain whose registrable label is within two edits of, or
    contains / is contained by, the intake domain's label."""
    if not host or not intake_domain or on_intake_domain(host, intake_domain):
        return False
    a, b = registrable_label(host), registrable_label(intake_domain)
    if not a or not b or len(b) < 4:
        return False
    if a == b:
        return True
    if len(a) >= 4 and (a in b or b in a):
        return True
    return _levenshtein(a, b) <= 2


def is_primary_macro(host: str) -> bool:
    """A government host, or one of the listed institutions' domains or subdomains.

    Matches on whole labels only: 'evilfederalreserve.org' is not
    'federalreserve.org'.
    """
    host = host.lower().removeprefix("www.")
    if host.endswith(PRIMARY_MACRO_TLDS):
        return True
    return any(host == d or host.endswith("." + d) for d in PRIMARY_MACRO_DOMAINS)


def urls_in(text: str | None) -> list[str]:
    out: list[str] = []
    for m in _URL.finditer(text or ""):
        u = m.group(0).rstrip(".,;")
        if u not in out:
            out.append(u)
    return out


def lookalike_hosts(urls: Iterable[str], intake_domain: str) -> list[str]:
    seen: list[str] = []
    for u in urls:
        h = host_of(u)
        if h and is_lookalike(h, intake_domain) and h not in seen:
            seen.append(h)
    return seen


def found_on_intake_domain(coverage: dict[str, Any] | None, urls: Iterable[str], intake_domain: str) -> bool:
    """True when any data source or research came back with something for the domain itself."""
    cov = coverage or {}
    if any(str(cov.get(k, "")).lower().startswith("ok") for k in ("ledger", "apollo", "prospecting", "site")):
        return True
    return any(on_intake_domain(host_of(u), intake_domain) for u in urls)


def credit_spend_allowed(manifest: dict[str, Any]) -> bool:
    return bool(((manifest.get("data_sources") or {}).get("allow_credit_spend")))


def check_run(manifest: dict[str, Any], coverage: dict[str, Any] | None, research_text: str,
              data_sources_text: str, proposal_md: str, cited: list[str]) -> list[str]:
    """Every guardrail violation, as one line each. Empty list = the run may file."""
    problems: list[str] = []
    intake = normalize_domain(((manifest.get("state") or {}).get("account") or {}).get("domain"))
    cov = coverage or {}

    if intake:
        research_urls = urls_in(research_text) + urls_in(data_sources_text)
        for where, urls in (("research", research_urls), ("proposal", cited)):
            bad = lookalike_hosts(urls, intake)
            if bad:
                problems.append(f"domain lock: the {where} uses a similarly named company at another domain "
                                f"({', '.join(bad)}); the intake form says {intake}")

        if not found_on_intake_domain(cov, research_urls + cited, intake):
            offside = sorted({host_of(u) for u in cited
                              if not on_intake_domain(host_of(u), intake) and not is_primary_macro(host_of(u))})
            if offside:
                problems.append("empty means empty: nothing was found on " + intake + ", so the proposal may cite only "
                                "that domain and primary macro sources; it cites " + ", ".join(offside))
            if "not found" not in proposal_md.lower():
                problems.append(f"empty means empty: nothing was found on {intake}; the proposal must say so "
                                "(\"not found\") instead of describing the company")

    if not credit_spend_allowed(manifest):
        for key in ("apollo", "prospecting"):
            v = str(cov.get(key, "")).lower()
            if v.startswith("ok"):
                problems.append(f"credit spend: {key} reports data but the intake form did not allow credit spend")
    return problems
