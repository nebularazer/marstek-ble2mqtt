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
VERSION_RE = re.compile(r"^v?(?P<version>\d{4}\.\d{1,2}\.\d{1,2}(?:\.\d+)?)$")


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


def normalize_version_arg(value: str) -> str:
    match = VERSION_RE.fullmatch(value)
    if match is None:
        raise ReleaseError("version must look like YYYY.M.D or vYYYY.M.D, with optional .N")
    return match.group("version")


def release_tag(version: str) -> str:
    return f"v{version}"


def release_branch(version: str) -> str:
    return f"release/{release_tag(version)}"


def release_branch_push_ref(version: str) -> str:
    return f"HEAD:refs/heads/{release_branch(version)}"


def prepare_push_command(version: str) -> list[str]:
    return ["git", "push", "-u", "origin", release_branch_push_ref(version)]


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


def fetch_main_and_tags() -> None:
    run(["git", "fetch", "origin", "main", "--tags"])


def existing_tags() -> list[str]:
    result = output(["git", "tag", "--list", "v*"])
    return [line.strip() for line in result.splitlines() if line.strip()]


def current_branch() -> str:
    branch = output(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch == "HEAD":
        raise ReleaseError("cannot release from a detached HEAD")
    return branch


def confirm_prepare(version: str, branch: str) -> None:
    print("Release summary")
    print(f"  Version: {version}")
    print(f"  Git tag: {release_tag(version)}")
    print(f"  Docker tags: {version}, latest")
    print("  Version/changelog: Commitizen bump with uv provider")
    print("  Checks: uv run ruff check .; uv run ruff format --check .; uv run pytest")
    print(f"  Current branch: {branch}")
    print(f"  Commit: chore(release): {release_tag(version)}")
    print(f"  Push release branch: {release_branch(version)}")
    print("  Tag push: deferred until after the release PR is merged")
    answer = input("Continue with this release? Type 'release' to proceed: ")
    if answer != "release":
        raise ReleaseError("release cancelled")


def confirm_finalize(version: str) -> None:
    print("Release finalization summary")
    print(f"  Version: {version}")
    print(f"  Git tag: {release_tag(version)}")
    print("  Tag target: origin/main")
    print("  Push tag to origin: yes")
    answer = input("Finalize this release? Type 'release' to proceed: ")
    if answer != "release":
        raise ReleaseError("release finalization cancelled")


def prepare_release(version: str) -> None:
    run(["uv", "run", "ruff", "check", "."])
    run(["uv", "run", "ruff", "format", "--check", "."])
    run(["uv", "run", "pytest"])
    run(["uv", "run", "cz", "bump", version, "--allow-no-commit", "--changelog", "--yes"])
    run(["git", "status", "--short"])
    run(prepare_push_command(version))
    run(["git", "tag", "-d", release_tag(version)])
    print()
    print("Release PR branch pushed.")
    print("Open the release PR with:")
    print(
        "  gh pr create "
        f"--base main --head {release_branch(version)} "
        f'--title "chore(release): {release_tag(version)}" '
        f'--body "Release {release_tag(version)}."'
    )
    print()
    print("After the PR is squash-merged, publish the tag with:")
    print(f"  scripts/release finalize {release_tag(version)}")


def remote_tag_exists(tag: str) -> bool:
    return output(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"]) != ""


def finalize_release(version: str) -> None:
    tag = release_tag(version)
    fetch_main_and_tags()
    if remote_tag_exists(tag):
        raise ReleaseError(f"remote tag {tag} already exists")
    run(["git", "tag", "-f", "-a", tag, "origin/main", "-m", tag])
    run(["git", "push", "origin", tag])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a date-versioned marstek-ble2mqtt release."
    )
    subparsers = parser.add_subparsers(dest="command")
    finalize_parser = subparsers.add_parser(
        "finalize", help="Publish a release tag after the release PR is merged."
    )
    finalize_parser.add_argument(
        "version", help="Version to tag, with or without leading v, for example v2026.5.26."
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

        if args.command == "finalize":
            version = normalize_version_arg(args.version)
            confirm_finalize(version)
            finalize_release(version)
            return 0

        fetch_tags()
        release_date = normalize_date(args.date)
        version = choose_version(release_date, existing_tags(), args.patch)
        branch = current_branch()
        if branch != "main":
            raise ReleaseError("release preparation must start from local main")

        confirm_prepare(version, branch)
        prepare_release(version)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
