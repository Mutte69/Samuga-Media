# Samuga Media Build 6 — Clean Mobile Feed + Shared Content Lab

## Public website

- Removed the public **Newsroom login** link from the footer.
- Removed the oversized lead-story block from the top of the homepage; the public site now opens directly into the Samuga feed.
- Fixed the mobile **Ask Samuga AI** control so the full label remains visible instead of collapsing to a small dot.
- Reworked category navigation into simple, horizontally scrollable chips on mobile and desktop.
- Fixed the Breaking strip so it recognizes the API boolean, the BREAKING category, and urgent fallback wording when older rows were not marked correctly.
- Replaced the unreliable external Faruma font request with Google-hosted Noto Sans Thaana Light/Regular and restrained font weights.

## Newsroom dashboard

- Added a dedicated **Content Lab** section in the left panel.
- Displays the exact generated card image already sent to Telegram.
- Shows headline, caption/Dhivehi text, category, language, time and breaking status.
- Includes the same actions: **Post to Telegram**, **Post to Social**, **Post to All**, **Edit**, and **Reject**.
- Polls every five seconds while open and maintains a pending-card badge in the sidebar.
- Shows recent actions from Telegram and the dashboard.

## Synchronization

- Both Telegram and the dashboard now use the same `approval_queue` and the same `publish_approved_item()` function.
- A dashboard action removes the Telegram inline keyboard and posts an action note to Content Lab.
- A Telegram action removes the item from the dashboard on its next live refresh.
- Atomic queue removal prevents two editors from publishing the same card at the same time.
- Restored Content Lab cards can be regenerated after a Railway restart, so the dashboard preview and publish action do not depend on an in-memory PNG surviving.
