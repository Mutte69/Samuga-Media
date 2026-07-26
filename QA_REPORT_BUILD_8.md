# Build 8 QA Report

## Passed

- All website JavaScript files pass `node --check`.
- All backend Python files compile successfully.
- All HTML pages have unique IDs.
- All local HTML CSS, JavaScript and image references exist.
- All CSS files have balanced braces.
- All public HTML pages reference Build 8 cache-busted assets.
- Dhivehi article test with `lang="DV"` renders an explicit RTL article while keeping site chrome LTR.
- Chat test at a 390px mobile viewport calculated a 374px panel width with 8px side margins.
- Keyboard-open chat test fitted the panel to the reduced visual viewport.
- Cover source loader test successfully opened a persistent newsroom image.
- Existing `generate_web_cover()` produced a valid 1200×630 PNG.
- All API route decorators were scanned; no duplicate method/path pair was found.
- The new protected branding endpoint is present.
- Remove, replace and branding controls are wired in the editor.

## Requires production smoke test

The build environment cannot use the live Railway database, Telegram, Cloudflare, Facebook or X credentials. After deployment, test:

1. One published Dhivehi article on desktop and iPhone.
2. Samuga AI chat in Telegram's in-app browser with the keyboard open.
3. Uploading a disposable image, removing it from the article and replacing it.
4. Applying Samuga branding and saving the resulting cover.
5. One Content Lab action from Telegram and one from the dashboard to confirm Build 7 synchronization remains intact.
