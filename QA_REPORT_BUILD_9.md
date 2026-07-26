# Build 9 QA Report

## Verified
- All 14 backend Python files compile.
- All website JavaScript files pass `node --check`.
- All public/admin HTML pages have unique element IDs and valid local asset references.
- New API routes have no method/path collisions.
- The dashboard card renderer generated a valid PNG using the same `generate_card()` function as Telegram manual cards.
- Article publishing includes an explicit editor reset after `Publish now` succeeds.
- Author deletion is restricted to Super Admin and requires reassignment when articles or logins still use the profile.
- Web analytics does not store raw reader IP addresses; session IDs are irreversibly hashed server-side.

## Live tests still required
- One disposable card to Telegram Community.
- One disposable card to Facebook/Instagram/X through the existing queue.
- One duplicate-author merge/delete on the production database.
- Analytics page after several real public pageviews.
