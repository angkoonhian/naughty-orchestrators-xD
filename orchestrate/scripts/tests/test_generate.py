"""Tests for generate.py."""
from __future__ import annotations

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.generate import generate_orchestration


def _basic_profile(name: str = "myapp") -> dict:
    return {
        "shape": "single_app",
        "projects": [{"name": name, "path": "/tmp/fake", "framework": "react", "qa_scripts": {}}],
        "infrastructure": {},
        "domain_markers": {},
    }


def test_generate_creates_cross_cutting_agents(tmp_path: Path) -> None:
    profile = _basic_profile()
    profile["projects"][0]["path"] = str(tmp_path)
    manifest = generate_orchestration(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": []})

    cc = tmp_path / "docs" / "agents" / "cross-cutting"
    assert (cc / "architect.md").exists()
    assert (cc / "da-lead.md").exists()
    assert (cc / "pre-impl-validator.md").exists()
    assert (cc / "post-impl-validator.md").exists()
    assert (cc / "qa-delegator.md").exists()


def test_generate_creates_universal_critics(tmp_path: Path) -> None:
    profile = _basic_profile()
    profile["projects"][0]["path"] = str(tmp_path)
    generate_orchestration(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": []})

    core = tmp_path / "docs" / "agents" / "da" / "core"
    assert len(list(core.glob("*.md"))) == 7


def test_generate_creates_validators(tmp_path: Path) -> None:
    profile = _basic_profile()
    profile["projects"][0]["path"] = str(tmp_path)
    generate_orchestration(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": []})

    pre = tmp_path / "docs" / "agents" / "validators" / "pre-impl"
    post = tmp_path / "docs" / "agents" / "validators" / "post-impl"
    assert len(list(pre.glob("*.md"))) == 6
    assert len(list(post.glob("*.md"))) == 5


def test_generate_creates_task_agents(tmp_path: Path) -> None:
    profile = _basic_profile()
    profile["projects"][0]["path"] = str(tmp_path)
    generate_orchestration(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": []})

    tasks = tmp_path / "docs" / "agents" / "task-agents"
    assert len(list(tasks.glob("*.md"))) == 4


def test_generate_creates_root_claude_md_when_absent(tmp_path: Path) -> None:
    profile = _basic_profile()
    profile["projects"][0]["path"] = str(tmp_path)
    generate_orchestration(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": []})

    root_claude = tmp_path / "CLAUDE.md"
    assert root_claude.exists()
    content = root_claude.read_text()
    assert "Orchestrator Agent System" in content


def test_generate_writes_orchestration_config(tmp_path: Path) -> None:
    profile = _basic_profile()
    profile["projects"][0]["path"] = str(tmp_path)
    generate_orchestration(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": ["socket-realtime"]})

    config = tmp_path / ".claude" / "orchestration.config.yaml"
    assert config.exists()
    import yaml
    data = yaml.safe_load(config.read_text())
    assert "socket-realtime" in data["platform_pack"]["critics"]


def test_generate_copies_confirmed_platform_pack(tmp_path: Path) -> None:
    profile = _basic_profile("api")
    profile["projects"][0]["path"] = str(tmp_path)
    profile["infrastructure"] = {"real_time": "socket.io"}
    generate_orchestration(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": ["socket-realtime"]})

    pack_dir = tmp_path / "docs" / "agents" / "da" / "api-pack"
    assert pack_dir.exists()
    assert (pack_dir / "socket-fanout-critic.md").exists()
    assert (pack_dir / "reconnect-correctness-critic.md").exists()


def test_generate_preserves_existing_claude_md(tmp_path: Path) -> None:
    """If CLAUDE.md already exists, generate should NOT overwrite it."""
    profile = _basic_profile()
    profile["projects"][0]["path"] = str(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# Existing content")

    generate_orchestration(tmp_path, profile, {"qa_wiring": {}}, {"install_packs": []})

    assert (tmp_path / "CLAUDE.md").read_text() == "# Existing content"
