#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG_RE = re.compile(r"^v(?P<date>\d{4}\.\d{1,2}\.\d{1,2})(?:\.(?P<patch>\d+))?$")


class ReleaseError(RuntimeError):
    pass


def normalize_date(value: str | None) -> str:
    if value is None:
        today = dt.date.today()
        return f"{today.year}.{today.month}.{today.day}"

    match = re.fullmatch(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})", value)
    if not match:
        raise ReleaseError("date must use YYYY-M-D, YYYY-MM-DD, YYYY.M.D, or YYYY.MM.DD")

    year, month, day = (int(part) for part in match.groups())
    try:
        parsed = dt.date(year, month, day)
    except ValueError as exc:
        raise ReleaseError(f"invalid release date: {value}") from exc
    return f"{parsed.year}.{parsed.month}.{parsed.day}"


def patch_for_tag(tag: str, release_date: str) -> int | None:
    match = TAG_RE.fullmatch(tag)
    if match is None or match.group("date") != release_date:
        return None
    patch = match.group("patch")
    return 0 if patch is None else int(patch)


def choose_version(release_date: str, tags: list[str], patch: int | None = None) -> str:
    existing_patches = {
        value for tag in tags if (value := patch_for_tag(tag, release_date)) is not None
    }

    if patch is None:
        next_patch = 0 if not existing_patches else max(existing_patches) + 1
    else:
        if patch < 0:
            raise ReleaseError("patch must be zero or greater")
        next_patch = patch

    if next_patch in existing_patches:
        version = release_date if next_patch == 0 else f"{release_date}.{next_patch}"
        raise ReleaseError(f"release tag v{version} already exists")

    return release_date if next_patch == 0 else f"{release_date}.{next_patch}"


def run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def output(args: list[str]) -> str:
    return run(args, capture=True).stdout.strip()


def git_clean() -> bool:
    return output(["git", "status", "--porcelain"]) == ""


def fetch_tags() -> None:
    remotes = output(["git", "remote"]).splitlines()
    if "origin" in remotes:
        run(["git", "fetch", "--tags", "origin"])


def existing_tags() -> list[str]:
    result = output(["git", "tag", "--list", "v*"])
    return [line.strip() for line in result.splitlines() if line.strip()]


def current_branch() -> str:
    branch = output(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch == "HEAD":
        raise ReleaseError("cannot release from a detached HEAD")
    return branch


def confirm(version: str, branch: str) -> None:
    print("Release summary")
    print(f"  Version: {version}")
    print(f"  Git tag: v{version}")
    print(f"  Docker tags: {version}, latest")
    print("  Version/changelog: Commitizen bump with uv provider")
    print("  Checks: uv run ruff check .; uv run ruff format --check .; uv run pytest")
    print(f"  Commit: chore(release): v{version}")
    print(f"  Push: origin {branch} and tag v{version}")
    answer = input("Continue with this release? Type 'release' to proceed: ")
    if answer != "release":
        raise ReleaseError("release cancelled")


def release(version: str, branch: str) -> None:
    run(["uv", "run", "ruff", "check", "."])
    run(["uv", "run", "ruff", "format", "--check", "."])
    run(["uv", "run", "pytest"])
    run(["uv", "run", "cz", "bump", version, "--allow-no-commit", "--changelog", "--yes"])
    run(["git", "status", "--short"])
    run(["git", "push", "origin", branch])
    run(["git", "push", "origin", f"v{version}"])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a date-versioned marstek-ble2mqtt release."
    )
    parser.add_argument(
        "--date", help="Release date as YYYY-M-D, YYYY-MM-DD, YYYY.M.D, or YYYY.MM.DD."
    )
    parser.add_argument(
        "--patch",
        type=int,
        help="Same-day patch counter. Use 0 for the bare date version, 1 for .1, etc.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if not git_clean():
            raise ReleaseError("working tree must be clean before releasing")

        fetch_tags()
        release_date = normalize_date(args.date)
        version = choose_version(release_date, existing_tags(), args.patch)
        branch = current_branch()

        confirm(version, branch)
        release(version, branch)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
