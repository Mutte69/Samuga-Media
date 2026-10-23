# 16.3.7 — operator attention in Publishing centre

Admin/super-admin users can see the durable Telegram news-card attention list
and reconcile unknown or rejected sends. The panel uses existing authenticated
18.6.8+ backend endpoints and does not add a send, retry or delete operation.
Editors and other roles do not fetch the list; server authorization remains
the actual security boundary.

Recording success requires a positive safe-integer message ID, an explicit
checkbox confirming verification in the correct channel, and a note of at
least ten characters. Cancellation records a stop, not a claim that a post
is absent. Active sends and rate-limit waits have no resolution buttons.
The backend arbitrates stale-state conflicts and records the authenticated
actor/note. HTTP/commit uncertainty must be checked by refreshing; no outcome
is invented by the frontend. Load failures are displayed, not shown as clear.

This covers Telegram news-card intents only, not weather/text senders, Buffer
or website publication. Existing publishing retry controls are unchanged and
are not evidence that those other lanes have equivalent guarantees. Reader
design, source/claim quality thresholds and automation settings are unchanged.

`build16_3_7_delivery_controls_tests.mjs` verifies role gating, escaped untrusted
fields, action eligibility, verified receipts, cancellation payloads, conflict
and load-error states. Browser QA used a local offline fixture; no production
resolution or test post was created. Theme styles reuse admin CSS variables.
The local fixture is excluded from the release. Existing legacy AI-page and
literal-version contract failures in the website's full runner remain open.
