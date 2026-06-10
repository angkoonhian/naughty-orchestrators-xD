"""Tests for graph_bake.py — snapshot distillation from graphify graph.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import graph_bake


def _write_graph(path: Path, nodes: list[dict], links: list[dict], directed: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"directed": directed, "nodes": nodes, "links": links}))


def test_load_graph_returns_none_for_missing(tmp_path: Path) -> None:
    assert graph_bake.load_graph(tmp_path / "nope.json") is None


def test_bake_project_groups_communities(tmp_path: Path) -> None:
    g = tmp_path / "graphify-out" / "graph.json"
    _write_graph(
        g,
        nodes=[
            {"id": "a", "label": "AuthGuard", "community": 0, "source_file": "auth/guard.ts"},
            {"id": "b", "label": "AuthService", "community": 0, "source_file": "auth/svc.ts"},
            {"id": "c", "label": "DeviceReading", "community": 1, "source_file": "device/r.ts"},
        ],
        links=[{"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"}],
    )
    block = graph_bake.bake_project(g)
    assert block["node_count"] == 3
    assert block["community_count"] == 2
    labels = {c["label"] for c in block["communities"]}
    # "Auth" is the dominant token in community 0's member labels.
    assert "Auth" in labels


def test_bake_project_no_community_attr_yields_empty(tmp_path: Path) -> None:
    g = tmp_path / "graphify-out" / "graph.json"
    _write_graph(
        g,
        nodes=[{"id": "a", "label": "X", "source_file": "x.ts"}],  # no community key
        links=[],
    )
    block = graph_bake.bake_project(g)
    assert block["communities"] == []
    assert block["community_count"] == 0


def test_hubs_ranked_by_in_degree(tmp_path: Path) -> None:
    g = tmp_path / "graph.json"
    # b has fan-in 3 (a,c,d → b); e has fan-in 2. b should rank first.
    _write_graph(
        g,
        nodes=[{"id": x, "label": x.upper(), "source_file": f"{x}.ts"} for x in "abcde"],
        links=[
            {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "c", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "d", "target": "b", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "a", "target": "e", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "c", "target": "e", "relation": "calls", "confidence": "EXTRACTED"},
        ],
    )
    block = graph_bake.bake_project(g)
    hubs = block["hubs"]
    assert hubs[0]["id"] == "b"
    assert hubs[0]["in_degree"] == 3
    assert hubs[0]["provenance"] == "EXTRACTED"
    assert {h["id"] for h in hubs} == {"b", "e"}  # only fan-in ≥ 2


def test_hub_provenance_inferred_when_incoming_mostly_inferred(tmp_path: Path) -> None:
    g = tmp_path / "graph.json"
    _write_graph(
        g,
        nodes=[{"id": x, "label": x, "source_file": f"{x}.ts"} for x in ("a", "b", "h")],
        links=[
            {"source": "a", "target": "h", "relation": "references", "confidence": "INFERRED"},
            {"source": "b", "target": "h", "relation": "references", "confidence": "INFERRED"},
        ],
    )
    block = graph_bake.bake_project(g)
    assert block["hubs"][0]["provenance"] == "INFERRED"


def test_bake_seam_keeps_cross_project_drops_same_project(tmp_path: Path) -> None:
    g = tmp_path / "seam.json"
    _write_graph(
        g,
        nodes=[
            {"id": "route", "label": "planner route", "source_file": "api-oxen/src/planner.controller.ts"},
            {"id": "consumer", "label": "planner.api", "source_file": "fieldops-oxen/src/planner.api.js"},
            {"id": "sibling", "label": "other", "source_file": "api-oxen/src/other.controller.ts"},
        ],
        links=[
            {"source": "route", "target": "consumer", "relation": "shares_data_with", "confidence": "INFERRED", "confidence_score": 0.85},
            {"source": "route", "target": "sibling", "relation": "shares_data_with", "confidence": "INFERRED"},
        ],
    )
    seam_map, co_fire = graph_bake.bake_seam(g, ["api-oxen", "fieldops-oxen"])
    assert len(seam_map) == 1  # same-project edge dropped
    assert seam_map[0]["from_project"] == "api-oxen"
    assert seam_map[0]["to_project"] == "fieldops-oxen"
    # co_fire is symmetric
    assert co_fire["api-oxen"] == ["fieldops-oxen"]
    assert co_fire["fieldops-oxen"] == ["api-oxen"]


def test_bake_full_snapshot_shape(tmp_path: Path) -> None:
    g1 = tmp_path / "p1" / "graphify-out" / "graph.json"
    _write_graph(
        g1,
        nodes=[
            {"id": "a", "label": "A", "community": 0, "source_file": "p1/a.ts"},
            {"id": "b", "label": "B", "community": 0, "source_file": "p1/b.ts"},
        ],
        links=[{"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"}],
    )
    snapshot = graph_bake.bake(
        {"p1": str(g1)},
        None,
        ["p1"],
        built_at="2026-06-08T00:00:00Z",
        enabled=True,
    )
    assert snapshot["schema_version"] == graph_bake.SCHEMA_VERSION
    assert snapshot["built_at"] == "2026-06-08T00:00:00Z"
    assert snapshot["graph_integration"] == "enabled"
    assert "p1" in snapshot["projects"]
    assert snapshot["seam_map"] == []
    assert snapshot["source"]["per_project_graphs"]["p1"] == str(g1)


def test_discover_per_project_graphs(tmp_path: Path) -> None:
    (tmp_path / "appA" / "graphify-out").mkdir(parents=True)
    (tmp_path / "appA" / "graphify-out" / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / "appB" / "graphify-out").mkdir(parents=True)
    (tmp_path / "appB" / "graphify-out" / "graph.json").write_text('{"nodes":[],"links":[]}')
    found = graph_bake.discover_per_project_graphs(tmp_path)
    assert set(found.keys()) == {"appA", "appB"}


def test_write_snapshot_roundtrip(tmp_path: Path) -> None:
    snap = {"schema_version": 1, "projects": {}}
    out = graph_bake.write_snapshot(snap, tmp_path / ".claude" / "orchestration.graph.json")
    assert Path(out).exists()
    assert json.loads(Path(out).read_text())["schema_version"] == 1
