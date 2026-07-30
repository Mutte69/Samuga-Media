# Samuga Media Build 15.9.8 — Every Article Cover Guarantee

## Permanent rule
Every public article must have a cover image. If a trustworthy story-specific
image cannot be found, Samuga uses Maldives scenery. Blank cards and branding-only
error placeholders are not permitted.

## Four protection layers

1. **Image selection:** Tavily → Pexels Maldives query → bundled offline Maldives scenery.
2. **Database:** publishing assigns a deterministic scenery URL when a caller supplies no cover.
3. **Public API:** `/api/stories` and `/api/article` always return a cover URL.
4. **Browser:** missing or broken image URLs are replaced by a deterministic bundled scenery asset.

## Old article recovery

- Full practical archive lookback: 3,650 days.
- 50 articles per repair batch by default.
- Repair repeats every five minutes.
- Frontend fallback appears immediately while permanent database repair continues.

## Bundled fallback scenes

- Malé city aerial
- Island and lagoon
- Coral reef
- Speedboat
- Lagoon beach
- Island harbour

The fallback selection is deterministic per article, so the same story keeps the
same image across refreshes and restarts.
