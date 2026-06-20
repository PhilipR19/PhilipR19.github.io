# DEBRIEF — Research website build

**Date:** 2026-06-20. **Outcome:** ✅ Live at https://PhilipR19.github.io (push-to-deploy green).

## What shipped
- **Quarto site** (`index`, `research`, `publications`) with a *structured-minimal* design
  (Space Grotesk display / IBM Plex Sans body / IBM Plex Mono metadata; ink-on-paper +
  single indigo accent). Signature element: the research-program **pathway spine**
  (nutrition → adipose epigenome → storage capacity → health & aging) used as the hero
  thesis and the Research-page section order.
- **ORCID → citations pipeline** (`scripts/fetch_orcid.py`, stdlib only) — resolves the
  17 works from ORCID `0000-0002-4028-8200` via doi.org content-negotiation, year-grouped
  with **Ruppert** bolded. Tests pass 2/2.
- **CI** (`.github/workflows/publish.yml`) — render + deploy to Pages on push, weekly
  ORCID refresh cron, committed snapshot as fallback.
- Real **landing + research copy** grounded in published work (no invented facts).
- Email `pmr96@cornell.edu`, headshot from Google Scholar, **mock CV** (public-safe).

## Division of labor
- **Codex** wrote the engineering (ORCID script, tests, CI) from PLAN.md Tasks 2–3.
- **Claude** did the design (theme, layout, copy) and integration.

## Deviations & fixes (not in PLAN.md)
- **Bug fix in `fetch_orcid.py`:** guarded `issued.date-parts[0][0] == None` so a DOI with
  no parseable year (the PhD thesis) lands in an "Other" group instead of crashing.
  Surfaced only by running the live fetch — Codex's sandbox had no network, so this was
  caught locally. (Lesson: exercise external integrations against real data.)
- **Design direction:** chose *structured minimal* (over the plan's litera default), made
  the minimalism meaningful via the pathway signature rather than generic hairlines.
- **CV privacy:** the real 2025 CV contains DOB + personal mobile. Kept it out of git
  entirely; generated a dependency-free **mock CV** with public info only.
- **Pages config fix:** the repo had Pages in *legacy (Jekyll-from-branch)* mode, which
  would have published raw `.qmd`. Switched `build_type` to `workflow`; first deploy job
  raced the switch and failed, re-ran the failed job → green.

## Affiliation note
Confirmed by Philip: **Research Associate, Sander Kersten lab, Cornell University**
(Kersten is now at Cornell Nutritional Sciences; Philip rejoins his PhD advisor). The
2025 CV header still lists the prior EMBO postdoc role at SDU/Kornfeld.

## Open follow-ups (optional, non-blocking)
1. Swap the mock CV for a fuller public CV (and update its header to the Cornell role).
2. Optional: dedupe preprint↔published pairs in the publications list (currently both show).
3. Node 20 deprecation warning on `upload-pages-artifact@v3` — cosmetic; bump when convenient.
