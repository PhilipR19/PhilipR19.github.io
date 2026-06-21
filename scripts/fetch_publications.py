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
SCHOLAR_USER = "zknZJ8EAAAAJ"
SCHOLAR_URL = (f"https://scholar.google.com/citations?user={SCHOLAR_USER}"
               "&hl=en&cstart=0&pagesize=100")
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
# Scholar entries that are not standalone papers
SKIP_TITLE_PREFIX = ("publisher correction", "author correction", "correction to",
                     "correction:", "corrigendum", "erratum", "reply to",
                     "author response", "comment on", "response to")


def _title_sim(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def fetch_scholar() -> list[dict]:
    """Best-effort scrape of the Google Scholar profile — the most complete
    list. Returns [{title, authors, venue, year}]; [] if blocked/empty."""
    try:
        req = urllib.request.Request(SCHOLAR_URL, headers={
            "User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            page = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"  ! Google Scholar fetch failed: {e}", file=sys.stderr)
        return []
    if 'gsc_a_at' not in page or 'class="g-recaptcha"' in page:
        print("  ! Google Scholar returned no rows (blocked?)", file=sys.stderr)
        return []
    import html as _html
    clean = lambda s: _html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
    out = []
    for row in page.split('class="gsc_a_tr"')[1:]:
        mt = re.search(r'class="gsc_a_at"[^>]*>(.*?)</a>', row, re.S)
        if not mt:
            continue
        title = clean(mt.group(1))
        if not title or title.lower().startswith(SKIP_TITLE_PREFIX):
            continue
        grays = re.findall(r'class="gs_gray">(.*?)</div>', row, re.S)
        authors = clean(grays[0]) if grays else ""
        venue = clean(grays[1]) if len(grays) > 1 else ""
        my = re.search(r'class="gsc_a_y[^"]*"[^>]*>.*?(\d{4})', row, re.S)
        year = my.group(1) if my else (re.search(r"(20\d\d|19\d\d)", venue) or [None])[0]
        out.append({"title": title, "authors": authors, "venue": venue, "year": year})
    return out


def enrich_by_title(title: str) -> dict | None:
    """Resolve a Scholar title to a full OpenAlex work (DOI + authors)."""
    try:
        q = urllib.parse.urlencode({"filter": f"title.search:{title}", "per-page": "1",
                                    "mailto": MAILTO, "select": SELECT})
        res = json.loads(_get(f"{OPENALEX}?{q}")).get("results", [])
    except Exception:  # noqa: BLE001
        return None
    if res and _title_sim(title, res[0].get("display_name", "")) >= 0.7:
        return res[0]
    return None


def _scholar_work(entry: dict) -> dict:
    """OpenAlex-shaped record from Scholar fields (used when OpenAlex has no
    match — e.g. brand-new papers or commentaries)."""
    authors = [{"author": {"display_name": a.strip()}}
               for a in re.split(r",|\band\b", entry.get("authors", "")) if a.strip()]
    venue = re.sub(r"[,\s]*(20\d\d|19\d\d).*$", "", entry.get("venue", "")).strip()
    return {
        "display_name": entry["title"],
        "publication_year": int(entry["year"]) if entry.get("year") else None,
        "doi": None, "type": "article", "authorships": authors,
        "primary_location": {"source": {"display_name": venue}},
    }


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
    """Union of Google Scholar (most complete), OpenAlex-by-author, and
    ORCID-curated works — with OpenAlex metadata wherever available."""
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
        oa.append(fetch_openalex_by_doi(it["doi"]) or _orcid_fallback_work(it))
        added += 1
    print(f"recovered {added} ORCID-only works", file=sys.stderr)

    scholar = fetch_scholar()
    print(f"Google Scholar: {len(scholar)} entries", file=sys.stderr)
    sch_added = 0
    for e in scholar:
        venue = (e.get("venue") or "").lower()
        scholar_published = bool(venue) and not any(p in venue for p in PREPRINT_VENUES)
        w = enrich_by_title(e["title"])
        # Use Scholar's own (published) record if OpenAlex has no match, or only
        # knows the preprint while Scholar shows a journal version of record.
        if w is None or (scholar_published and _is_preprint(w)):
            w = _scholar_work(e)
        if not w.get("doi") and not w.get("publication_year"):
            continue  # no DOI and no year => unverifiable Scholar row / parse artifact
        nd = _norm_doi(w.get("doi"))
        if nd and nd in seen:
            continue  # exact same record already in the pool (dedupe handles title overlap)
        if nd:
            seen.add(nd)
        oa.append(w)
        sch_added += 1
    print(f"added {sch_added} Scholar works", file=sys.stderr)
    return oa


def bold_author(name: str) -> str:
    # Philip's own name is highlighted AND normalised to one canonical form,
    # so it reads consistently regardless of how each source spelled it.
    return "**PMM Ruppert**" if "ruppert" in name.lower() else name


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


PREPRINT_VENUES = ("biorxiv", "medrxiv", "arxiv", "ssrn", "research square",
                   "preprint", "chemrxiv", "authorea", "cold spring harbor")


def _is_preprint(w: dict) -> bool:
    if w.get("type") == "preprint":
        return True
    venue = (((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "").lower()
    return any(p in venue for p in PREPRINT_VENUES)


def _is_published(w: dict) -> bool:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    if loc.get("version") == "publishedVersion" or src.get("type") == "journal":
        return True
    if _is_preprint(w):
        return False
    return bool(src.get("display_name"))  # a journal-like venue (e.g. Scholar fallback)


def dedupe(works: list[dict]) -> list[dict]:
    """Drop non-papers, then cluster reworded versions of the same paper.
    Within each cluster, keep the best PUBLISHED record and (separately) the
    best PREPRINT record — so a preprint and its journal version both appear,
    while same-version duplicates (multiple eLife/bioRxiv records) collapse."""
    items = [w for w in works
             if (w.get("type") or "") not in DROP_TYPES and (w.get("display_name") or "").strip()]
    clusters: list[list[dict]] = []
    for w in items:
        for c in clusters:
            if _title_sim(w["display_name"], c[0]["display_name"]) >= 0.6:
                c.append(w)
                break
        else:
            clusters.append([w])
    reps: list[dict] = []
    for c in clusters:
        published = [w for w in c if _is_published(w)]
        preprints = [w for w in c if not _is_published(w)]
        if published:
            reps.append(max(published, key=_rank))
        if preprints:
            reps.append(max(preprints, key=_rank))
    return reps


def format_citation(work: dict) -> str:
    authors = _author_list(work)
    title = (work.get("display_name") or "").rstrip(".")
    src = (work.get("primary_location") or {}).get("source") or {}
    venue = src.get("display_name") or ""
    if _is_preprint(work):
        venue = f"{venue} · preprint".lstrip(" ·") if venue else "preprint"
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

    # Regression guard: never overwrite the committed snapshot with a SHORTER
    # list. Protects against a captcha-blocked Scholar run (or any source
    # hiccup) silently shrinking the published publications on a weekly build.
    if OUT.exists():
        existing = sum(1 for ln in OUT.read_text().splitlines() if ln.startswith("- "))
        if len(reps) < existing:
            print(f"refusing to shrink {existing} -> {len(reps)} entries "
                  f"(a source was likely incomplete); keeping committed snapshot", file=sys.stderr)
            return 0

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
