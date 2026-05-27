from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


release = load_script("release_script", "scripts/release.py")
changelog = load_script("changelog_section_script", "scripts/changelog_section.py")


def test_normalize_date_accepts_dash_and_dot_formats():
    assert release.normalize_date("2026-05-26") == "2026.5.26"
    assert release.normalize_date("2026.5.26") == "2026.5.26"


def test_normalize_date_rejects_invalid_dates():
    with pytest.raises(release.ReleaseError):
        release.normalize_date("2026-02-31")


def test_choose_version_uses_bare_date_when_no_tag_exists():
    assert release.choose_version("2026.5.26", []) == "2026.5.26"


def test_choose_version_uses_next_patch_for_same_day_release():
    tags = ["v2026.5.26", "v2026.5.26.1", "v2026.5.25"]
    assert release.choose_version("2026.5.26", tags) == "2026.5.26.2"


def test_choose_version_allows_patch_override():
    assert release.choose_version("2026.5.26", ["v2026.5.26"], patch=3) == "2026.5.26.3"


def test_choose_version_rejects_duplicate_patch_override():
    with pytest.raises(release.ReleaseError):
        release.choose_version("2026.5.26", ["v2026.5.26.3"], patch=3)


def test_normalize_version_arg_accepts_optional_v_prefix():
    assert release.normalize_version_arg("2026.5.26") == "2026.5.26"
    assert release.normalize_version_arg("v2026.5.26.1") == "2026.5.26.1"


def test_release_branch_name_uses_v_prefixed_tag():
    assert release.release_branch("2026.5.26") == "release/v2026.5.26"


def test_prepare_push_command_pushes_release_branch_not_main():
    command = release.prepare_push_command("2026.5.26")

    assert command == ["git", "push", "origin", "HEAD:refs/heads/release/v2026.5.26"]
    assert "main" not in command


def test_release_pr_create_command_opens_release_pr():
    command = release.release_pr_create_command("2026.5.26", "Release body")

    assert command == [
        "gh",
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        "release/v2026.5.26",
        "--title",
        "chore(release): v2026.5.26",
        "--body",
        "Release body",
    ]


def test_latest_release_tag_uses_highest_date_version():
    assert release.latest_release_tag(["v2026.5.26", "v2026.5.27", "not-a-release"]) == (
        "v2026.5.27"
    )


def test_latest_release_tag_uses_same_day_patch_counter():
    assert release.latest_release_tag(["v2026.5.27", "v2026.5.27.2", "v2026.5.27.1"]) == (
        "v2026.5.27.2"
    )


def test_extract_changelog_section_matches_v_prefixed_or_plain_headings():
    content = """# Changelog

## v2026.5.26 (2026-05-26)

### Feat

- add release automation

## 2026.5.25 (2026-05-25)

- older
"""
    assert "add release automation" in changelog.extract_section(content, "2026.5.26")
    assert "older" in changelog.extract_section(content, "2026.5.25")


def test_extract_release_notes_reads_section_until_next_heading():
    body = """## Summary
- internal summary

## Release notes

<!-- Maintainers may edit this. -->

- First user-facing note.
- Second user-facing note.

## Checks

- tests
"""

    assert release.extract_release_notes(body) == (
        "- First user-facing note.\n- Second user-facing note."
    )


def test_extract_release_notes_ignores_none_and_missing_sections():
    assert release.extract_release_notes("## Release notes\n\n- None\n") is None
    assert release.extract_release_notes("## Summary\n\n- no notes") is None


def test_format_details_section_groups_notes_by_pr():
    details = release.format_details_section(
        [
            release.MergedPullRequest(
                number=4,
                title="refactor!: flatten MQTT telemetry payloads",
                body=(
                    "## Release notes\n\n- Flat MQTT payloads.\nBREAKING CHANGE: old shape removed."
                ),
                merge_commit="abc123",
            ),
            release.MergedPullRequest(
                number=5,
                title="docs: internal cleanup",
                body="## Release notes\n\n- None",
                merge_commit="def456",
            ),
        ]
    )

    assert details == (
        "### Details\n\n"
        "- PR 4: refactor!: flatten MQTT telemetry payloads\n"
        "  - Flat MQTT payloads.\n"
        "  - BREAKING CHANGE: old shape removed.\n"
    )


def test_insert_changelog_details_updates_only_target_version():
    content = """# Changelog

## v2026.5.27 (2026-05-27)

### BREAKING CHANGE

- Flat payloads.

### Refactor

- flatten MQTT telemetry payloads

## v2026.5.26 (2026-05-26)

### Feat

- add bridge
"""

    updated = release.insert_changelog_details(
        content,
        "2026.5.27",
        "### Details\n\n- PR 4: refactor!: flatten MQTT telemetry payloads\n  - More detail.\n",
    )

    assert (
        "### Details\n\n- PR 4: refactor!: flatten MQTT telemetry payloads\n  - More detail."
        in updated
    )
    assert updated.count("### Details") == 1
    assert "  - More detail.\n\n## v2026.5.26" in updated
    assert "## v2026.5.26 (2026-05-26)\n\n### Feat" in updated


def test_insert_changelog_details_replaces_existing_details():
    content = """# Changelog

## v2026.5.27 (2026-05-27)

### Refactor

- flatten MQTT telemetry payloads

### Details

- old detail
"""

    updated = release.insert_changelog_details(
        content,
        "2026.5.27",
        "### Details\n\n- new detail\n",
    )

    assert "- new detail" in updated
    assert "- old detail" not in updated
    assert updated.count("### Details") == 1


def test_release_pr_body_includes_changelog_without_version_heading(tmp_path, monkeypatch):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """# Changelog

## v2026.5.27 (2026-05-27)

### Fix

- fix runtime

### Details

- PR 6: fix runtime
  - MQTT publishing is stable.

## v2026.5.26 (2026-05-26)

### Feat

- add bridge
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(release, "ROOT", tmp_path)

    assert release.release_pr_body("2026.5.27") == (
        "Release v2026.5.27.\n\n"
        "## Changelog\n\n"
        "### Fix\n\n"
        "- fix runtime\n\n"
        "### Details\n\n"
        "- PR 6: fix runtime\n"
        "  - MQTT publishing is stable.\n"
    )
