#!/usr/bin/env python3
"""Generate a themed SVG word cloud from the publications snapshot.

Reads paper titles from _publications.md (no network — derived from the
committed list, so it updates whenever the publications do) and packs
horizontal words on a spiral into assets/wordcloud.svg, styled in the
site palette + Space Grotesk. Stdlib only.

Run: python scripts/wordcloud.py
"""
from __future__ import annotations
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBS = ROOT / "_publications.md"
OUT = ROOT / "assets" / "wordcloud.svg"
# Inline include partial — inlined into the page so the SVG can use the
# page's Space Grotesk web font (an <img>-embedded SVG cannot).
OUT_MD = ROOT / "_wordcloud.md"
# Cached abstracts so a rate-limited / offline build still has the corpus.
CACHE = ROOT / "_abstracts.json"

ORCID = "0000-0002-4028-8200"
MAILTO = "pmr96@cornell.edu"
OPENALEX = "https://api.openalex.org/works"
S2 = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=abstract"

# Palette (matches custom.scss)
INK, ACCENT, MID, MUTED = "#1A1A1A", "#234E70", "#555555", "#9a9a9a"

STOP = set((
    # function words
    "the a an and or of to in on for with by from as at is are was were be been being "
    "this that these those it its their our we they them he she his her into via not "
    "but during between both upon while which whereas thus therefore however also here "
    "than then when where what who whom can may could would should will more most such "
    "each per other due if no nor only own same so too very s t re ve ll d m o "
    # generic science / abstract filler (domain terms kept: adipose lipid fasting etc.)
    "study studies using used use reveals reveal shows show shown showed novel role "
    "results result resulting demonstrate demonstrated suggest suggests suggesting "
    "indicate indicates indicated observed found increase increased decrease decreased "
    "reduced reduces induces induced induction levels level compared comparison "
    "associated significant significantly respectively groups group control controls "
    "treatment treated effect effects data analysis identified following present "
    "however whether function dispensable causes elicits feeding subjects term reduces "
    "acts rapid five ways decide future leaders new male female mice mouse human "
    "vivo vitro day days week weeks time number total three two one including measured "
    "approach based toward towards single high low higher lower").split())

# Curated multi-word terms kept whole (longest first to avoid sub-phrase counts)
PHRASES = [
    "sulfur amino acid", "fatty acid oxidation", "adipose tissue", "amino acid",
    "fatty acid", "brown adipose", "white adipose", "lipoprotein lipase",
    "adenylyl cyclase", "gene expression", "insulin resistance", "brown fat",
]


def _titles() -> list[str]:
    out = []
    for line in PUBS.read_text().splitlines():
        if not line.startswith("- "):
            continue
        line = re.sub(r"\*\*[^*]+\*\*", "", line)      # drop bold author spans
        m = re.search(r"\*([^*]+)\*", line)            # italic title
        if m:
            out.append(m.group(1))
    return out


def _display(word: str) -> str:
    # keep acronyms / gene names as-is (ANGPTL4, LPL, PPAR), lowercase the rest
    if word.isupper() or any(c.isdigit() for c in word) or re.search(r"[A-Z].*[A-Z]", word):
        return word
    return word.lower()


def _abstract_text(inv: dict | None) -> str:
    """Reconstruct abstract text from OpenAlex's inverted index."""
    if not inv:
        return ""
    positions = [(i, word) for word, idxs in inv.items() for i in idxs]
    positions.sort()
    return " ".join(w for _, w in positions)


def _dois() -> list[str]:
    """DOIs linked in the publications snapshot."""
    found = re.findall(r"https://doi\.org/([^\s)\]]+)", PUBS.read_text())
    return sorted(set(found))


def _fetch_openalex() -> list[str]:
    """All abstracts in a single OpenAlex query (backoff on 429)."""
    params = urllib.parse.urlencode({
        "filter": f"author.orcid:{ORCID}", "per-page": "200",
        "mailto": MAILTO, "select": "abstract_inverted_index",
    })
    url = f"{OPENALEX}?{params}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": f"pr-website/1.0 (mailto:{MAILTO})"})
            with urllib.request.urlopen(req, timeout=30) as r:
                results = json.loads(r.read()).get("results", [])
            return [t for t in (_abstract_text(w.get("abstract_inverted_index")) for w in results) if t]
        except urllib.error.HTTPError as e:  # noqa: PERF203
            if e.code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            break
        except Exception:  # noqa: BLE001
            break
    return []


