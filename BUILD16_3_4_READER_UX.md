# 16.3.4 — Samuga white-first reader clarity pass

## Scope and design decision

User standard: readers should understand the experience within three seconds;
white by default, optional dark mode, more space, modern and restrained.
This is a bounded improvement to the existing reader site, not a new frontend.
Existing logos, blue masthead, category palette, original Thaana font stack,
publication content, clean article routes and editorial controls are retained.
No paid design or evaluation tool is introduced.

Three seconds is the design target, **not** a measured comprehension claim.

## Screenshot-based inspection

1. **Homepage arrival — needed improvement.** Fresh mobile view opened dark;
   moving live strip and repeated top-story previews competed for attention.
   The headline and community identity were visible, but categories required
   opening the drawer. Baseline `/tmp/samuga-ux-before-home.png`.
2. **Theme choice — worked, inconsistent default.** Theme toggle worked, but
   startup/SSR/system preference and later CMS settings could each choose the
   theme. Baseline `/tmp/samuga-ux-before-light.png`.
3. **Article reading — usable, dense on mobile.** Working canonical article
   navigation, source cover, headline and readable copy; oversized wrapping
   headline and dense presentation delayed access to the body. Baseline
   `/tmp/samuga-ux-before-article.png`.

These captures were inspected during this run. Screenshots alone cannot certify
accessibility or reading comprehension. They do not validate the article facts.

## Changes

- Public HTML and dynamic EN/DV article SSR start light. Only an explicit saved
  `dark` choice opts into dark; invalid/missing/blocked storage falls back light.
- OS preference and late CMS settings no longer silently re-enable dark mode.
  Explicit reader choice persists across reloads and navigation.
- New final-layer stylesheet sets an actual white canvas, more generous gutters,
  calmer card boundaries, readable spacing and visible keyboard focus.
- Duplicate moving ticker and top-stories sidebar are hidden; their stories
  remain available in the normal feed. Featured story and feed remain intact.
- Six visible category filters reuse the existing category engine and drawer
  integration. Pressed state is exposed to assistive technology; labels switch
  with English/Thaana. Active filters/search hide the unrelated featured section.
- Search gets a clear field boundary/focus state; share targets are at least 44px
  high. Mobile chat launcher is compact so it covers less content.
- Thaana RTL direction and existing `MV Faseyha` / `Noto Sans Thaana` font stack
  are preserved. The private admin interface gets release metadata only.

## Verification

- New offline suite: **72 theme-head execution cases** across ten static pages
  and two SSR language editions, including explicit dark/light, invalid/system
  values and blocked storage. SSR also receives a dark CMS default fixture and
  still emits light. Category and settings-precedence contracts pass.
- Existing seven function contracts, public link/redirect contracts, three
  Python hardening/source-control suites and active JavaScript syntax checks pass
  after updating release/cache markers. No behavior assertions were removed.
- Full historical regression remains **221/229**: the same eight pre-existing
  standalone AI-page/extensionless-link assertions remain failing. This release
  does not hide those failures or delete that page to silence tests.
- Local browser: homepage → category → search empty state → clean article route;
  white computed background, explicit dark persistence, language switching,
  native Thaana article RTL and no horizontal document overflow at 390px.
  Desktop layout inspected at 1280px. A loading/blank mobile capture was rejected
  and replaced after the page settled; it is not acceptance evidence.
- Fixtures are explicitly synthetic. No AI messages or production stories were
  generated/published. Local API/analytics routes are fixtures, not production.

Local reproduction: `node preview_public_links.mjs` and open localhost port 4187;
`node build16_3_4_reader_tests.mjs`; `python3 run_current_tests.py` (the historical
eight failures remain). No production rollout is proven by these local tests.

Remaining: actual three-second comprehension testing with readers; native-editor
review of language/copy; full keyboard/screen-reader audit; legacy AI-page policy.
