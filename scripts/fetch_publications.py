#!/usr/bin/env python3
"""Fetch Philip Ruppert's publications from OpenAlex (keyed to his ORCID),
dedupe preprint/published versions, and write a year-grouped Markdown
partial (_publications.md).

OpenAlex is a free, API-stable, ToS-friendly aggregator that is more
complete than ORCID's claimed-works list (it finds papers not added to
ORCID) without the captcha/scraping problems of Google Scholar.

Stdlib only. Run: python scripts/fetch_publications.py
"""
from __future__ import annotations
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ORCID = "0000-0002-4028-8200"
MAILTO = "pmr96@cornell.edu"  # OpenAlex "polite pool" — faster, kinder
OPENALEX = "https://api.openalex.org/works"
OUT = Path(__file__).resolve().parent.parent / "_publications.md"
TIMEOUT = 30

# Work types that are not standalone publications (peer-review reports /
# "author response", corrections, editorials, datasets, grants).
DROP_TYPES = {"peer-review", "paratext", "grant", "dataset", "erratum", "editorial"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "pr-website/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _get_accept(url: str, accept: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "pr-website/1.0", "Accept": accept})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


SELECT = "id,display_name,publication_year,doi,type,authorships,primary_location"
ORCID_WORKS_URL = f"https://pub.orcid.org/v3.0/{ORCID}/works"


def _norm_doi(doi: str | None) -> str:
    if not doi:
        return ""
    return doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()


def fetch_openalex_by_author() -> list[dict]:
    """OpenAlex works linked to the ORCID's author entity."""
    params = urllib.parse.urlencode({
        "filter": f"author.orcid:{ORCID}", "per-page": "200",
        "mailto": MAILTO, "select": SELECT,
    })
    return json.loads(_get(f"{OPENALEX}?{params}")).get("results", [])


def fetch_openalex_by_doi(doi: str) -> dict | None:
    """Single OpenAlex work by DOI (recovers papers split off the author entity)."""
    try:
        url = f"{OPENALEX}/https://doi.org/{doi}?" + urllib.parse.urlencode({"mailto": MAILTO, "select": SELECT})
        return json.loads(_get(url))
    except Exception as e:  # noqa: BLE001
        print(f"  ! OpenAlex DOI lookup failed for {doi}: {e}", file=sys.stderr)
        return None


def fetch_orcid_dois() -> list[dict]:
    """DOIs (+title/year fallback) the author has curated on ORCID — the
    ground-truth list, more complete than OpenAlex's author disambiguation."""
    try:
        data = json.loads(_get_accept(ORCID_WORKS_URL, "application/json"))
    except Exception as e:  # noqa: BLE001
        print(f"  ! ORCID works fetch failed: {e}", file=sys.stderr)
        return []
    items = []
    for group in data.get("group", []):
        summary = group["work-summary"][0]
        title = (((summary.get("title") or {}).get("title")) or {}).get("value", "")
        yd = (summary.get("publication-date") or {}).get("year") or {}
        year = yd.get("value") if yd else None
        doi = None
        for eid in ((summary.get("external-ids") or {}).get("external-id") or []):
            if eid.get("external-id-type", "").lower() == "doi":
                doi = (eid.get("external-id-value") or "").strip()
                break
        items.append({"doi": doi, "title": title, "year": year})
    return items


def _orcid_fallback_work(item: dict) -> dict:
    """Build a minimal OpenAlex-shaped record from an ORCID item lacking an
    OpenAlex record, so it still renders."""
    doi = item.get("doi")
    return {
        "display_name": item.get("title") or "Untitled",
        "publication_year": int(item["year"]) if item.get("year") else None,
        "doi": f"https://doi.org/{doi}" if doi else None,
        "type": "article",
        "authorships": [],
        "primary_location": {},
    }


def collect_works() -> list[dict]:
    """Union of OpenAlex-by-author and ORCID-curated DOIs, with OpenAlex
    metadata for every entry."""
    oa = fetch_openalex_by_author()
    print(f"OpenAlex author entity: {len(oa)} works", file=sys.stderr)
    seen = {_norm_doi(w.get("doi")) for w in oa if w.get("doi")}

    orcid_items = fetch_orcid_dois()
    print(f"ORCID curated: {len(orcid_items)} works", file=sys.stderr)
    added = 0
    for it in orcid_items:
        nd = _norm_doi(it.get("doi"))
        if not nd or nd in seen:
            continue
        seen.add(nd)
        w = fetch_openalex_by_doi(it["doi"]) or _orcid_fallback_work(it)
        oa.append(w)
        added += 1
    print(f"recovered {added} ORCID-only works missing from the author entity", file=sys.stderr)
    return oa


def bold_author(name: str) -> str:
    return f"**{name}**" if "ruppert" in name.lower() else name


def _author_list(work: dict) -> str:
    names = []
    for a in work.get("authorships", []) or []:
        nm = ((a.get("author") or {}).get("display_name")) or a.get("raw_author_name") or ""
        nm = nm.strip()
        if nm:
            names.append(bold_author(nm))
    if len(names) > 8:
        names = names[:8] + ["et al."]
    return ", ".join(names)


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _rank(work: dict) -> tuple:
    """Higher is preferred: publishedVersion > journal-hosted > newer year."""
    loc = work.get("primary_location") or {}
    src = loc.get("source") or {}
    published = 1 if loc.get("version") == "publishedVersion" else 0
    journal = 1 if src.get("type") == "journal" else 0
    return (published, journal, work.get("publication_year") or 0)


def _tokens(title: str) -> set:
    return set(_norm_title(title).split())


def _merge_near_dupes(reps: list[dict], threshold: float = 0.6) -> list[dict]:
    """Collapse reworded versions of the same paper (e.g. bioRxiv vs SSRN vs
    journal titles) by token-set Jaccard similarity, keeping the best-ranked."""
    ordered = sorted(reps, key=_rank, reverse=True)  # best first → kept as representative
    kept: list[dict] = []
    for w in ordered:
        tw = _tokens(w.get("display_name", ""))
        if any(tw and (tk := _tokens(k.get("display_name", "")))
               and len(tw & tk) / len(tw | tk) >= threshold for k in kept):
            continue
        kept.append(w)
    return kept


def dedupe(works: list[dict]) -> list[dict]:
    """Drop non-papers, collapse exact-title versions, then merge reworded
    near-duplicate versions to the best one."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for w in works:
        if (w.get("type") or "") in DROP_TYPES:
            continue
        if not (w.get("display_name") or "").strip():
            continue
        groups[_norm_title(w["display_name"])].append(w)
    exact = [max(ws, key=_rank) for ws in groups.values()]
    return _merge_near_dupes(exact)


def format_citation(work: dict) -> str:
    authors = _author_list(work)
    title = (work.get("display_name") or "").rstrip(".")
    src = (work.get("primary_location") or {}).get("source") or {}
    venue = src.get("display_name") or ""
    year = work.get("publication_year")
    doi = work.get("doi") or ""  # full URL (e.g. https://doi.org/10.x) or None
    parts = []
    if authors:
        parts.append(authors + ".")
    parts.append(f"*{title}*.")
    if venue:
        parts.append(venue)
    if year:
        parts.append(f"{year}.")
    line = " ".join(parts)
    if doi:
        url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
        label = url.replace("https://", "").replace("http://", "")
        line += f" [{label}]({url})"
    return line


def year_of(work: dict) -> int:
    return int(work.get("publication_year") or 0)


def main() -> int:
    works = collect_works()
    print(f"{len(works)} works before dedupe", file=sys.stderr)
    reps = dedupe(works)
    print(f"{len(reps)} after dedupe", file=sys.stderr)
    reps.sort(key=lambda w: (year_of(w), _norm_title(w.get("display_name", ""))), reverse=True)

    by_year: dict[int, list[str]] = defaultdict(list)
    for w in reps:
        by_year[year_of(w)].append(format_citation(w))

    lines = ["<!-- generated by scripts/fetch_publications.py — do not edit by hand -->", ""]
    for yr in sorted(by_year, reverse=True):
        header = str(yr) if yr else "Other"
        lines.append(f"### [{header}]{{.pub-year}}")
        lines.append("")
        for c in by_year[yr]:
            lines.append(f"- {c}")
        lines.append("")
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT} ({len(reps)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
