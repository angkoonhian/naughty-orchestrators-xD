"""Tests for update.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.update import update


def _write_pkg(path: Path, name: str, deps: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, "dependencies": deps or {}}))


def test_update_returns_message_when_no_config(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "myapp", {"react": "^18.0.0"})

    result = update(tmp_path)

    assert result["stored_config_present"] is False
    assert "No prior" in result["message"]


def test_update_detects_added_pack_after_new_dep(tmp_path: Path) -> None:
    # Set up initial state with NO socket.io
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0"})

    # Pretend we ran orchestrate previously — write a config with no socket-realtime
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (config_dir / "orchestration.config.yaml").write_text(yaml.safe_dump({
        "platform_pack": {"critics": []},
        "adaptive_tier2": {"enabled_leads": []},
    }))

    # Now add socket.io and run update
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0", "socket.io": "^4.0.0"})

    result = update(tmp_path)

    assert "socket-realtime" in result["added_platform_packs"]


def test_update_detects_no_change_when_config_matches(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0"})

    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (config_dir / "orchestration.config.yaml").write_text(yaml.safe_dump({
        "platform_pack": {"critics": []},
        "adaptive_tier2": {"enabled_leads": []},
    }))

    result = update(tmp_path)

    assert result["added_platform_packs"] == []
    assert result["removed_platform_packs"] == []
