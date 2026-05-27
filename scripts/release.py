#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
TAG_RE = re.compile(r"^v(?P<date>\d{4}\.\d{1,2}\.\d{1,2})(?:\.(?P<patch>\d+))?$")
VERSION_RE = re.compile(r"^v?(?P<version>\d{4}\.\d{1,2}\.\d{1,2}(?:\.\d+)?)$")


class ReleaseError(RuntimeError):
    pass


class MergedPullRequest(NamedTuple):
    number: int
    title: str
    body: str
    merge_commit: str


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
    return ["git", "push", "origin", release_branch_push_ref(version)]


def release_pr_create_command(version: str, body: str) -> list[str]:
    tag = release_tag(version)
    return [
        "gh",
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        release_branch(version),
        "--title",
        f"chore(release): {tag}",
        "--body",
        body,
    ]


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


def latest_release_tag(tags: list[str]) -> str | None:
    release_tags = [(key, tag) for tag in tags if (key := _release_tag_sort_key(tag)) is not None]
    if not release_tags:
        return None
    return max(release_tags)[1]


def _release_tag_sort_key(tag: str) -> tuple[int, int, int, int] | None:
    match = TAG_RE.fullmatch(tag)
    if match is None:
        return None
    year, month, day = (int(part) for part in match.group("date").split("."))
    patch = match.group("patch")
    return year, month, day, 0 if patch is None else int(patch)


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
    print("  Release PR: created automatically with gh pr create")
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


def prepare_release(version: str, *, previous_tag: str | None) -> None:
    run(["uv", "run", "ruff", "check", "."])
    run(["uv", "run", "ruff", "format", "--check", "."])
    run(["uv", "run", "pytest"])
    run(["uv", "run", "cz", "bump", version, "--allow-no-commit", "--changelog", "--yes"])
    if append_release_note_details(version=version, previous_tag=previous_tag):
        run(["git", "add", "CHANGELOG.md"])
        run(["git", "commit", "--amend", "--no-edit"])
    pr_body = release_pr_body(version)
    run(["git", "status", "--short"])
    run(prepare_push_command(version))
    run(["git", "tag", "-d", release_tag(version)])
    run(release_pr_create_command(version, pr_body))
    print()
    print("Release PR branch pushed.")
    print(f"Release PR created for {release_branch(version)}.")
    print()
    print("After the release PR is squash-merged, sync main and publish the tag with:")
    print("  git switch main")
    print("  git pull --ff-only origin main")
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


def append_release_note_details(*, version: str, previous_tag: str | None) -> bool:
    details = format_details_section(collect_release_note_prs(previous_tag))
    if details is None:
        return False

    changelog_path = ROOT / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    updated = insert_changelog_details(changelog, version, details)
    if updated == changelog:
        return False

    changelog_path.write_text(updated, encoding="utf-8")
    return True


def collect_release_note_prs(previous_tag: str | None) -> list[MergedPullRequest]:
    return [
        pr
        for commit in commits_since_tag(previous_tag)
        if (pr := merged_pr_for_commit(commit)) is not None
    ]


def commits_since_tag(previous_tag: str | None) -> list[str]:
    revision = "HEAD" if previous_tag is None else f"{previous_tag}..HEAD"
    result = output(["git", "rev-list", "--reverse", revision])
    return [line.strip() for line in result.splitlines() if line.strip()]


def merged_pr_for_commit(commit: str) -> MergedPullRequest | None:
    raw = output(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "merged",
            "--search",
            commit,
            "--json",
            "number,title,body,mergeCommit",
            "--limit",
            "10",
        ]
    )
    for item in json.loads(raw):
        merge_commit = item.get("mergeCommit") or {}
        if merge_commit.get("oid") == commit:
            return MergedPullRequest(
                number=int(item["number"]),
                title=str(item["title"]),
                body=str(item.get("body") or ""),
                merge_commit=commit,
            )
    return None


def extract_release_notes(body: str) -> str | None:
    lines = body.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.fullmatch(r"\s*##\s+Release notes\s*", line, flags=re.IGNORECASE):
            start = index + 1
            break
    if start is None:
        return None

    end = len(lines)
    for index in range(start, len(lines)):
        if re.match(r"\s*##\s+\S", lines[index]):
            end = index
            break

    note_lines = _strip_html_comments(lines[start:end])
    text = "\n".join(note_lines).strip()
    if not text or _is_empty_release_note(text):
        return None
    return text


def _strip_html_comments(lines: list[str]) -> list[str]:
    result = []
    in_comment = False
    for line in lines:
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        result.append(line.rstrip())
    return result


def _is_empty_release_note(text: str) -> bool:
    normalized = [line.strip().lower() for line in text.splitlines() if line.strip()]
    return all(line in {"none", "- none", "* none", "n/a", "- n/a", "* n/a"} for line in normalized)


def format_details_section(prs: list[MergedPullRequest]) -> str | None:
    lines = ["### Details", ""]
    for pr in prs:
        notes = extract_release_notes(pr.body)
        if notes is None:
            continue
        lines.append(f"- PR {pr.number}: {pr.title}")
        for line in notes.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "* ")):
                lines.append(f"  {stripped}")
            else:
                lines.append(f"  - {stripped}")

    if len(lines) == 2:
        return None
    return "\n".join(lines) + "\n"


def release_pr_body(version: str) -> str:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    section = changelog_section_for_body(changelog, version)
    return f"Release {release_tag(version)}.\n\n## Changelog\n\n{section}"


def changelog_section_for_body(changelog: str, version: str) -> str:
    lines = changelog.splitlines()
    start, end = _version_section_bounds(lines, version)
    section_lines = lines[start + 1 : end]
    while section_lines and not section_lines[0].strip():
        section_lines.pop(0)
    return "\n".join(section_lines).strip() + "\n"


def insert_changelog_details(changelog: str, version: str, details: str) -> str:
    lines = changelog.splitlines()
    start, end = _version_section_bounds(lines, version)
    section = _remove_existing_details(lines[start:end])
    details_lines = details.strip().splitlines()
    updated_section = [*section]
    if updated_section and updated_section[-1] != "":
        updated_section.append("")
    updated_section.extend(details_lines)
    if end < len(lines) and updated_section[-1] != "":
        updated_section.append("")
    updated_lines = [*lines[:start], *updated_section, *lines[end:]]
    return "\n".join(updated_lines).rstrip() + "\n"


def _version_section_bounds(lines: list[str], version: str) -> tuple[int, int]:
    heading_re = re.compile(r"^##\s+\[?v?" + re.escape(version) + r"\]?(?:\s|\(|$)")
    start = None
    for index, line in enumerate(lines):
        if heading_re.match(line):
            start = index
            break
    if start is None:
        raise ReleaseError(f"version {version} was not found in CHANGELOG.md")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[index]):
            end = index
            break
    return start, end


def _remove_existing_details(section: list[str]) -> list[str]:
    start = None
    for index, line in enumerate(section):
        if line.strip() == "### Details":
            start = index
            break
    if start is None:
        return section

    end = len(section)
    for index in range(start + 1, len(section)):
        if re.match(r"^###\s+", section[index]):
            end = index
            break

    remove_start = start - 1 if start > 0 and section[start - 1] == "" else start
    return [*section[:remove_start], *section[end:]]


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
        tags = existing_tags()
        previous_tag = latest_release_tag(tags)
        version = choose_version(release_date, tags, args.patch)
        branch = current_branch()
        if branch != "main":
            raise ReleaseError("release preparation must start from local main")

        confirm_prepare(version, branch)
        prepare_release(version, previous_tag=previous_tag)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
