# 16.3.3 — Clean Samuga article URLs

The new `/news/[slug]` Pages Function delegates to the shared server-rendered
article handler. The handler resolves the trailing public key through the bot
API, not by guessing the title. Old `/article?id=...`, `/story?id=...` and legacy
slug links remain supported and redirect to the clean canonical URL when the API
supplies it. Homepage, related-story, share, copy and RSS links use `public_path`.
RSS GUIDs remain unchanged to avoid resending old entries. Analytics retains the
original article ID through a metadata tag. Updated scripts are cache-busted.

The website palette now matches the cards: breaking red, politics orange, local
blue, world purple and sports green. No card font or editorial pipeline changed.

Temporary backend failures return non-cacheable 503 rather than a false 404;
article-proxy errors are also non-cacheable. The old duplicate `functions/story.js`
implementation is now an alias, so fixes cannot drift between the two routes.

Local evidence: the new Node contract suite passes public routing, canonical/OG,
sharing, related links, redirects, headline changes, bad paths, upstream status
handling, no-store errors, stable RSS GUIDs, browser helper parity and sports green.
Seven pre-existing function contracts pass, three Python suites pass, and active
JavaScript syntax passes. A real browser navigated homepage → clean article and
legacy link → clean article against synthetic fixtures; the fresh redirect-load
check had no console errors.

The full legacy Python regression file is NOT green: eight failures are present
in both untouched baseline (209/217) and modified source (211/219). They concern
the preserved old standalone AI page and seven extensionless file-reference
checks on it. They were not suppressed. The runner now reports every group even
when one fails. This release deliberately does not delete unrelated legacy pages.

Deploy this website support before bot/API 18.6.4 starts advertising public paths.
Until then, missing `public_path` falls back to existing ID links. Check Cloudflare
Pages deployment separately from GitHub Pages and the Railway bot deployment.
For rollback, preserve the new route and API resolver for already-shared links.

Offline preview: `node preview_public_links.mjs` (localhost port 4187, synthetic
stories, no publication). Full cross-repository engineering/tool comparison:
`BUILD18_6_4_LINKS_ENGINEERING.md` in Mutte69/samuga-news-bot.
