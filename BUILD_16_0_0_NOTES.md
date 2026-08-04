# Samuga Media Build 16.0.0 — V3 Clean Public Experience

## Product direction

**Maldives, as it happens.**  
*From every island to every screen.*

Build 16.0.0 modernizes only the public website shell. It preserves the current story API, article preview cards, article rendering, Samuga AI, bilingual filtering, theme preference, analytics, ad source, authors, Cloudflare Pages deployment and admin dashboard.

## Public design changes

- Thin sticky header in the Samuga logo blue.
- Hamburger at the outer left, followed by the supplied white Samuga Media logo.
- EN/DV and light/dark controls at the top right.
- Smooth accessible left drawer on one continuous matte powder-blue surface.
- White Samuga logo, Ask Samuga AI, official social links, categories, free email subscription and policy links inside the drawer.
- Existing homepage article cards retained.
- Responsive ad insertion changed from every six stories to every three visible stories.
- Clean navy footer with the approved Samuga statement.
- The public shell is shared across homepage, article pages and policy pages.

## Newsletter

- New server-side endpoint: `POST /api/newsletter/subscribe`.
- Private provider key: `BUTTONDOWN_API_KEY` in Cloudflare Pages only.
- Honeypot, body-size, email and consent validation included.
- Buttondown's confirmation flow is preserved by not forcing an active subscriber state.
- New `/feed.xml` RSS feed supports one email per newly published website story through Buttondown RSS automation.

## Accessibility and performance

- Drawer uses dialog semantics, focus trapping, Escape close, focus restoration and background inert state.
- Motion is disabled for users who request reduced motion.
- Header and logo dimensions are reserved to reduce layout shifts.
- Newsletter and social states provide accessible labels and live status text.
- Unknown social URLs are disabled rather than guessed.

## Out of scope

No admin, backend, News Bot, story schema, author schema, analytics contract, public API, publishing workflow or article-preview model was redesigned.
