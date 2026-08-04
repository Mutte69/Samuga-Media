#!/usr/bin/env python3
"""Static release-gate checks for Samuga Media Build 16.2.0."""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
PUBLIC_HTML = [
    "index.html", "article.html", "ask-samuga-ai.html", "about.html",
    "advertising.html", "contact.html", "editorial-policy.html",
    "corrections-policy.html", "privacy-policy.html", "terms.html",
]
ACTIVE_JS = [
    "site-build16-2-0.js",
    "samuga-v3-shell-16-2-0.js",
    "website-settings-runtime-16-2-0.js",
    "ask-samuga-ai-16-2-0.js",
    "admin-website-settings-16-2-0.js",
    "site-common-build16-0-1.js",
    "site-transitions-build15-2.js",
    "analytics-build12.js",
    "article-build16-0-1.js",
    "admin-build15-9.js",
    "functions/article.js",
    "functions/story.js",
    "functions/api/chat.js",
    "functions/api/site-settings.js",
    "functions/api/stories.js",
    "functions/api/article.js",
    "functions/api/banner.js",
    "functions/api/ads.js",
    "functions/api/track.js",
    "functions/api/newsletter/subscribe.js",
    "functions/feed.xml.js",
]
ACTIVE_CSS = [
    "site-build15-2.css",
    "site-v3-16-0-1.css",
    "website-settings-runtime-16-2-0.css",
    "ask-samuga-ai-16-2-0.css",
    "admin-build15-9.css",
    "admin-website-settings-16-2-0.css",
]

passes: list[str] = []
failures: list[str] = []
warnings: list[str] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    if condition:
        passes.append(label)
    else:
        failures.append(f"{label}{': ' + detail if detail else ''}")


def text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def soup(name: str) -> BeautifulSoup:
    return BeautifulSoup(text(name), "html.parser")


def local_path(raw: str) -> Path | None:
    raw = (raw or "").strip()
    if not raw or raw.startswith(("#", "data:", "mailto:", "tel:", "javascript:")):
        return None
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path
    if not path or path == "/":
        return None
    candidate = path.lstrip("/")
    # Clean public routes are handled by Cloudflare and are not asset files.
    if "." not in Path(candidate).name:
        return None
    return ROOT / candidate


# 1. Required release files.
for name in PUBLIC_HTML + ACTIVE_JS + ACTIVE_CSS + ["_headers", "_redirects", "CNAME"]:
    check((ROOT / name).is_file(), f"required file exists: {name}")

# 2. HTML integrity, asset references, IDs, basic accessibility/security.
for name in PUBLIC_HTML:
    doc = soup(name)
    raw = text(name)
    check(doc.html is not None and doc.head is not None and doc.body is not None, f"valid document skeleton: {name}")
    check(doc.find("meta", attrs={"name": "viewport"}) is not None, f"viewport meta present: {name}")
    if name != "admin.html":
        check(doc.html.get("data-samuga-build") == "16.2.0", f"build marker 16.2.0: {name}")
    ids = [node.get("id") for node in doc.find_all(attrs={"id": True})]
    dupes = [key for key, count in Counter(ids).items() if count > 1]
    check(not dupes, f"no duplicate DOM IDs: {name}", ", ".join(dupes))

    missing = []
    for node, attr in [(n, "src") for n in doc.find_all(src=True)] + [(n, "href") for n in doc.find_all(href=True)]:
        p = local_path(node.get(attr, ""))
        if p and not p.exists():
            missing.append(node.get(attr, ""))
    check(not missing, f"all local HTML assets exist: {name}", ", ".join(sorted(set(missing))))

    imgs_without_alt = [str(img)[:100] for img in doc.find_all("img") if img.get("alt") is None]
    check(not imgs_without_alt, f"all images have alt text: {name}")

    unsafe_blank = [a.get("href", "") for a in doc.select('a[target="_blank"]') if "noopener" not in (a.get("rel") or [])]
    check(not unsafe_blank, f"new-tab links use noopener: {name}", ", ".join(unsafe_blank))
    check("javascript:" not in raw.lower(), f"no javascript: URLs: {name}")

