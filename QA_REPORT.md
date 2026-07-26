# QA report — Samuga Media Platform Build 3/4

## Automated checks completed

- All 14 Python source files parsed and compiled successfully.
- All 6 website JavaScript and Cloudflare Pages Function files passed `node --check`.
- All 10 HTML pages passed duplicate-ID and local-resource checks.
- Dashboard JavaScript literal ID selectors were compared with `admin.html`; the only unmatched selector is the intentionally dynamic social checkbox prefix.
- `styles.css` and `admin.css` have balanced rule blocks.
- The bot exposes 39 Flask API routes with no duplicate method/path registrations.
- The new publishing, connection-check, retry, cancel, media-reprocess and Telegram-import routes are registered.
- A real odd-dimension MOV test was converted to H.264/YUV420P MP4 at even dimensions and received an automatic JPEG poster.
- A real H.264 MP4 test was normalized to a fast-start web MP4 without unnecessary video re-encoding.
- The full video-processing function was executed in isolation with a mocked database, confirming its pending → processing → ready flow and source cleanup.
- Public feed cards now render video posters instead of preloading full video files.
- The Newsroom upload flow waits for video readiness before inserting a freshly uploaded cover or inline video.
- Claude's author-profile patch and the earlier editorial consistency protections remain included.
- Docker deployment installs `ffmpeg`; both Dockerfile variants are synchronized.

## Runtime tests required after deployment

The real Railway PostgreSQL database, persistent volume, Telegram channel, Buffer Facebook/X connections and Cloudflare deployment are not available in this environment. Before production use:

1. Confirm startup migrations create `cms_publish_jobs` and the new media metadata columns.
2. Run **Newsroom → Publishing → Check connections**.
3. Publish a private test story to Telegram, Facebook and X separately.
4. Cause or simulate one failed share and confirm retry works.
5. Upload a short iPhone MOV and confirm processing reaches **Ready**.
6. Reply to a Telegram Core Team video with `/webmedia` and verify it appears in the Media Library.
7. Restart Railway and confirm uploaded videos, posters and pending jobs remain available.
8. Check Dhivehi headlines on desktop and mobile in light and dark modes.
