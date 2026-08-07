#!/usr/bin/env python3
"""Run the authoritative Build 16.3.1 website regression suite."""
from pathlib import Path
import subprocess, sys, os

ROOT = Path(__file__).resolve().parent
PY_TESTS = [
    "build16_3_1_hardening_tests.py",
    "build16_3_0_newsroom_source_control_tests.py",
    "build16_3_0_full_regression_tests.py",
]
for test in PY_TESTS:
    print(f"\n===== {test} =====", flush=True)
    env = dict(os.environ, TERM=os.environ.get("TERM", "xterm"))
    result = subprocess.run([sys.executable, str(ROOT / test)], cwd=ROOT, env=env)
    if result.returncode:
        raise SystemExit(result.returncode)
subprocess.run(["node", str(ROOT / "build16_3_1_function_contract_tests.mjs")], cwd=ROOT, check=True)
for path in sorted((ROOT / "functions").rglob("*.js")):
    subprocess.run(["node", "--check", str(path)], check=True, stdout=subprocess.DEVNULL)
subprocess.run(["node", "--check", str(ROOT / "admin-build15-9.js")], check=True, stdout=subprocess.DEVNULL)
print(f"\nPASS: {len(PY_TESTS)} website suites, function contracts, and JavaScript syntax")