# 3. All public pages use the active shell/runtime and sticky header.
for name in [n for n in PUBLIC_HTML if n != "admin.html"]:
    raw = text(name)
    check("samuga-v3-shell-16-2-0.js" in raw, f"active drawer shell loaded: {name}")
    check("website-settings-runtime-16-2-0.js" in raw, f"active settings runtime loaded: {name}")
    check("website-settings-runtime-16-2-0.css" in raw, f"active settings CSS loaded: {name}")
    check("settings-sticky-header" in raw, f"sticky header enabled: {name}")
    check("samuga-v3-shell-16-1-0.js" not in raw and "website-settings-runtime-16-1-0" not in raw,
          f"no stale 16.1 runtime reference: {name}")

# 4. Redirect-loop regression checks.
redirect_lines = [line.strip() for line in text("_redirects").splitlines() if line.strip() and not line.lstrip().startswith("#")]
check(not redirect_lines, "no custom redirect/rewrite rules can fight Cloudflare Pretty URLs", " | ".join(redirect_lines))
check("/ask-samuga-ai.html" not in text("samuga-v3-shell-16-2-0.js"), "drawer never links to .html AI route")
ask = soup("ask-samuga-ai.html")
canonical = ask.find("link", rel="canonical")
check(canonical is not None and canonical.get("href", "").endswith("/ask-samuga-ai"), "AI page canonical uses clean URL")
check(ask.body.get("data-floating-ai") == "disabled" and "ai-page" in (ask.body.get("class") or []), "AI page explicitly disables floating widget")
check(ask.find(id="aiPageForm") is not None and ask.find(id="aiPageMessages") is not None, "AI page owns a standalone chat UI")
check(ask.find(id="chatFab") is None and ask.find(id="chatPanel") is None, "AI page contains no floating-chat duplicate")

# 5. Floating widget regression checks.
index = soup("index.html")
check(index.find(id="chatFab") is not None and index.find(id="chatPanel") is not None, "homepage includes floating AI controls")
runtime_css = text("website-settings-runtime-16-2-0.css")
check(re.search(r"body\s*>\s*\.chat-fab\s*\{[^}]*position\s*:\s*fixed", runtime_css, re.S | re.I) is not None,
      "floating AI button is fixed as a direct body child")
check(re.search(r"body\s*>\s*\.chat-panel\s*\{[^}]*position\s*:\s*fixed", runtime_css, re.S | re.I) is not None,
      "floating AI panel is fixed as a direct body child")
check("env(safe-area-inset-bottom" in runtime_css, "floating AI respects mobile safe area")
check("z-index: 2147483000" in runtime_css or "z-index:2147483000" in runtime_css, "floating AI has top-level stacking priority")
runtime_js = text("website-settings-runtime-16-2-0.js")
check('document.body.appendChild(fab)' in runtime_js and 'document.body.appendChild(panel)' in runtime_js,
      "runtime moves floating controls outside footer/layout containers")
check('document.body.classList.contains("ai-page")' in runtime_js, "runtime excludes dedicated AI page from floating relocation")
shell_js = text("samuga-v3-shell-16-2-0.js")
check('href="/ask-samuga-ai"' in shell_js, "sidebar AI opens dedicated clean-route chatbot")
check('dataset.floatingAi' in shell_js and 'ai-page' in shell_js, "shell will not inject floating chat into dedicated page")
check('fab.dataset.chatBound' in shell_js, "generic chat binding is idempotent")
site_js = text("site-build16-2-0.js")
check('dataset.chatBound' in site_js, "homepage chat binding is idempotent")
check('boolSetting' in site_js and 'ai_floating_enabled' in site_js, "homepage respects typed AI visibility settings")

# 6. Dedicated chat behavior and independent history.
ask_js = text("ask-samuga-ai-16-2-0.js")
for needle, label in [
    ('samuga-ai-page-history-v1', "dedicated AI uses separate session history"),
    ('surface: "dedicated-page"', "dedicated AI identifies its surface to backend"),
    ('#aiClearChat', "dedicated AI supports clearing chat"),
    ('form?.requestSubmit()', "prompt buttons submit through one form path"),
    ('event.key === "Enter" && !event.shiftKey', "Enter sends while Shift+Enter remains available"),
]:
    check(needle in ask_js, label)
