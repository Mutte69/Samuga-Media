#!/usr/bin/env python3
"""Build 16.3.1 web correctness, proxy, security, and admin recovery tests."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    version = (ROOT / "VERSION.txt").read_text().strip()
    html = (ROOT / "admin.html").read_text()
    js = (ROOT / "admin-build15-9.js").read_text()
    headers = (ROOT / "_headers").read_text()
    require(version == "16.3.1", "website version was not advanced")
    require('data-samuga-build="16.3.1"' in html, "admin build marker is stale")

    article_fn = (ROOT / "functions" / "article.js").read_text()
    story_fn = (ROOT / "functions" / "story.js").read_text()
    for source, label in ((article_fn, "article"), (story_fn, "story")):
        require("16-2-0" not in source, f"{label} SSR still loads old 16.2.0 runtime assets")
        for asset in ("site-v3-16-2-1.css", "website-settings-runtime-16-2-1.css", "website-settings-runtime-16-2-1.js", "samuga-v3-shell-16-2-1.js"):
            require(asset in source, f"{label} SSR is missing current asset {asset}")
        require("SECURITY_HEADERS" in source and "fetchWithTimeout" in source, f"{label} SSR lacks shared security/timeout layer")

    runtime = (ROOT / "functions" / "_lib" / "runtime.js").read_text()
    require("SAMUGA_API_BASE" in runtime, "backend URL is not environment configurable")
    require("AbortController" in runtime, "upstream timeout implementation missing")
    require("x-samuga-edge-signature" in runtime and "SAMUGA_EDGE_PROXY_SECRET" in runtime,
            "signed client identity forwarding missing")

    proxy_files = [
        ROOT / "functions/api/ads.js", ROOT / "functions/api/article.js",
        ROOT / "functions/api/banner.js", ROOT / "functions/api/site-settings.js",
        ROOT / "functions/api/stories.js", ROOT / "functions/api/chat.js",
        ROOT / "functions/api/track.js", ROOT / "functions/api/newsletter/subscribe.js",
        ROOT / "functions/feed.xml.js",
    ]
    for path in proxy_files:
        text = path.read_text()
        require("fetchWithTimeout" in text, f"{path.relative_to(ROOT)} lacks explicit upstream timeout")
        if "newsletter/subscribe" not in str(path):
            require("backendBase" in text, f"{path.relative_to(ROOT)} hardcodes backend routing")

    chat = (ROOT / "functions/api/chat.js").read_text()
    require('catch { return json({ok:false,error:"Invalid JSON"}, 400); }' in chat,
            "malformed chat JSON is not returned as HTTP 400")

    for token in ("Strict-Transport-Security", "X-Frame-Options: DENY", "Referrer-Policy", "Permissions-Policy", "Content-Security-Policy-Report-Only"):
        require(token in headers, f"security header missing: {token}")

    require('id="shareInstagram"' in html and 'data-platform-card="instagram"' in html,
            "Instagram admin publishing controls missing")
    require('id="aiGenerationJobs"' in html and 'id="refreshGenerationJobsBtn"' in html, "AI generation recovery panel missing")
    require("loadGenerationJobs" in js and "generationJobAction" in js and "use_source_copy" in js,
            "AI generation recovery actions are not wired")
    require('"instagram"' in js and "BUFFER_IG_ID" not in js, "Instagram admin target is not provider-neutral")
    for token in ("processing", "retryable", "deferred", "oldest", "database_verified", "Saved in PostgreSQL"):
        require(token in js, f"source-mode operational status is missing: {token}")
    require("The backend did not verify this source-mode change in PostgreSQL." in js,
            "dashboard does not fail closed when source-mode persistence is unverified")

    # The only Samuga backend default may live in the shared runtime helper.
    hardcoded = []
    for path in (ROOT / "functions").rglob("*.js"):
        text = path.read_text()
        if "samuga-news-bot-production.up.railway.app" in text and path.name != "runtime.js":
            hardcoded.append(str(path.relative_to(ROOT)))
    require(not hardcoded, f"hardcoded backend URLs remain outside runtime helper: {hardcoded}")

    js_files = [ROOT / "admin-build15-9.js", *sorted((ROOT / "functions").rglob("*.js"))]
    for path in js_files:
        subprocess.run(["node", "--check", str(path)], check=True, stdout=subprocess.DEVNULL)
    print(f"PASS Build 16.3.1 hardening ({len(js_files)} JavaScript files syntax-checked)")


if __name__ == "__main__":
    main()
