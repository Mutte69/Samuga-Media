#!/usr/bin/env python3
"""Build 16.3.2 admin newsroom source-control contract tests."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    html = (ROOT / "admin.html").read_text(encoding="utf-8")
    js = (ROOT / "admin-build15-9.js").read_text(encoding="utf-8")
    css = (ROOT / "admin-build15-9.css").read_text(encoding="utf-8")
    version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()

    require(version == "16.3.2", "website version was not advanced")
    require('data-samuga-build="16.3.2"' in html, "admin build marker missing")
    require('data-view="sources"' in html and 'id="view-sources"' in html,
            "Newsroom Sources navigation/view missing")
    for mode in ("argus", "hybrid", "legacy"):
        require(f'name="newsIngestMode" value="{mode}"' in html, f"{mode} mode control missing")
    require('id="saveSourceModeBtn"' in html and 'id="refreshSourceModeBtn"' in html,
            "source control actions missing")
    require('/api/admin/news-ingest-mode' in js, "source mode API connection missing")
    require('ADMIN_ROLES.has(user?.role)' in js, "admin role protection missing")
    require('pendingSourceModeConfirmation' in js and 'Confirm ${sourceModeLabel(selected)}' in js,
            "hybrid/legacy inline confirmation missing")
    require('if (name === "sources") loadNewsIngestMode(true)' in js,
            "source status does not load when view opens")
    require('newsroomModeState' in js and 'renderNewsIngestMode' in js,
            "source mode state rendering missing")
    require('.source-mode-card.selected' in css and '.source-control-summary' in css,
            "source control styling missing")
    require('admin-build15-9.js?v=18.3.2.6' in html and 'admin-build15-9.css?v=18.3.2.6' in html,
            "cache-busting assets were not updated")

    subprocess.run(["node", "--check", str(ROOT / "admin-build15-9.js")], check=True)
    print("PASS Build 16.3.2 newsroom source-control admin UI")


if __name__ == "__main__":
    main()