def _fetch_semanticscholar(dois: list[str]) -> dict:
    """{doi: abstract} from Semantic Scholar. Retries each DOI on 429 with
    backoff (its unauthenticated pool throttles aggressively)."""
    out = {}
    for doi in dois:
        for attempt in range(4):
            try:
                req = urllib.request.Request(S2.format(doi=urllib.parse.quote(doi, safe="")),
                                             headers={"User-Agent": f"pr-website/1.0 (mailto:{MAILTO})"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    a = json.loads(r.read()).get("abstract")
                if a:
                    out[doi] = a
                break
            except urllib.error.HTTPError as e:  # noqa: PERF203
                if e.code == 429:
                    time.sleep(4 * (attempt + 1))
                    continue
                break
            except Exception:  # noqa: BLE001
                break
        time.sleep(1.2)
    return out


def load_cache() -> dict:
    """{doi: abstract_text}, accumulated across builds so coverage only grows."""
    try:
        return json.loads(CACHE.read_text()).get("by_doi", {})
    except Exception:  # noqa: BLE001
        return {}


def _accumulate(text: str, weight: int, freq: Counter, disp: dict) -> None:
    masked = text
    for ph in PHRASES:
        n = len(re.findall(re.escape(ph), masked, flags=re.I))
        if n:
            freq[ph] += n * weight
            disp[ph] = ph
            masked = re.sub(re.escape(ph), " ", masked, flags=re.I)
    for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", masked):
        wl = w.lower()
        if wl in STOP or len(re.sub(r"[^a-z0-9]", "", wl)) < 3:
            continue
        freq[wl] += weight
        disp.setdefault(wl, _display(w))


def frequencies(titles: list[str], abstracts: list[str], top: int = 48) -> list[tuple[str, int]]:
    """Title terms weighted ×3 over abstract terms so the cloud stays on-theme."""
    freq: Counter = Counter()
    disp: dict[str, str] = {}
    for title in titles:
        _accumulate(title, 3, freq, disp)
    for abstract in abstracts:
        _accumulate(abstract, 1, freq, disp)
    return [(disp[w], c) for w, c in freq.most_common(top)]


def _font_size(count: int, lo: int, hi: int) -> float:
    if hi == lo:
        return 34.0
    t = (count - lo) / (hi - lo)
    return 15.0 + (62.0 - 15.0) * math.sqrt(t)


def _color(rank: int, total: int) -> tuple[str, int]:
    """(fill, weight) by frequency rank — accent spent on the top few only."""
    if rank < 2:
        return ACCENT, 600
    if rank < 8:
        return INK, 600
    if rank < 18:
        return MID, 500
    return MUTED, 500


def _overlaps(a, b, pad=6.0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (abs(ax - bx) * 2 < (aw + bw + pad * 2)) and (abs(ay - by) * 2 < (ah + bh + pad * 2))


def build_svg(words: list[tuple[str, int]]) -> str:
    counts = [c for _, c in words]
    lo, hi = min(counts), max(counts)
    placed = []   # (cx, cy, w, h)
    items = []    # (text, cx, cy, fs, fill, weight)
    for rank, (text, count) in enumerate(words):
        fs = _font_size(count, lo, hi)
        w = len(text) * fs * 0.56 + 4   # Space Grotesk approx advance width
        h = fs
        # Archimedean spiral search, slightly wider than tall (landscape cloud)
        cx = cy = 0.0
        theta = 0.0
        while True:
            box = (cx, cy, w, h)
            if not any(_overlaps(box, p) for p in placed):
                break
            theta += 0.28
            r = 9.0 * theta
            cx, cy = r * math.cos(theta), r * 0.62 * math.sin(theta)
        placed.append((cx, cy, w, h))
        fill, weight = _color(rank, len(words))
        items.append((text, cx, cy, fs, fill, weight))

    xs = [cx - w / 2 for cx, _, w, _ in placed] + [cx + w / 2 for cx, _, w, _ in placed]
    ys = [cy - h / 2 for _, cy, _, h in placed] + [cy + h / 2 for _, cy, _, h in placed]
    pad = 14
    minx, maxx, miny, maxy = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    vw, vh = maxx - minx, maxy - miny

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.1f} {miny:.1f} {vw:.1f} {vh:.1f}" '
        f'role="img" aria-label="Word cloud of research themes from Philip Ruppert\'s publications" '
        f'font-family="Space Grotesk, IBM Plex Sans, sans-serif">',
        f'<title>Research themes</title>',
    ]
    for text, cx, cy, fs, fill, weight in items:
        esc = text.replace("&", "&amp;").replace("<", "&lt;")
        parts.append(
            f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="{fs:.1f}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="middle" dominant-baseline="central">{esc}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    titles = _titles()
    by_doi = load_cache()
    missing = [d for d in _dois() if d not in by_doi]
    fresh = _fetch_semanticscholar(missing) if missing else {}
    by_doi.update(fresh)  # accumulate — coverage only grows across builds
    if by_doi:
        CACHE.write_text(json.dumps({"by_doi": by_doi}, ensure_ascii=False, indent=0))
        abstracts = list(by_doi.values())
    else:
        abstracts = _fetch_openalex()  # last resort if nothing is cached yet
    print(f"abstracts: {len(by_doi)} cached (+{len(fresh)} new), {len(missing)} DOIs missing",
          file=sys.stderr)
    words = frequencies(titles, abstracts)
    svg = build_svg(words)
    OUT.write_text(svg)
    OUT_MD.write_text("```{=html}\n" + svg + "\n```\n")
    print(f"wrote {OUT} and {OUT_MD} ({len(words)} terms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
