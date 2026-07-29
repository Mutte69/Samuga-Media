# Samuga Media Build 15.9.6 — Relevant Social Images

## Goal

Use the same accurate real-news image selection for social cards that Build 15.9.5 introduced for website covers. When no trustworthy related image exists, use a safe Maldivian scenic image instead of a misleading person or unrelated foreign stock image.

## Image priority

1. Tavily exact/relevant news photo.
2. Maldives scenic fallback from Pexels.
3. Packaged local Maldives/category image, when available.
4. Branded Samuga fallback.

## Tavily relevance improvements

- Scores candidate descriptions and URLs against distinctive headline terms.
- Prefers named people, institutions and places over Tavily's first generic result.
- Gives additional confidence to official Maldives domains.
- Rejects logos, icons, vectors, advertisements, screenshots and posters.
- A healthy Tavily response with no relevant image no longer opens the Tavily failure circuit.
- Searches up to six Tavily results by default within one API request.
- Dhivehi headlines use the writer's English visual keyword when available.

## Maldives fallback pool

Fallbacks include stable, story-specific selections from:

- Malé city aerial and waterfront views
- Local islands and harbours
- Coral reefs and lagoons
- Speedboats and ferries
- Coastlines and ocean views
- Resort/island scenes for tourism stories

The selection is deterministic for each story, so retries keep the same visual.

## Social and website consistency

`fetch_background_image()` is shared by automatic cards, manual cards, Content Lab cards and website-cover generation. The returned image is reused by the publishing pipeline, so the social card and website article can use the same relevant visual.

## Existing protections retained

- Source/outlet names and URLs remain private.
- Tavily hourly cap and circuit breaker remain active.
- Pexels remains a safe fallback.
- First-party Railway media storage remains active.
- Gemini, Buffer, Cortex and AI Usage behavior are unchanged.
