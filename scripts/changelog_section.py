#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def extract_section(changelog: str, version: str) -> str:
    heading_re = re.compile(r"^##\s+\[?v?" + re.escape(version) + r"\]?(?:\s|\(|$)")
    any_heading_re = re.compile(r"^##\s+")
    lines = changelog.splitlines()
    start = None

    for index, line in enumerate(lines):
        if heading_re.match(line):
            start = index
            break

    if start is None:
        raise ValueError(f"version {version} was not found in CHANGELOG.md")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if any_heading_re.match(lines[index]):
            end = index
            break

    return "\n".join(lines[start:end]).strip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print one version section from CHANGELOG.md.")
    parser.add_argument("version", help="Version without the leading v, for example 2026.5.26.")
    parser.add_argument(
        "--changelog",
        default=str(ROOT / "CHANGELOG.md"),
        help="Path to the changelog file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        changelog = Path(args.changelog).read_text(encoding="utf-8")
        print(extract_section(changelog, args.version), end="")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
