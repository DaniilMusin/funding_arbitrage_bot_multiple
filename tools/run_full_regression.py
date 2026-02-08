#!/usr/bin/env python3
"""
Run full repository regression tests without coverage gate.

Why:
- The repository has global pytest addopts with --cov and fail-under.
- For local regression/debugging we often need raw pass/fail without coverage threshold.
"""

import argparse
import os
import subprocess
import sys
from typing import List


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run full pytest regression without coverage gate.")
    parser.add_argument(
        "--paths",
        nargs="*",
        default=["test"],
        help="Test paths to run (default: test).",
    )
    parser.add_argument(
        "--with-cov",
        action="store_true",
        help="Keep coverage enabled (default: disabled).",
    )
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Extra args forwarded to pytest.",
    )
    return parser


def run_pytest(paths: List[str], with_cov: bool, extra_args: List[str]) -> int:
    env = dict(os.environ)
    env.setdefault("HB_ALLOW_PYTHON_FALLBACKS", "1")

    cmd: List[str] = [sys.executable, "-m", "pytest", "--override-ini", "addopts="]
    if not with_cov:
        cmd.append("--no-cov")
    cmd.extend(paths)
    cmd.extend(extra_args)

    print("Executing:", " ".join(cmd), flush=True)
    process = subprocess.run(cmd, env=env)
    return int(process.returncode)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run_pytest(paths=args.paths, with_cov=args.with_cov, extra_args=args.pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
