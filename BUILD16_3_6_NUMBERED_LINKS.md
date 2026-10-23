# 16.3.6 — simple permanent article numbers

The website accepts `/n/12345` style links supplied by the backend. Numbered
routes resolve via `number` rather than assuming a truncated digest is unique.
The backend assigns a database identity with a unique index; headline corrections
do not change the number. Gaps are normal, and the number is not authentication.

The previous 22-character links, title/digest links and query-based links remain
valid. When the backend returns a numbered canonical path, the edge responds to
an old link with a permanent 308 redirect. Browser cards, article/share metadata
and feeds use the backend's canonical numbered path. Existing feed GUIDs stay
unchanged to avoid re-importing old stories as new items.

Deploy this compatibility release before the backend starts issuing numbers.
No typography, theme, image replacement or publication-policy change is included.
Run `node build16_3_6_number_links_tests.mjs` and the previous route/theme tests.
