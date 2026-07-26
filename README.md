# Samuga Media — Publishing + Video Newsroom Build 3/4

This is the public website and desktop newsroom frontend for Samuga Media.


## Build 3/4 additions

- Thin, regular-weight Dhivehi typography for easy reading
- Durable Telegram, Facebook and X publishing queue
- Publishing Centre with connection checks, retries and cancel controls
- Browser-compatible video conversion and automatic posters
- Dashboard drag-and-drop media library
- Telegram `/webmedia` import workflow
- Scheduled publishing with saved social targets
- Browser recovery, article preview and revision history

## Included

- Minimal light and dark public layout
- English/Dhivehi switch and RTL Thaana presentation
- Featured story, clean card feed, breaking strip and search
- Image and video story cards
- Full-width sponsor banners with `contain` as the safe default, so artwork is not cropped
- Clean article pages with image/video covers, inline media, shares and related stories
- Footer copyright, policy links and clickable “Powered by Samuga Creative” credit
- About, contact, advertising, editorial, corrections, privacy and terms pages
- `/admin.html` desktop newsroom dashboard
- Simple English/Thaana article editor
- Cover and inline image/video uploads
- Draft, review and publish workflow
- Per-platform Telegram, Facebook and X publishing choices
- User roles, advertisement management, website settings and activity log

## Backend

The site calls:

`https://samuga-news-bot-production.up.railway.app`

Deploy the matching Samuga News Bot build first, then deploy this folder to Cloudflare Pages.

## Newsroom login

After the bot is deployed and the CMS environment variables are configured, open:

`https://samugamedia.com/admin.html`

See `DEPLOYMENT.md` for the exact order and variables.

## Policy notice

The included policy pages are Samuga-specific operational drafts. They should be reviewed by a qualified Maldivian legal professional before being treated as final legal advice or final contractual wording.
