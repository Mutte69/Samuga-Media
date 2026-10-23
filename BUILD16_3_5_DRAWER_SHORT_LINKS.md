# 16.3.5 — white drawer and compact article URLs

## Visible changes

The old sidebar was not included in the previous reader pass. Current-run capture
confirmed a real layering defect: the masthead was z-index 320, but the drawer
was 190, covering its logo and close button. The drawer now sits at 410, its
overlay at 400, and its header/44px close button remain visible while scrolling.
The default is white, with the existing explicit dark preference preserved.

Categories now come first; AI is secondary; unconfigured social links are hidden;
email signup stays available under a closed disclosure. Existing category,
newsletter, social and AI actions are retained. Background controls, including
the floating AI launcher, are inert/hidden while the modal is open. Escape closes
the drawer and restores focus to the menu trigger. Touch panning is allowed in
the drawer while the background stays scroll-locked.

## Short links

New canonical links are `/n/<22-character-code>`: a 25-character path, without the
headline. The complete existing 128-bit routing digest is encoded as URL-safe
base64; it is **not truncated**, an authentication token, or encryption. No
alias table, paid shortener, new database index or primary-key change is needed.
Codes are case-sensitive. Non-canonical unused padding bits are rejected.

The edge converts the short code back to the existing 32-hex-digit public key
before calling the existing parameterized/public-status-filtered API lookup.
Browser links, canonical/OG/share URLs, related stories and RSS links normalize
both old headline paths and new short paths. Legacy `/news/...`, ID and slug URLs
remain resolvable and redirect to the new canonical URL. RSS GUIDs remain intact
to avoid replaying previously delivered entries. API/analytics internal identity
does not change.

Deploy the website route before the bot URL producer. The website can already
normalize the previous backend's long public paths, so rollout does not need an
atomic two-service switch. If rolling back, retain `/n` routing and key decoding
for already-shared links.

## Local evidence

- 1,000 deterministic JS cases verify complete key roundtrips and browser/edge
  parity, plus legacy redirects, canonical output and invalid-code rejection.
- 500 Hypothesis Unicode-ID cases verify the matching Python generator/resolver
  and same-origin validation; every generated path is exactly 25 characters.
- All 48 authoritative bot suites plus compileall passed.
- Website route/link/theme contracts and active JavaScript syntax checks pass.
  The full historical suite still has its eight pre-existing legacy AI-page
  assertions failing; they are not removed or called green.
- Local browser at 390px: drawer is white; its settled bounds begin at x=0,
  close button is visible near y=24; drawer z=410 > header z=320; only the one
  configured social link is visible; main has the native inert attribute;
  Escape restores focus to menuBtn; opening an article uses `/n/...`.

Visual baseline: `/tmp/samuga-drawer-before.png`; settled local result:
`/tmp/samuga-drawer-after-mobile.png`. A screenshot taken during the opening
animation was rejected and replaced. This is not full WCAG certification or a
timed three-second comprehension study. No production stories were generated or
published for these checks.
