# DEBRIEF — Research website build

**Date:** 2026-06-20. **Outcome:** ✅ Live at https://PhilipR19.github.io (push-to-deploy green; auto-rebuilds monthly).

## What shipped
- **Quarto site** (`index`, `research`, `publications`) in a *structured-minimal* design:
  Space Grotesk display / IBM Plex Sans body / IBM Plex Mono metadata; ink-on-paper +
  a single indigo accent. Signature element: the research-program **pathway spine**
  (nutrition → adipose epigenome → storage capacity → health & aging), used as the hero
  thesis and the Research-page section order.
- **Publications pipeline** (`scripts/fetch_publications.py`, stdlib only) — union of
  **Google Scholar ∪ OpenAlex ∪ ORCID**, deduped, keeping both preprint and published
  versions of a paper. ~28 entries. Snapshot in `_publications.md`.
- **Research-themes word cloud** on the front page (`scripts/wordcloud.py`) — a build-time
  SVG packed from paper **titles + abstracts**, inlined so it uses the page web font.
- **CI** (`.github/workflows/publish.yml`) — refresh publications → rebuild word cloud →
  persist abstract cache → render Quarto → deploy to Pages. **Monthly** cron.
- Real **landing + research copy** grounded in published work; email `pmr96@cornell.edu`;
  Google Scholar headshot; public-safe **mock CV** (no DOB/mobile).

## Division of labor
- **Codex** wrote the first engineering pass (ORCID→citations script, tests, CI).
- **Claude** did the design (theme, layout, copy, word cloud) and all the
  data-pipeline iteration that needed live testing (Codex's sandbox had no network).

## Key engineering decisions
- **Publications: union of three sources, not one.** ORCID is curated but incomplete;
  OpenAlex's author disambiguation split Philip across identities (dropping the Trends
  review + Khani Nat Metab paper); Google Scholar is the most complete (has co-authored
  papers absent from both) but has no API. Solution: scrape Scholar for the title list,
  enrich each via OpenAlex for clean authors + DOI, union with ORCID, dedupe. Scholar is
  best-effort; if captcha-blocked in CI it degrades to OpenAlex ∪ ORCID.
- **Keep both preprint + published.** Cluster reworded versions by title similarity, then
  keep the best published AND best preprint per cluster; preprints labelled "· preprint".
- **Regression guards everywhere.** The publications writer refuses to shrink the committed
  snapshot (so a captcha-blocked build can't drop papers); the word-cloud abstract cache
  (`_abstracts.json`) is keyed by DOI and only grows.
- **Abstracts via Semantic Scholar (per-DOI) → OpenAlex fallback.** Both APIs rate-limit
  aggressively (OpenAlex returned a 51-min Retry-After; S2 throttles bursts from local AND
  CI IPs). Mitigation: DOI-keyed cache that accumulates, plus a CI step that commits the
  enriched cache back ([skip ci]) — coverage self-completes over monthly builds. Verified
  working: CI committed `chore: accumulate abstract cache` on its own.
- **Real bug fixed in the original ORCID code:** guarded `issued.date-parts[0][0] == None`
  (the thesis has a DOI but no parseable year) — only surfaced against live data.
- **Pages config fix:** repo was in legacy Jekyll mode (would publish raw `.qmd`); switched
  `build_type` to `workflow`.

## Coverage status (honest)
- Publications: complete (~28, all sources unioned).
- Abstracts in the word cloud: **11 of ~20** papers. The rest are either genuinely
  abstract-less (2 conference talks, the PhD thesis, preprints) or were API-throttled this
  session; the DOI-keyed cache + monthly CICommit-back will fill the throttled ones in over
  coming builds.

## Affiliation note
Confirmed by Philip: **Research Associate, Sander Kersten lab, Cornell University**
(Kersten is now at Cornell Nutritional Sciences; Philip rejoins his PhD advisor). The
prior 2025 CV header still lists the SDU/Kornfeld EMBO postdoc role.

## Open follow-ups (optional, non-blocking)
1. Swap the mock CV for a fuller public CV (update its header to the Cornell role).
2. Top up the last few throttled abstracts in one shot (a free Semantic Scholar API key
   lifts the rate limit), or let the monthly builds accumulate them.
3. Tune word-cloud terms (drop jargon like *chylous*/*ascites* if undesired).
4. Node 20 deprecation warning on `upload-pages-artifact@v3` — cosmetic; bump when convenient.
