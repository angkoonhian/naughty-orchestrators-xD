"""Tests for the graph-aware paths in scan / infer / generate (SP2)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.scan import scan_project
from scripts.infer import infer_recommendations
from scripts import generate


def _write_pkg(path: Path, name: str, deps: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, "dependencies": deps or {}}))


def _write_snapshot(root: Path, *, enabled: bool, project: str) -> None:
    snap = {
        "schema_version": 1,
        "built_at": "2026-06-08T00:00:00Z",
        "graph_integration": "enabled" if enabled else "disabled",
        "source": {"per_project_graphs": {}, "seam_graph": None},
        "projects": {
            project: {
                "node_count": 120,
                "edge_count": 300,
                "community_count": 6,
                "complexity": "high",
                "metrics": {"hub_count": 2, "modularity": None},
                "communities": [
                    {"id": "c0", "label": "Auth", "size": 10, "members": [], "provenance": "graphify"},
                    {"id": "c1", "label": "Device", "size": 12, "members": [], "provenance": "graphify"},
                ],
                "hubs": [
                    {"id": "g", "label": "AuthGuard", "source_file": "auth/guard.ts", "in_degree": 9, "degree": 11, "provenance": "EXTRACTED"},
                ],
            }
        },
        "seam_map": [
            {"from_project": project, "from": "route", "to_project": "fe", "to": "api",
             "relation": "shares_data_with", "confidence": "INFERRED", "confidence_score": 0.85, "provenance": "INFERRED"},
        ],
        "co_fire": {project: ["fe"], "fe": [project]},
    }
    out = root / ".claude" / "orchestration.graph.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap))


def test_scan_ignores_snapshot_when_disabled(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9"})
    _write_snapshot(tmp_path, enabled=False, project="api")
    profile = scan_project(tmp_path)
    assert profile["graph"] is None  # disabled → no enrichment


def test_scan_enriches_when_snapshot_enabled(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9"})
    _write_snapshot(tmp_path, enabled=True, project="api")
    profile = scan_project(tmp_path)
    assert profile["graph"]["present"] is True
    proj = profile["projects"][0]
    assert proj["complexity"] == "high"  # graph-derived
    assert "AuthGuard" in proj["graph_metrics"]["hubs"]
    assert profile["graph"]["co_fire"]["api"] == ["fe"]


def test_infer_emits_graph_recommendations(tmp_path: Path) -> None:
    _write_pkg(tmp_path / "package.json", "api", {"@nestjs/core": "^9"})
    _write_snapshot(tmp_path, enabled=True, project="api")
    profile = scan_project(tmp_path)
    recs = infer_recommendations(profile)
    assert recs["tier2_domain_boundaries"]["api"] == ["Auth", "Device"]
    assert recs["seam_routing"]["api"] == ["fe"]
    assert any("hub" in b.get("condition", "").lower() for b in recs["impact_bumps"])


def test_infer_no_graph_keys_neutral_without_snapshot() -> None:
    profile = {"shape": "single_app", "projects": [{"name": "x", "qa_scripts": {}}],
               "infrastructure": {}, "domain_markers": {}, "graph": None}
    recs = infer_recommendations(profile)
    assert recs["tier2_domain_boundaries"] == {}
    assert recs["seam_routing"] == {}
    assert not any("hub" in b.get("condition", "").lower() for b in recs["impact_bumps"])


def test_wire_graph_integration_injects_and_is_idempotent(tmp_path: Path) -> None:
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("# Root\n\nExisting orchestration content.\n")

    r1 = generate.wire_graph_integration(tmp_path, enabled=True, snapshot=None)
    assert r1["claude_md"] in ("appended", "created")
    after1 = claude.read_text()
    assert generate.GRAPH_BLOCK_START in after1
    assert "Existing orchestration content." in after1  # original preserved

    # Second call replaces the block, not appends a duplicate.
    generate.wire_graph_integration(tmp_path, enabled=True, snapshot=None)
    after2 = claude.read_text()
    assert after2.count(generate.GRAPH_BLOCK_START) == 1
    assert after2.count(generate.GRAPH_BLOCK_END) == 1


def test_wire_graph_integration_disable_removes_block(tmp_path: Path) -> None:
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("# Root\n\nKeep me.\n")
    generate.wire_graph_integration(tmp_path, enabled=True, snapshot=None)
    assert generate.GRAPH_BLOCK_START in claude.read_text()

    generate.wire_graph_integration(tmp_path, enabled=False)
    final = claude.read_text()
    assert generate.GRAPH_BLOCK_START not in final
    assert "Keep me." in final


def test_wire_writes_config_graph_integration(tmp_path: Path) -> None:
    import yaml
    (tmp_path / "CLAUDE.md").write_text("# Root\n")
    generate.wire_graph_integration(tmp_path, enabled=True, snapshot=None)
    cfg = yaml.safe_load((tmp_path / ".claude" / "orchestration.config.yaml").read_text())
    assert cfg["graph_integration"]["enabled"] is True
    assert cfg["graph_integration"]["trust"]["cofire_blocking_when"] == "EXTRACTED"
