#!/usr/bin/env python3
"""Run all website checks, reporting every failure rather than hiding later tests."""
from pathlib import Path
import subprocess, sys, os

ROOT = Path(__file__).resolve().parent
failures = []

def run(label, command):
    print(f"\n===== {label} =====", flush=True)
    result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, TERM=os.environ.get("TERM", "xterm")))
    if result.returncode:
        failures.append(label)

PY_TESTS = [
    "build16_3_2_source_mode_save_tests.py",
    "build16_3_1_hardening_tests.py",
    "build16_3_0_newsroom_source_control_tests.py",
    "build16_3_0_full_regression_tests.py",
]
for test in PY_TESTS:
    run(test, [sys.executable, str(ROOT / test)])
for test in ("build16_3_1_function_contract_tests.mjs", "build16_3_3_public_links_tests.mjs"):
    run(test, ["node", str(ROOT / test)])
for path in sorted((ROOT / "functions").rglob("*.js")):
    run(f"syntax {path.relative_to(ROOT)}", ["node", "--check", str(path)])
for name in ("admin-build15-9.js", "site-build16-2-1.js", "article-build16-0-1.js",
             "analytics-build12.js", "public-article-links.js", "preview_public_links.mjs"):
    run(f"syntax {name}", ["node", "--check", str(ROOT / name)])
if failures:
    print("\nFAILED CHECK GROUPS: " + ", ".join(failures))
    raise SystemExit(1)
print("\nPASS: all website suites, function contracts and active JavaScript syntax")
