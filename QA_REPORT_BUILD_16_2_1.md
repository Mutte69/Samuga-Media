# Samuga Media Build 16.2.1 — QA Report

## Result

- Static and integration-contract checks: **197/197 passed**
- Headless layout and interaction contracts: **passed**
- JavaScript syntax checks: **passed**
- Deployment archive integrity: run during final packaging

## Root causes verified and repaired

1. The page-entry animation retained a transformed `body`. That changed the containing block for `position: fixed`, causing Ask Samuga AI to follow document/footer geometry instead of the viewport.
2. `overflow-x: hidden` on `html/body` interfered with the sticky header's scroll container.
3. The featured media grid item stretched to match the long headline while the inner media did not fill it, producing the large blank area.
4. The settings runtime replaced the Samuga-blue header with the page background in light mode, leaving the white logo and controls almost invisible.
5. The homepage and shell contained competing chat binders, while the sidebar linked to an unwanted standalone page.

## Browser-layout contracts tested

The active Build 16.2.1 CSS and JavaScript were mounted into a Chromium document and measured at desktop and mobile viewports.

### Desktop — 1440 × 1000

- Sticky header remained at `y = 0` after scrolling 700 px.
- Header background computed as `rgb(41, 184, 254)`.
- Floating AI button remained 18 px above the viewport bottom before and after scrolling.
- Featured frame: approximately `476.75 × 297.97`.
- Inner media/image filled the frame, allowing only the expected 1 px border difference and no blank reserved panel.
- Sidebar AI control was a `BUTTON`, had no navigation URL, and opened the shared chat controller.

### Mobile — 430 × 932

- Header remained 56 px high with the Samuga-blue background.
- Featured frame measured `404 × 252.5`, matching the intended 16:10 ratio.
- Featured image filled the media frame.
- Headline used approximately `31.39 px`, full available width, normal word wrapping, and no arbitrary mid-word breaking.
- Floating AI button remained 14 px above the viewport bottom.
- Open chat measured `410 × 560` and appeared as a bottom sheet rather than a forced full-screen page.

## AI behavior

- Removed the standalone Ask Samuga AI page and active references to it.
- Floating button and sidebar button use one shared overlay controller.
- Open/close uses opacity and transform transitions.
- Escape and close-button behavior remain available.
- Mobile keyboard handling uses `visualViewport` when available.
- Session chat-history persistence remains handled by the website-settings runtime.
- `/api/chat` remains the existing backend endpoint.

## Files added

- `site-build16-2-1.css`
- `site-v3-16-2-1.css`
- `site-build16-2-1.js`
- `samuga-v3-shell-16-2-1.js`
- `website-settings-runtime-16-2-1.css`
- `website-settings-runtime-16-2-1.js`
- `BUILD_16_2_1_NOTES.md`
- `QA_REPORT_BUILD_16_2_1.md`
- `build16_2_1_tests.py`

## Files updated

- All public HTML pages now load the Build 16.2.1 assets.
- `_headers`
- `_redirects`
- `VERSION.txt`

## Files removed

- `ask-samuga-ai.html`
- `ask-samuga-ai-16-2-0.js`
- `ask-samuga-ai-16-2-0.css`

## Database and backend

- No database migration is required.
- No Railway API contract was changed.
- Website Settings and `/api/site-settings` remain in place.

## Honest deployment limitation

The repaired assets were tested in a controlled Chromium layout and interaction harness. The production domain itself cannot be deployed or cache-purged from this environment. After uploading to Cloudflare Pages, verify the new `16.2.1` asset filenames in a private browser window so an older cached HTML page is not mistaken for this build.
