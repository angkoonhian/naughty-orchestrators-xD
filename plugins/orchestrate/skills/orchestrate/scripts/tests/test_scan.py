"""Tests for scan.py — happy-path verification of detection logic."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make scripts importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.scan import scan_project


def _write_pkg(path: Path, name: str, deps: dict | None = None, scripts: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pkg = {"name": name, "dependencies": deps or {}}
    if scripts:
        pkg["scripts"] = scripts
    path.write_text(json.dumps(pkg))


def test_detects_single_app_with_one_package_json(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "myapp", {"react": "^18.0.0"})

    profile = scan_project(tmp_path)

    assert profile["shape"] == "single_app"
    assert len(profile["projects"]) == 1
    assert profile["projects"][0]["framework"] == "react"


def test_detects_monorepo_with_multiple_package_json(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "app1" / "package.json", "app1", {"react": "^18.0.0"})
    _write_pkg(tmp_path / "app2" / "package.json", "app2", {"express": "^4.0.0"})

    profile = scan_project(tmp_path)

    assert profile["shape"] == "monorepo"
    assert len(profile["projects"]) == 2
    names = {p["name"] for p in profile["projects"]}
    assert names == {"app1", "app2"}


def test_detects_workspace_marker(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "root")
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n")
    _write_pkg(tmp_path / "packages" / "a" / "package.json", "a", {"react": "^18.0.0"})

    profile = scan_project(tmp_path)

    assert profile["shape"] == "monorepo"


def test_infers_real_time_when_socketio_present(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0", "socket.io": "^4.0.0"})

    profile = scan_project(tmp_path)

    assert profile["infrastructure"].get("real_time") == "socket.io"


def test_infers_queues_when_bull_present(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0", "bull": "^4.0.0"})

    profile = scan_project(tmp_path)

    assert "bull" in profile["infrastructure"].get("queues", [])


def test_infers_observability_sentry(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0", "@sentry/node": "^7.0.0"})

    profile = scan_project(tmp_path)

    assert "sentry" in profile["infrastructure"].get("observability", [])


def test_infers_complexity_high_when_threshold_hit(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0"})
    src = tmp_path / "src"
    src.mkdir()
    for i in range(35):
        (src / f"f{i}.ts").write_text("export const x = 1;\n")

    profile = scan_project(tmp_path)

    proj = profile["projects"][0]
    assert proj["complexity"] == "high"
    assert proj["file_count"] >= 30


def test_detects_subdomains_from_src_top_level(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0"})
    for sub in ["auth", "users", "devices", "billing", "infra"]:
        (tmp_path / "src" / sub).mkdir(parents=True)
        (tmp_path / "src" / sub / "index.ts").write_text("export {};\n")

    profile = scan_project(tmp_path)

    proj = profile["projects"][0]
    assert set(proj["subdomains"]) == {"auth", "users", "devices", "billing", "infra"}


def test_detects_multi_tenant_when_tenant_id_repeated(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0"})
    src = tmp_path / "src"
    src.mkdir()
    for i in range(3):
        (src / f"entity{i}.ts").write_text(f"export class Entity{i} {{ company_id!: number; }}\n")

    profile = scan_project(tmp_path)

    assert profile["domain_markers"]["multi_tenant"] is True


def test_extracts_qa_scripts(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0"}, scripts={"lint": "eslint .", "test": "jest", "build": "tsc"})

    profile = scan_project(tmp_path)

    proj = profile["projects"][0]
    assert proj["qa_scripts"]["lint"] == "eslint ."
    assert proj["qa_scripts"]["test"] == "jest"
    assert proj["qa_scripts"]["typecheck"] == "tsc"


def test_detects_existing_orchestration(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9.0.0"})
    (tmp_path / "CLAUDE.md").write_text("# Existing\n")
    (tmp_path / "docs" / "agents").mkdir(parents=True)

    profile = scan_project(tmp_path)

    assert profile["existing_orchestration"]["root_claude_md"] is True
    assert profile["existing_orchestration"]["docs_agents"] is True


def test_unknown_shape_for_empty_dir(tmp_path: Path) -> None:
    profile = scan_project(tmp_path)
    assert profile["shape"] == "unknown"
    assert profile["projects"] == []
