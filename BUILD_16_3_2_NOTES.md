# Samuga Media Build 16.3.2

## Newsroom Sources Save Reliability

### Changes

- Removed `window.confirm()` from Hybrid/Legacy mode changes.
- Hybrid and Legacy now use an inline two-step confirmation: `Apply mode` then `Confirm …`.
- Added a 30-second authenticated API timeout so a stalled request cannot leave the dashboard stuck indefinitely.
- The page shows `Saving to PostgreSQL…` while the request is active.
- A successful POST must report PostgreSQL verification and the exact requested mode.
- The dashboard then performs a second authoritative GET read-back before showing success.
- Failure details are shown inline and in the toast instead of silently reverting or appearing stuck.
- Admin asset cache key advanced to backend build `18.3.2.6`.
- Website version advanced to `16.3.2`.
