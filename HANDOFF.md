# HANDOFF — Build the research website

**From:** ScienceOS session 2026-06-20. **To:** a repo-scoped Claude Code session run from *this* repo (`cd ~/Work/GitHub/PhilipR19.github.io && claude`), or a cloud session against `origin/main`.

## Goal
Build a lean, publications-forward research-program website for Philip Ruppert, served at **https://PhilipR19.github.io**. Quarto + ORCID-auto publications + GitHub Pages.

## Authoritative plan
Full task-by-task implementation plan (with complete, runnable code) is in **`PLAN.md`** in this repo (copied from the ScienceOS spec `docs/superpowers/specs/2026-06-20-research-website-design.md`). Execute it with the superpowers `executing-plans` or `subagent-driven-development` skill.

## Scope (4 tasks)
1. Quarto site skeleton (`_quarto.yml`, `index.qmd`, `research.qmd`, `publications.qmd`, `custom.scss`).
2. ORCID→citations Python build script (`scripts/fetch_orcid.py`, stdlib only) + tests — resolves Philip's 17 ORCID works (`0000-0002-4028-8200`) via doi.org content-negotiation, writes year-grouped `_publications.md`.
3. GitHub Actions `publish.yml` — render Quarto, deploy to Pages (weekly ORCID refresh). Then **Settings → Pages → Source = GitHub Actions**.
4. Landing + research-program narrative copy.

## Human gates (do NOT skip)
- **Task 4 content** carries biographical/scientific claims — draft for Philip, do **not** publish without his sign-off (no invented facts).
- **Affiliation string:** "Research Associate, Sander Kersten lab, Cornell University" (NOT postdoc/Bauer-Rowe). Confirm before go-live.
- Philip provides `assets/photo.jpg` + `assets/cv.pdf`.

## Done-when
- `https://PhilipR19.github.io` serves the site; publications render from ORCID grouped by year with working DOI links; push-to-deploy green; affiliation correct.

## Debrief
On completion, write `DEBRIEF.md` in this repo (tracked + pushed) so the ScienceOS session can ingest it (`/OS-ingest-repo-debrief`).
