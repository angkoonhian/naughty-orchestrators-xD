"""graph_bake — distill graphify graph.json files into the orchestration snapshot.

Reads per-project graphs (`<project>/graphify-out/graph.json`) and an optional
cross-project "seam" graph, and produces `.claude/orchestration.graph.json` — the
ONLY graph artifact the orchestrator reads at runtime.

Design constraints:
  - stdlib `json` only (NO networkx import) so it runs and unit-tests in isolation,
    independent of whether graphify is installed.
  - Pure / deterministic: same inputs → byte-identical snapshot (timestamp aside).

graphify graph.json schema (verified): networkx node-link JSON —
  nodes[]: {id, label, community (int|null), norm_label, source_file, file_type, ...}
  links[]: {source, target (node ids, true direction), relation, confidence
            (EXTRACTED|INFERRED|AMBIGUOUS), confidence_score, weight, ...}
  top-level: {directed: bool, ...}

See references/graph-integration.md for the full contract.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Split an identifier into word tokens: break on non-alpha AND camelCase/PascalCase
# boundaries, so "AuthGuard" / "auth_service" both yield ["auth", "guard"/"service"].
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+")

SCHEMA_VERSION = 1
DEFAULT_HUB_TOP_N = 8
HUB_MIN_FANIN = 2

# Relations that count as cross-project coupling in the seam graph.
SEAM_RELATIONS = {
    "shares_data_with",
    "semantically_similar_to",
    "references",
    "conceptually_related_to",
    "cites",
}


def load_graph(path: str | Path) -> dict[str, Any] | None:
    """Load a graphify graph.json. Returns None on missing/invalid file."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or "nodes" not in data:
        return None
    data.setdefault("links", [])
    return data


def _links(graph: dict[str, Any]) -> list[dict[str, Any]]:
    # node-link export uses "links"; tolerate "edges" just in case.
    return graph.get("links") or graph.get("edges") or []


def _degrees(graph: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Compute in/out/total degree per node id from links (true direction)."""
    deg: dict[str, dict[str, int]] = defaultdict(lambda: {"in": 0, "out": 0, "deg": 0})
    for link in _links(graph):
        s, t = link.get("source"), link.get("target")
        if s is None or t is None:
            continue
        deg[s]["out"] += 1
        deg[s]["deg"] += 1
        deg[t]["in"] += 1
        deg[t]["deg"] += 1
    return deg


def _incoming_confidence(graph: dict[str, Any]) -> dict[str, Counter]:
    """For each node id, a Counter of incoming-edge confidence tags."""
    inc: dict[str, Counter] = defaultdict(Counter)
    for link in _links(graph):
        t = link.get("target")
        if t is None:
            continue
        inc[t][link.get("confidence", "EXTRACTED")] += 1
    return inc


def _label_for(node: dict[str, Any]) -> str:
    return node.get("label") or node.get("id") or "?"


def _community_label(member_labels: list[str]) -> str:
    """Derive a short human label for a community from its members' labels.

    Picks the most common alphabetic token across member labels; falls back to
    the first member label. Deterministic.
    """
    tokens: Counter = Counter()
    for lbl in member_labels:
        for tok in _CAMEL_RE.findall(str(lbl)):
            if len(tok) >= 3:
                tokens[tok.lower()] += 1
    if tokens:
        # most common, tie-break alphabetically for determinism
        best = sorted(tokens.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        return best.capitalize()
    return member_labels[0] if member_labels else "Community"


def _communities(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Group nodes by their graphify `community` attribute.

    Returns [] when no node carries a community (e.g. an AST-only graph that was
    not clustered) — callers then fall back to subdomain counting.
    """
    by_comm: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for node in graph.get("nodes", []):
        cid = node.get("community")
        if cid is None:
            continue
        by_comm[cid].append(node)

    communities: list[dict[str, Any]] = []
    for cid in sorted(by_comm.keys(), key=lambda c: str(c)):
        members = by_comm[cid]
        member_labels = sorted(_label_for(n) for n in members)
        communities.append(
            {
                "id": f"c{cid}",
                "label": _community_label(member_labels),
                "size": len(members),
                "members": member_labels,
                "provenance": "graphify",
            }
        )
    return communities


def _hubs(graph: dict[str, Any], top_n: int = DEFAULT_HUB_TOP_N) -> list[dict[str, Any]]:
    """Rank nodes by fan-in (in-degree). High fan-in = touching it ripples widely."""
    deg = _degrees(graph)
    inc_conf = _incoming_confidence(graph)
    nodes_by_id = {n.get("id"): n for n in graph.get("nodes", [])}

    ranked = []
    for nid, d in deg.items():
        if d["in"] < HUB_MIN_FANIN:
            continue
        node = nodes_by_id.get(nid, {})
        conf = inc_conf.get(nid, Counter())
        extracted = conf.get("EXTRACTED", 0)
        total = sum(conf.values()) or 1
        provenance = "EXTRACTED" if extracted * 2 >= total else "INFERRED"
        ranked.append(
            {
                "id": nid,
                "label": _label_for(node),
                "source_file": node.get("source_file", ""),
                "in_degree": d["in"],
                "degree": d["deg"],
                "provenance": provenance,
            }
        )
    # Sort by in_degree desc, then degree desc, then label for determinism.
    ranked.sort(key=lambda h: (-h["in_degree"], -h["degree"], str(h["label"])))
    return ranked[:top_n]


def _graph_complexity(node_count: int, community_count: int) -> str:
    if community_count >= 5 or node_count >= 30:
        return "high"
    if node_count >= 10:
        return "medium"
    return "low"


def bake_project(path: str | Path, top_n: int = DEFAULT_HUB_TOP_N) -> dict[str, Any] | None:
    """Bake one project's graph.json into the per-project snapshot block."""
    graph = load_graph(path)
    if graph is None:
        return None
    node_count = len(graph.get("nodes", []))
    edge_count = len(_links(graph))
    communities = _communities(graph)
    hubs = _hubs(graph, top_n)
    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "community_count": len(communities),
        "complexity": _graph_complexity(node_count, len(communities)),
        "metrics": {"hub_count": len(hubs), "modularity": None},
        "communities": communities,
        "hubs": hubs,
    }


