# QA Report — Samuga Media Build 16.2.0

## Result

**PASS — release gate cleared**

- Static audit checks: **294 passed, 0 failed**
- Function contract checks: **7 passed, 0 failed**
- Combined checks: **301 passed, 0 failed**

## Static release gate

Command:

```bash
python3 build16_2_0_full_audit_tests.py
```

Verified:

- all required build files exist;
- public HTML structure and viewport metadata;
- no duplicate DOM IDs;
- local HTML/CSS assets exist;
- image alt attributes and safe new-tab links;
- every public page loads the 16.2.0 shell and settings runtime;
- sticky headers are enabled;
- no stale 16.1.0 shell/runtime reference remains active;
- no custom redirect rule can recreate the AI redirect loop;
- dedicated and floating chat interfaces are separate;
- the floating button/panel use fixed top-level positioning;
- AI settings and independent history namespaces work by contract;
- dynamic article Functions generate the 16.2.0 public shell;
- admin Website Settings controls remain connected;
- cache rules cover current routes and bundles;
- all active JavaScript files pass `node --check`;
- active CSS files have balanced blocks;
- active files are valid UTF-8.

## Function contract gate

Command:

```bash
node --experimental-default-type=module build16_2_0_function_contract_tests.mjs
```

Verified:

- `/article` renders the 16.2.0 shell;
- `/story` renders the 16.2.0 shell;
- dynamic article output includes current settings CSS/JS and clean links;
- chat proxy rejects unsupported methods;
- chat proxy forwards valid JSON and preserves the backend response;
- malformed chat JSON is handled safely;
- site-settings proxy forwards query parameters without caching;
- site-settings public endpoint rejects writes.

## Manual production checks after deployment

1. Open `/ask-samuga-ai` in a private browser window and confirm there is no redirect loop.
2. Open the homepage and confirm the floating AI button stays above the bottom edge while scrolling.
3. Open the drawer and confirm **Ask Samuga AI** opens a full standalone page.
4. Send one message from the floating chat and one from the dedicated page.
5. Open a real article and confirm the header remains sticky and the drawer/AI controls use Build 16.2.0.
6. Check mobile layout on the Samsung and iPhone widths.
