"""blast_radius — "what depends on X?" over a graphify graph.json.

The optional live escalation for runtime impact assessment (SP3). Given a project
graph and a target (file / symbol / label substring), returns the set of nodes that
*depend on* the target (its callers / importers, transitively up to N hops) plus
whether the target is a hub. The orchestrator uses a large dependent set or a hub
hit to raise the impact tier.

stdlib `json` only — no networkx. Direction matters: dependency edges run
caller→callee (`calls`) and importer→imported (`imports`), so "what depends on X"
= the predecessors of X reached by walking those edges in reverse.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

# Edges whose direction means "source depends on target".
DEPENDENCY_RELATIONS = {
    "calls",
    "imports",
    "uses",
    "depends_on",
    "references",
    "implements",
    "extends",
    "instantiates",
}

DEFAULT_MAX_HOPS = 3
HUB_TOP_N = 8
HUB_MIN_FANIN = 2


def _load(path: str | Path) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or "nodes" not in data:
        return None
    data.setdefault("links", data.get("edges", []))
    return data


def _links(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return graph.get("links") or graph.get("edges") or []


def find_nodes(graph: dict[str, Any], term: str) -> list[dict[str, Any]]:
    """Nodes whose label, id, or source_file contains `term` (case-insensitive)."""
    t = term.lower().strip()
    if not t:
        return []
    hits = []
    for n in graph.get("nodes", []):
        hay = " ".join(
            str(n.get(k, "")) for k in ("label", "id", "source_file", "norm_label")
        ).lower()
        if t in hay:
            hits.append(n)
    return hits


def _reverse_dep_adjacency(graph: dict[str, Any]) -> dict[str, set]:
    """predecessors[target] = {sources that depend on target}."""
    pred: dict[str, set] = defaultdict(set)
    for link in _links(graph):
        if link.get("relation") not in DEPENDENCY_RELATIONS:
            continue
        s, t = link.get("source"), link.get("target")
        if s is None or t is None:
            continue
        pred[t].add(s)
    return pred


def _in_degrees(graph: dict[str, Any]) -> dict[str, int]:
    indeg: dict[str, int] = defaultdict(int)
    for link in _links(graph):
        t = link.get("target")
        if t is not None:
            indeg[t] += 1
    return indeg


def _hub_ranking(graph: dict[str, Any]) -> dict[str, int]:
    """Map node id → 1-based hub rank (by in-degree). Only ranks fan-in ≥ min."""
    indeg = _in_degrees(graph)
    ranked = sorted(
        ((nid, d) for nid, d in indeg.items() if d >= HUB_MIN_FANIN),
        key=lambda kv: (-kv[1], str(kv[0])),
    )
    return {nid: i + 1 for i, (nid, _) in enumerate(ranked)}


def blast_radius(
    graph_path: str | Path,
    target: str,
    *,
    max_hops: int = DEFAULT_MAX_HOPS,
) -> dict[str, Any]:
    """Compute the dependents of `target` and whether it is a hub.

    Returns a dict; `error` is set when the graph or target is missing.
    """
    graph = _load(graph_path)
    if graph is None:
        return {"error": "graph_not_found", "graph_path": str(graph_path)}

    matched = find_nodes(graph, target)
    if not matched:
        return {"error": "target_not_found", "target": target, "dependents": []}

    nodes_by_id = {n.get("id"): n for n in graph.get("nodes", [])}
    pred = _reverse_dep_adjacency(graph)
    hub_rank = _hub_ranking(graph)
    top_hub_ranks = {nid for nid, r in hub_rank.items() if r <= HUB_TOP_N}

    matched_ids = {n.get("id") for n in matched}
    # BFS over predecessors (reverse dependency edges).
    visited: dict[str, int] = {}  # node id -> hops
    queue: deque = deque((mid, 0) for mid in matched_ids)
    while queue:
        nid, hops = queue.popleft()
        if hops >= max_hops:
            continue
        for p in sorted(pred.get(nid, ())):
            if p in matched_ids:
                continue
            if p not in visited or visited[p] > hops + 1:
                visited[p] = hops + 1
                queue.append((p, hops + 1))

    dependents = [
        {
            "id": nid,
            "label": nodes_by_id.get(nid, {}).get("label", nid),
            "source_file": nodes_by_id.get(nid, {}).get("source_file", ""),
            "hops": hops,
        }
        for nid, hops in sorted(visited.items(), key=lambda kv: (kv[1], str(kv[0])))
    ]

    best_rank = min((hub_rank.get(mid, 10**9) for mid in matched_ids), default=10**9)
    is_hub = any(mid in top_hub_ranks for mid in matched_ids)

    return {
        "target": target,
        "matched": [
            {"id": n.get("id"), "label": n.get("label"), "source_file": n.get("source_file", "")}
            for n in matched
        ],
        "dependents": dependents,
        "dependent_count": len(dependents),
        "is_hub": is_hub,
        "hub_rank": best_rank if best_rank < 10**9 else None,
        "max_hops": max_hops,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: python -m scripts.blast_radius <graph.json> <target> [max_hops]")
        raise SystemExit(2)
    g, tgt = sys.argv[1], sys.argv[2]
    hops = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_MAX_HOPS
    result = blast_radius(g, tgt, max_hops=hops)
    print(json.dumps(result, indent=2))