def _attribute_project(source_file: str, project_names: list[str]) -> str | None:
    """Attribute a seam node to a project by matching its source_file path."""
    if not source_file:
        return None
    norm = source_file.replace("\\", "/")
    segments = set(norm.split("/"))
    # Prefer an exact path-segment match; longest name first to avoid prefixes.
    for name in sorted(project_names, key=len, reverse=True):
        if name in segments or name in norm:
            return name
    return None


def bake_seam(
    path: str | Path, project_names: list[str]
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Extract cross-project coupling from the seam graph.

    Returns (seam_map, co_fire). Only edges connecting two *different* attributed
    projects are kept.
    """
    graph = load_graph(path)
    if graph is None:
        return [], {}

    nodes_by_id = {n.get("id"): n for n in graph.get("nodes", [])}
    seam_map: list[dict[str, Any]] = []
    co_fire: dict[str, set] = defaultdict(set)

    for link in _links(graph):
        if link.get("relation") not in SEAM_RELATIONS:
            continue
        s_node = nodes_by_id.get(link.get("source"))
        t_node = nodes_by_id.get(link.get("target"))
        if not s_node or not t_node:
            continue
        s_proj = _attribute_project(s_node.get("source_file", ""), project_names)
        t_proj = _attribute_project(t_node.get("source_file", ""), project_names)
        if not s_proj or not t_proj or s_proj == t_proj:
            continue
        confidence = link.get("confidence", "INFERRED")
        seam_map.append(
            {
                "from_project": s_proj,
                "from": _label_for(s_node),
                "to_project": t_proj,
                "to": _label_for(t_node),
                "relation": link.get("relation"),
                "confidence": confidence,
                "confidence_score": link.get("confidence_score"),
                "provenance": confidence,
            }
        )
        co_fire[s_proj].add(t_proj)
        co_fire[t_proj].add(s_proj)

    # Deterministic ordering.
    seam_map.sort(
        key=lambda e: (e["from_project"], e["to_project"], str(e["from"]), str(e["to"]))
    )
    co_fire_out = {k: sorted(v) for k, v in sorted(co_fire.items())}
    return seam_map, co_fire_out


def bake(
    per_project_graphs: dict[str, str],
    seam_graph_path: str | None,
    project_names: list[str],
    *,
    built_at: str,
    top_n: int = DEFAULT_HUB_TOP_N,
    enabled: bool = True,
) -> dict[str, Any]:
    """Produce the full orchestration snapshot dict.

    per_project_graphs: {project_name: path-to-graph.json}
    seam_graph_path: path to the seam graph.json, or None
    project_names: all project names (for seam attribution)
    built_at: ISO timestamp (caller-supplied; this module never calls the clock)
    """
    projects: dict[str, Any] = {}
    used_sources: dict[str, str] = {}
    for name, gpath in sorted(per_project_graphs.items()):
        block = bake_project(gpath, top_n)
        if block is not None:
            projects[name] = block
            used_sources[name] = str(gpath)

    seam_map, co_fire = ([], {})
    seam_source = None
    if seam_graph_path and Path(seam_graph_path).exists():
        seam_map, co_fire = bake_seam(seam_graph_path, project_names)
        seam_source = str(seam_graph_path)

    return {
        "schema_version": SCHEMA_VERSION,
        "built_at": built_at,
        "graph_integration": "enabled" if enabled else "disabled",
        "source": {
            "per_project_graphs": used_sources,
            "seam_graph": seam_source,
        },
        "projects": projects,
        "seam_map": seam_map,
        "co_fire": co_fire,
    }


def discover_per_project_graphs(root: str | Path) -> dict[str, str]:
    """Find `<root>/*/graphify-out/graph.json` files. Project name = the dir name."""
    root = Path(root)
    found: dict[str, str] = {}
    for gpath in sorted(root.glob("*/graphify-out/graph.json")):
        project_name = gpath.parent.parent.name
        found[project_name] = str(gpath)
    # single-app: <root>/graphify-out/graph.json
    self_graph = root / "graphify-out" / "graph.json"
    if self_graph.exists():
        found.setdefault(root.name, str(self_graph))
    return found


def write_snapshot(snapshot: dict[str, Any], out_path: str | Path) -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=False), encoding="utf-8")
    return str(out)


if __name__ == "__main__":
    import sys

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    # built_at is passed in by the orchestration glue; CLI use stamps a placeholder.
    built_at = sys.argv[2] if len(sys.argv) > 2 else "1970-01-01T00:00:00Z"
    per_project = discover_per_project_graphs(root)
    seam = root / "docs" / "agents" / "graph" / "seam" / "graphify-out" / "graph.json"
    snapshot = bake(
        per_project,
        str(seam) if seam.exists() else None,
        list(per_project.keys()),
        built_at=built_at,
    )
    out = write_snapshot(snapshot, root / ".claude" / "orchestration.graph.json")
    print(
        f"Snapshot written: {out}\n"
        f"  projects: {len(snapshot['projects'])}, "
        f"seam edges: {len(snapshot['seam_map'])}"
    )
