"""Tests for blast_radius.py — reverse-dependency reachability over graph.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import blast_radius


def _write_graph(path: Path, nodes: list[dict], links: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"directed": True, "nodes": nodes, "links": links}))


def _chain_graph(path: Path) -> None:
    # A calls B, B calls C  =>  dependents(C) = {B@1, A@2}; dependents(A) = {}
    _write_graph(
        path,
        nodes=[
            {"id": "A", "label": "AlphaService", "source_file": "a.ts"},
            {"id": "B", "label": "BetaService", "source_file": "b.ts"},
            {"id": "C", "label": "GammaCore", "source_file": "c.ts"},
        ],
        links=[
            {"source": "A", "target": "B", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "B", "target": "C", "relation": "calls", "confidence": "EXTRACTED"},
        ],
    )


def test_missing_graph_returns_error(tmp_path: Path) -> None:
    res = blast_radius.blast_radius(tmp_path / "nope.json", "X")
    assert res["error"] == "graph_not_found"


def test_target_not_found(tmp_path: Path) -> None:
    g = tmp_path / "g.json"
    _chain_graph(g)
    res = blast_radius.blast_radius(g, "Nonexistent")
    assert res["error"] == "target_not_found"


def test_dependents_walk_reverse(tmp_path: Path) -> None:
    g = tmp_path / "g.json"
    _chain_graph(g)
    res = blast_radius.blast_radius(g, "GammaCore")
    dep_ids = {d["id"]: d["hops"] for d in res["dependents"]}
    assert dep_ids == {"B": 1, "A": 2}
    assert res["dependent_count"] == 2


def test_leaf_has_no_dependents(tmp_path: Path) -> None:
    g = tmp_path / "g.json"
    _chain_graph(g)
    res = blast_radius.blast_radius(g, "AlphaService")
    assert res["dependents"] == []
    assert res["dependent_count"] == 0


def test_max_hops_limits_depth(tmp_path: Path) -> None:
    g = tmp_path / "g.json"
    _chain_graph(g)
    res = blast_radius.blast_radius(g, "GammaCore", max_hops=1)
    assert {d["id"] for d in res["dependents"]} == {"B"}  # A is 2 hops away


def test_non_dependency_relations_ignored(tmp_path: Path) -> None:
    g = tmp_path / "g.json"
    _write_graph(
        g,
        nodes=[
            {"id": "A", "label": "A", "source_file": "a.ts"},
            {"id": "B", "label": "B", "source_file": "b.ts"},
        ],
        # semantically_similar_to is NOT a dependency edge
        links=[{"source": "A", "target": "B", "relation": "semantically_similar_to", "confidence": "INFERRED"}],
    )
    res = blast_radius.blast_radius(g, "B")
    assert res["dependents"] == []


def test_hub_detection(tmp_path: Path) -> None:
    g = tmp_path / "g.json"
    # H has fan-in 3 → it is a hub.
    _write_graph(
        g,
        nodes=[{"id": x, "label": x, "source_file": f"{x}.ts"} for x in ("a", "b", "c", "H")],
        links=[
            {"source": "a", "target": "H", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "b", "target": "H", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "c", "target": "H", "relation": "calls", "confidence": "EXTRACTED"},
        ],
    )
    res = blast_radius.blast_radius(g, "H")
    assert res["is_hub"] is True
    assert res["hub_rank"] == 1
    assert res["dependent_count"] == 3
