#!/usr/bin/env python3
"""Generate a themed SVG word cloud from the publications snapshot.

Reads paper titles from _publications.md (no network — derived from the
committed list, so it updates whenever the publications do) and packs
horizontal words on a spiral into assets/wordcloud.svg, styled in the
site palette + Space Grotesk. Stdlib only.

Run: python scripts/wordcloud.py
"""
from __future__ import annotations
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBS = ROOT / "_publications.md"
OUT = ROOT / "assets" / "wordcloud.svg"
# Inline include partial — inlined into the page so the SVG can use the
# page's Space Grotesk web font (an <img>-embedded SVG cannot).
OUT_MD = ROOT / "_wordcloud.md"

# Palette (matches custom.scss)
INK, ACCENT, MID, MUTED = "#1A1A1A", "#234E70", "#555555", "#9a9a9a"

STOP = set((
    "the a an and or of to in on for with by from as at is are was were be been "
    "reveals reveal using used use study studies novel role but during between both "
    "via not new male female mice mouse human its their our we upon single day high "
    "function dispensable causes elicits feeding subjects term long-term reduces induces "
    "acts rapid five ways decide future leaders").split())

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


def frequencies(titles: list[str], top: int = 38) -> list[tuple[str, int]]:
    freq: Counter = Counter()
    disp: dict[str, str] = {}
    for title in titles:
        masked = title
        for ph in PHRASES:
            n = len(re.findall(re.escape(ph), masked, flags=re.I))
            if n:
                freq[ph] += n
                disp[ph] = ph
                masked = re.sub(re.escape(ph), " ", masked, flags=re.I)
        for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", masked):
            wl = w.lower()
            if wl in STOP or len(re.sub(r"[^a-z0-9]", "", wl)) < 3:
                continue
            freq[wl] += 1
            disp.setdefault(wl, _display(w))
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
    words = frequencies(_titles())
    svg = build_svg(words)
    OUT.write_text(svg)
    OUT_MD.write_text("```{=html}\n" + svg + "\n```\n")
    print(f"wrote {OUT} and {OUT_MD} ({len(words)} terms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
