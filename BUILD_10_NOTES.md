# Samuga Media Build 10

## Purpose

Build 10 repairs the public article reader without changing the homepage feed, newsroom workflows, social card creation, analytics, authors, Content Lab, video, or publishing systems.

## Fixed

- Public article cover now appears first, above the headline and byline.
- Cloudflare `/article` and legacy `/story` renderers now use the current Build 10 stylesheet instead of the obsolete `/styles.css` path.
- The document and site chrome remain left-to-right; only the Dhivehi article copy column becomes right-to-left.
- Dhivehi content is held in a centered, bounded reading column and can no longer push the headline, byline, or cover outside the viewport.
- Dhivehi related stories are restricted to Dhivehi; English related stories are restricted to English.
- Static `article.html` and Cloudflare Function output now use the same article structure.
- Article assets have new Build 10 names to prevent old Cloudflare/browser CSS and JavaScript from being reused.
- Newsroom Users table now gives email, role, and author fields safe widths and truncation instead of allowing them to overlap.

## Deployment

1. Deploy the Build 10 backend to Railway.
2. Wait for a healthy deployment.
3. Deploy the Build 10 website to Cloudflare Pages.
4. Hard-refresh once, then open one English and one Dhivehi article.

No new environment variables are required.
