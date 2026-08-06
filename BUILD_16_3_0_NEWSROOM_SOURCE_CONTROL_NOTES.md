# Samuga Media Build 16.3.0
## Newsroom Source Control

This build is based directly on Build 16.2.1 Emergency UI Repair. It adds one administrator-only control surface and does not change the public website, article pages, shared Samuga AI drawer, website settings, media, Content Lab, publishing or analytics behavior.

## New admin view

A **Newsroom Sources** item is available to Admin and Super Admin accounts.

The view exposes three backend modes:

- **ARGUS only** — recommended and default. ARGUS is the only automatic editorial source.
- **Hybrid** — ARGUS plus all preserved legacy collectors.
- **Legacy rollback** — legacy collectors active; normal ARGUS news is durably deferred.

The view also shows:

- current mode;
- ARGUS active/deferred state;
- legacy collector active/paused state;
- Google News Discovery active/paused state;
- ARGUS pending and failed queue counts.

Hybrid and legacy changes require a browser confirmation. Every save uses the authenticated admin API and is audit-logged by the backend.

## Backend connection

- `GET /api/admin/news-ingest-mode`
- `POST /api/admin/news-ingest-mode`

The control requires Samuga News Bot Build 18.3.0 or later.

## Preserved behavior

The source control does not alter:

- manual articles and social cards;
- Content Lab approval;
- scoring, Cortex or safety gates;
- official ARGUS Viber weather status;
- Night Mode;
- website/social publishing;
- Samuga AI;
- existing user and role controls.
