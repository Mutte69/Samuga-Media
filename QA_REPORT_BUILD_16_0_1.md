# QA Report — Samuga Media Build 16.0.1

## Result

**PASS for packaged static/regression checks. Live iPhone and production API verification remains required after deployment.**

## Tests completed

- Active homepage references Build 16.0.1 CSS, homepage JS and drawer shell.
- Fatal `safeStorage` initialization order verified fixed.
- Primary scripts evaluated successfully with `localStorage` deliberately throwing.
- Fourteen active JavaScript and Pages Function files passed `node --check`.
- Homepage keeps the existing story-card markup and advertisement-after-three rule.
- Drawer resets to the top on every open.
- Drawer geometry remains LTR while Dhivehi content receives RTL text alignment.
- `100dvh`, vertical scrolling, horizontal overflow protection and sticky drawer controls verified in active CSS.
- Same-origin proxy files verified present for stories, settings, ads, banner, article and chat.
- Ask Samuga AI elements remain present.
- Admin/dashboard files are byte-for-byte identical to the uploaded baseline.
- No `.env`, `.env.local` or `.env.production` files packaged.

## Root causes confirmed

1. `site-build16-0-1.js` initially referenced `safeStorage` before its declaration. This is a JavaScript temporal-dead-zone error and can stop the homepage script before stories render.
2. Global RTL direction was applied to the page shell, reversing/clipping the fixed left drawer on mobile.
3. The drawer preserved its previous scroll position, making it appear incomplete when reopened.
4. Only Telegram had a configured official social URL; the remaining icons had been rendered as disabled.
5. Legacy mobile chat CSS forced the AI panel to nearly full viewport height.
6. Newsletter server code was included as a Pages Function but the observed GitHub Pages deployment is static, so that endpoint cannot run there.

## Limitations

- No live production deployment was performed.
- No real newsletter subscription was sent.
- No exact Facebook, Instagram, TikTok, YouTube or WhatsApp URLs were invented.
- Container Chromium could not provide a trustworthy visual run in this environment; production mobile screenshots remain the final visual acceptance test.
