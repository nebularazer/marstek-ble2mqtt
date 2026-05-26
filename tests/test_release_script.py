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

    assert command == ["git", "push", "-u", "origin", "HEAD:refs/heads/release/v2026.5.26"]
    assert "main" not in command


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