check('samuga-ai-floating-history-v2' in runtime_js, "floating AI uses its own history namespace")

# 7. Dynamic article routes must match the public shell, not an old build.
for name in ["functions/article.js", "functions/story.js"]:
    raw = text(name)
    check('data-samuga-build="16.2.0"' in raw, f"dynamic article build marker updated: {name}")
    check('samuga-v3-shell-16-2-0.js' in raw, f"dynamic article uses active shell: {name}")
    check('website-settings-runtime-16-2-0.js' in raw and 'website-settings-runtime-16-2-0.css' in raw,
          f"dynamic article receives live website settings: {name}")
    check('settings-sticky-header' in raw, f"dynamic article header stays sticky: {name}")
    check('/about.html' not in raw and '/contact.html' not in raw, f"dynamic article footer uses clean routes: {name}")
    check('samuga-v3-shell-16-0-1.js' not in raw, f"dynamic article has no stale shell: {name}")

# 8. Admin website-settings connection remains intact.
admin = text("admin.html")
admin_js = text("admin-website-settings-16-2-0.js")
for needle, label in [
    ('data-view="site"', "admin has Website Settings navigation"),
    ('data-settings-section="ai"', "admin has Samuga AI settings section"),
    ('data-setting="ai_floating_enabled"', "admin controls floating AI"),
    ('data-setting="ai_sidebar_enabled"', "admin controls sidebar AI"),
    ('data-setting="ai_button_position"', "admin controls floating-button position"),
    ('admin-website-settings-16-2-0.js', "admin loads active settings controller"),
]:
    check(needle in admin, label)
check('flat.ai_enabled=flat.show_ai_chat' in admin_js, "admin maintains backend-compatible AI enabled field")
check('website_settings_v2' in admin_js, "admin saves versioned website settings payload")

# 9. Cache policy regression checks.
headers = text("_headers")
for route in ["/ask-samuga-ai", "/article*", "/admin*", "/site-build16-2-0.js", "/samuga-v3-shell-16-2-0.js", "/website-settings-runtime-16-2-0.css"]:
    check(route in headers, f"cache policy covers {route}")
check("no-cache, no-store, must-revalidate" in headers, "HTML is protected from mixed-build caching")
check("max-age=31536000, immutable" in headers, "versioned assets use immutable caching")

# 10. JavaScript syntax gate.
for name in ACTIVE_JS:
    path = ROOT / name
    if not path.exists():
        continue
    result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    check(result.returncode == 0, f"JavaScript syntax valid: {name}", (result.stderr or result.stdout).strip())

# 11. CSS references and simple structural integrity.
url_re = re.compile(r"url\((?:['\"]?)([^)'\"]+)")
for name in ACTIVE_CSS:
    path = ROOT / name
    if not path.exists():
        continue
    raw = text(name)
    stripped = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    check(stripped.count("{") == stripped.count("}"), f"balanced CSS blocks: {name}")
    missing = []
    for ref in url_re.findall(raw):
        p = local_path(ref)
        if p and not p.exists():
            # CSS-relative path, not site-root-relative.
            relative = path.parent / urlsplit(ref).path
            if not relative.exists():
                missing.append(ref)
    check(not missing, f"all local CSS assets exist: {name}", ", ".join(sorted(set(missing))))

# 12. UTF-8 release scan for active files.
for name in PUBLIC_HTML + ACTIVE_JS + ACTIVE_CSS + ["_headers", "_redirects"]:
    try:
        (ROOT / name).read_text(encoding="utf-8")
        ok = True
    except UnicodeDecodeError:
        ok = False
    check(ok, f"UTF-8 readable: {name}")

print(f"PASS: {len(passes)}")
print(f"FAIL: {len(failures)}")
print(f"WARN: {len(warnings)}")
for item in failures:
    print(f"FAIL | {item}")
for item in warnings:
    print(f"WARN | {item}")
if not failures:
    print("RESULT: RELEASE GATE PASSED")
else:
    print("RESULT: RELEASE GATE FAILED")
    sys.exit(1)
