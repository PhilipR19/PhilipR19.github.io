#!/usr/bin/env python3
"""Scrape Google Scholar citation metrics and write a small inline partial
(_scholar_metrics.md) linking to the profile. Stdlib only.

Best-effort: if Scholar is unreachable/blocked, the committed partial is
left untouched (never overwritten with nothing).

Run: python scripts/scholar_metrics.py
"""
from __future__ import annotations
import re
import sys
import urllib.request
from pathlib import Path

USER = "zknZJ8EAAAAJ"
PROFILE = f"https://scholar.google.com/citations?user={USER}&hl=en"
OUT = Path(__file__).resolve().parent.parent / "_scholar_metrics.md"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def fetch_metrics() -> dict | None:
    try:
        req = urllib.request.Request(PROFILE, headers={
            "User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"  ! Scholar metrics fetch failed: {e}", file=sys.stderr)
        return None
    # table #gsc_rsb_st: labels (Citations / h-index / i10-index), then the
    # "All" and "Since" value columns interleaved.
    labels = re.findall(r'class="gsc_rsb_sc1"[^>]*>(?:<a[^>]*>)?([^<]+)', page)
    values = re.findall(r'class="gsc_rsb_std">([^<]+)', page)
    if len(labels) < 3 or len(values) < 5:
        print("  ! Scholar metrics not found in page (blocked?)", file=sys.stderr)
        return None
    # values are [all, since] per row → take the "all" column (even indices)
    return {"citations": values[0], "h_index": values[2], "i10_index": values[4]}


def render(m: dict) -> str:
    return (
        "```{=html}\n"
        f'<a class="scholar-metrics" href="{PROFILE}" target="_blank" rel="noopener" '
        'aria-label="Google Scholar profile and citation metrics">\n'
        f'  <span class="gs-stat"><b>{m["citations"]}</b> citations</span>\n'
        f'  <span class="gs-stat"><b>{m["h_index"]}</b> h-index</span>\n'
        f'  <span class="gs-stat"><b>{m["i10_index"]}</b> i10-index</span>\n'
        '  <span class="gs-go">Google Scholar ↗</span>\n'
        "</a>\n"
        "```\n"
    )


def main() -> int:
    m = fetch_metrics()
    if not m:
        print("keeping committed _scholar_metrics.md", file=sys.stderr)
        return 0
    OUT.write_text(render(m))
    print(f"wrote {OUT}: {m}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
