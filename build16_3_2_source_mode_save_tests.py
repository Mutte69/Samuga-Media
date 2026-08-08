#!/usr/bin/env python3
"""Build 16.3.2 newsroom source-mode save UI regression tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
js = (ROOT / "admin-build15-9.js").read_text(encoding="utf-8")
html = (ROOT / "admin.html").read_text(encoding="utf-8")
version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()

assert version == "16.3.2"
assert 'const SAMUGA_BUILD = "18.3.2.6"' in js
assert 'data-samuga-build="16.3.2"' in html
assert 'admin-build15-9.js?v=18.3.2.6' in html
assert 'window.confirm(' not in js[js.index('async function saveNewsIngestMode()'):js.index('async function loadDashboard()')]
assert 'pendingSourceModeConfirmation' in js
assert 'Confirm ${sourceModeLabel(selected)}' in js
assert 'Saving to PostgreSQL…' in js
assert 'timeoutMs:30000' in js
assert 'const readback = await api("/api/admin/news-ingest-mode", {timeoutMs:15000});' in js
assert 'Save read-back mismatch' in js
assert 'Change failed: ${error.message}' in js
assert 'AbortController' in js
print("PASS: Build 16.3.2 source-mode save UI")
