# Samuga News Bot — Build 12

Build 12 combines an analytics accuracy repair with a structured newsroom AI pipeline.

## Analytics accuracy

The Cloudflare dashboard and Samuga dashboard were not measuring the same thing:

- Cloudflare Zone Analytics includes edge requests for HTML, images, scripts, APIs and other traffic over its selected historical range.
- Samuga first-party analytics records public browser page-load events only after its tracker was deployed.

Build 12 keeps the two sources separate instead of forcing incompatible numbers to match.

### First-party fixes

- Each real page load now sends a unique `event_id`.
- The backend deduplicates only retry copies of the same event.
- Reopening the same page in the same hour is counted as another pageview.
- The trend chart includes zero days and uses valid dashboard theme variables.
- Coverage start, lifetime events and last event are visible.
- Homepage, article, story and policy pages all load the same-origin tracker.

### Optional Cloudflare historical overview

When Railway has the following variables, the dashboard also loads aggregate Cloudflare zone data server-side:

```text
CLOUDFLARE_ZONE_ID=<samugamedia.com zone id>
CLOUDFLARE_ANALYTICS_TOKEN=<scoped token with Zone Analytics Read>
```

Optional:

```text
CLOUDFLARE_ANALYTICS_MAX_DAYS=31
```

The token is never sent to dashboard JavaScript. Cloudflare data is cached for five minutes and displayed in a separate panel as edge requests, HTML page views and peak daily unique visitors.

## Structured AI pipeline

When `DEEPSEEK_API_KEY` is configured, automatic newsroom writing now follows this path:

```text
Raw feed / source material
        ↓
DeepSeek V4 Flash
(strict evidence-only JSON fact pack)
        ↓
Claude Haiku 4.5             Gemini 3.5 Flash-Lite
(final English tone)         (final natural Thaana)
```

DeepSeek is not treated as a source. It may only normalize facts found in the supplied material. The validated pack records facts, people, organizations, locations, dates, numbers, quotes, unknowns, conflicts and image keywords.

The pipeline is connected to the active paths for:

- automatic English social-card captions;
- automatic English website article bodies;
- automatic Dhivehi captions;
- full English/Dhivehi story-builder output.

If DeepSeek is not configured, times out or returns invalid JSON, Build 11 behaviour remains available as a compatibility fallback.

## Required AI variable

```text
DEEPSEEK_API_KEY=<your DeepSeek API key>
```

Recommended defaults already built in:

```text
DEEPSEEK_MODEL=deepseek-v4-flash
CLAUDE_EDITOR_MODEL=claude-haiku-4-5-20251001
GEMINI_MODELS=gemini-3.5-flash-lite,gemini-2.5-flash-lite
```

## Editorial safety

- Final writers are instructed to use only the verified fact pack.
- Unknown facts remain unknown instead of being guessed.
- Existing headline/body person-consistency checks remain active.
- DeepSeek JSON is parsed and normalized before another model sees it.
- Invalid or fact-free JSON is rejected.
- Fact packs are cached to avoid paying twice for the same story.
