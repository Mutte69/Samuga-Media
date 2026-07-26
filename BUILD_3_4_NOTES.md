# Samuga Media — Build 3 + 4

This release completes the planned social-publishing and video-newsroom phases while keeping the Build 2 article editor, revisions, scheduling, advertisements, light/dark modes and Claude-inclusive author fixes.

## Dhivehi typography correction

The public website and Newsroom editor now use regular-weight **Noto Sans Thaana** for Dhivehi. Heavy display weights were removed from headlines, cards and previews. Dhivehi headlines use normal letter spacing and a larger line height for clearer reading.

No custom font file is bundled with the website. The browser loads the standard web font and falls back to a device Thaana font when necessary.

## Phase 3 — publishing centre

- Durable PostgreSQL jobs for Telegram, Facebook and X.
- One platform failing no longer blocks the others.
- Immediate background processing plus a once-per-minute recovery worker.
- Temporary failures retry after 1, 5 and 15 minutes, with a final bounded attempt.
- Separate connection checks that do not publish a test post.
- Desktop Publishing Centre with connection status, queue, recent activity, retry and cancel controls.
- Scheduled articles create the same durable platform jobs when they go live.
- Social status badges distinguish queued, processing, succeeded and failed states.

## Phase 4 — video newsroom

- Image and video drag-and-drop uploads.
- MOV, HEVC and editing-format videos are normalized to H.264 MP4 with browser fast-start.
- Automatic JPEG poster/thumbnail generation.
- Duration, dimensions, codec, source and processing status in the Media Library.
- Failed video processing can be restarted from the dashboard.
- Feed cards load a poster instead of downloading the full video before a reader opens the article.
- Responsive article video player with poster support.
- Telegram Core Team workflow: reply to an image or video with `/webmedia` to import it into Newsroom → Media.
- Pending video jobs survive a Railway restart and are resumed by the scheduler.

## Required deployment detail

The backend Docker image now installs `ffmpeg`. Keep a persistent Railway volume mounted at `/data` and use `CMS_MEDIA_DIR=/data/cms-media`.
