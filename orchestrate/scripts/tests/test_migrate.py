"""Tests for migrate.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.migrate import migrate


def _basic_profile(tmp_path: Path) -> dict:
    return {
        "shape": "single_app",
        "projects": [{"name": "api", "path": str(tmp_path), "framework": "nestjs", "qa_scripts": {}, "subdomains": ["auth", "users", "devices", "billing", "infra"], "complexity": "high"}],
        "infrastructure": {},
        "domain_markers": {},
    }


def test_migrate_creates_backup(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# Existing root\n")
    (tmp_path / "docs" / "agents" / "cross-cutting").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "cross-cutting" / "devils-advocate.md").write_text("old DA\n")

    profile = _basic_profile(tmp_path)
    manifest = migrate(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": [], "replace_devils_advocate": True})

    backup_dirs = list((tmp_path / ".claude").glob("orchestration.backup-*"))
    assert len(backup_dirs) == 1
    bd = backup_dirs[0]
    assert (bd / "CLAUDE.md").read_text() == "# Existing root\n"
    assert (bd / "docs" / "agents" / "cross-cutting" / "devils-advocate.md").exists()


def test_migrate_preserves_existing_claude_md(tmp_path: Path) -> None:
    original = "# My Root CLAUDE.md\n\nCustom content.\n"
    (tmp_path / "CLAUDE.md").write_text(original)

    profile = _basic_profile(tmp_path)
    migrate(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": []})

    assert (tmp_path / "CLAUDE.md").read_text() == original


def test_migrate_retires_devils_advocate_when_replace_true(tmp_path: Path) -> None:
    (tmp_path / "docs" / "agents" / "cross-cutting").mkdir(parents=True)
    da = tmp_path / "docs" / "agents" / "cross-cutting" / "devils-advocate.md"
    da.write_text("legacy")

    profile = _basic_profile(tmp_path)
    manifest = migrate(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": [], "replace_devils_advocate": True})

    assert not da.exists()
    assert manifest["legacy_devils_advocate_retired"] is True


def test_migrate_preserves_devils_advocate_when_replace_false(tmp_path: Path) -> None:
    (tmp_path / "docs" / "agents" / "cross-cutting").mkdir(parents=True)
    da = tmp_path / "docs" / "agents" / "cross-cutting" / "devils-advocate.md"
    da.write_text("legacy")

    profile = _basic_profile(tmp_path)
    migrate(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": [], "replace_devils_advocate": False})

    assert da.exists()


def test_migrate_adds_new_cross_cutting_agents(tmp_path: Path) -> None:
    profile = _basic_profile(tmp_path)
    migrate(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": []})

    cc = tmp_path / "docs" / "agents" / "cross-cutting"
    assert (cc / "da-lead.md").exists()
    assert (cc / "pre-impl-validator.md").exists()
    assert (cc / "post-impl-validator.md").exists()
    assert (cc / "qa-delegator.md").exists()


def test_migrate_preserves_existing_architect(tmp_path: Path) -> None:
    (tmp_path / "docs" / "agents" / "cross-cutting").mkdir(parents=True)
    arch = tmp_path / "docs" / "agents" / "cross-cutting" / "architect.md"
    original = "# Custom architect prompt"
    arch.write_text(original)

    profile = _basic_profile(tmp_path)
    migrate(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": []})

    assert arch.read_text() == original
