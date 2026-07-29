# QA Report — Build 15.9.6

## New relevant-image suite

- 19 checks passed.
- Tavily named-person candidate outranks a generic building candidate.
- Misleading named-person image is rejected.
- A normal Tavily no-match does not count as a provider failure.
- Tavily is attempted before the Maldives scenic fallback.
- Scenic Pexels queries are explicitly Maldivian and are not rewritten.
- The same story receives a stable fallback query.
- Dhivehi headlines use the English visual keyword when available.

## Regression suites

- Build 15.9.5 media recovery: 26 checks passed.
- Build 15.9.5 full-fix regression: 27 checks passed.
- Build 15.9.2 cost-aware diagnostics: 13 checks passed.
- Build 15.9.1 manual pacing: 13 checks passed.
- Build 15.9 cost-leak guard: 41 checks passed.
- Build 15.8 AI Usage: 34 checks passed.
- Source-safety regression: passed.
- Cortex News Director regression: passed.
- AI load-control and idempotency regressions: passed.
- Full Python compile: passed.

## Deployment scope

Backend only. No website asset changes are required.
