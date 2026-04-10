# forge-chantier-memos — Cron Prompt

## Mission
Work on MemOS in a clean, disciplined way.

## Start-of-session order
1. Read `PRD.md`.
2. Read `.openclaw/crons/jobs.json`.
3. Read `PRIORITIES.md`.
4. Run `memory_search` before any decision.

## Work selection
- If `PRIORITIES.md` has an OPEN item, work on the first OPEN item only.
- If `PRIORITIES.md` is empty, create one useful memory feature.
- For new features, use only memory-relevant signals from:
  - the PRD,
  - `.openclaw/crons/jobs.json`,
  - inspiration repos / patterns,
  - relevant signals / news / raw memory insights.

## Feature rules
A feature is valid only if it clearly improves one of:
- recall quality,
- token savings,
- memory structure,
- reliability,
- observability,
- onboarding,
- import / mining,
- correction / versioning.

## Implementation flow
- Create a branch.
- Implement the change.
- Test it.
- Push it.
- Open a PR.

## End-of-session rule
- Write a short memory note about:
  - what changed,
  - what was learned,
  - what is next.

## Hard rules
- Do not invent progress.
- Do not work on more than one priority at a time.
- Keep the repo single-source-of-truth.
- Stop if the work becomes broad or speculative.
