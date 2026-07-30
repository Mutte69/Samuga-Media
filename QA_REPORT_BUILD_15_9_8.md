# QA Report — Build 15.9.8

## Passed

- Python compileall: passed.
- Homepage JavaScript syntax: passed.
- Article JavaScript syntax: passed.
- Cover-guarantee regression suite: 20 checks passed.
- Tavily and Pexels disabled test: bundled fallback still returned a 1600×900 image.
- Bundled fallback generated a valid 1200×630 website cover.
- Backend includes six offline Maldives scenery files.
- Website includes six matching scenery files.
- Database-level missing-cover guard verified.
- Public API missing-cover fallback verified.
- Homepage missing/broken image replacement verified.
- Article-page missing/broken image replacement verified.
- Old-image removal behaviour is not used for article cards.
- Cache-busted website assets point to Build 15.9.8.

## Expected production verification

1. Deploy the website and hard refresh.
2. Confirm old blank cards immediately show Maldives scenery.
3. Deploy backend and confirm `Samuga AI v15.9.8 starting`.
4. Confirm repair logs appear within roughly 45 seconds.
5. Open one old article and one new article; both must display covers.
