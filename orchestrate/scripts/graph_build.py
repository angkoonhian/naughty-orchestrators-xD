"""graph_build — build/refresh the per-project graphs and compute the seam corpus.

Two responsibilities:
  1. Per-project graphs — built with graphify's FREE, deterministic AST path
     (no LLM): collect_files → extract → build_from_json → cluster → to_json.
     Runs only when graphify is importable; otherwise reports cleanly.
  2. Seam corpus — computes the *curated* cross-project contract file list
     (API controllers/DTOs + frontend `*.api.*` consumers). The seam graph itself
     is built by SEMANTIC extraction, which is LLM-driven and orchestrated from
     SKILL.md; this module only produces the file list + a build plan.

graphify is an OPTIONAL dependency. Nothing here is required for orchestrate to
function — when graphify is absent the integration simply stays disabled.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

API_CONTRACT_GLOBS = ["*.controller.ts", "*.dto.ts", "*.resolver.ts", "*.gateway.ts"]
FRONTEND_CONSUMER_GLOBS = ["*.api.ts", "*.api.js", "*.service.ts", "*.service.js"]
EXCLUDE_DIRS = {"node_modules", "dist", "build", ".git", "graphify-out", "__pycache__"}


def graphify_available() -> bool:
    try:
        import graphify  # noqa: F401

        return True
    except Exception:
        return False


def _excluded(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts)


def build_project_ast(project_path: str | Path, out_path: str | Path | None = None) -> dict[str, Any]:
    """Build one project's AST-only graph via graphify (free / no LLM).

    Returns a status dict; never raises. status ∈
    {built, graphify_unavailable, no_code, error}.
    """
    project_path = Path(project_path)
    if out_path is None:
        out_path = project_path / "graphify-out" / "graph.json"
    out_path = Path(out_path)

    if not graphify_available():
        return {"status": "graphify_unavailable", "project": project_path.name}

    try:
        from graphify.extract import collect_files, extract
        from graphify.build import build_from_json
        from graphify.cluster import cluster
        from graphify.export import to_json

        code_files = [p for p in collect_files(project_path) if not _excluded(Path(p))]
        if not code_files:
            return {"status": "no_code", "project": project_path.name}

        extraction = extract(code_files)
        if not extraction.get("nodes"):
            return {"status": "no_code", "project": project_path.name, "nodes": 0}

        graph = build_from_json(extraction)
        communities = cluster(graph)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        to_json(graph, communities, str(out_path), force=True)
        return {
            "status": "built",
            "project": project_path.name,
            "graph": str(out_path),
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "communities": len(communities),
            "llm_used": False,
        }
    except Exception as e:  # graphify present but failed — degrade, don't crash
        return {"status": "error", "project": project_path.name, "error": f"{type(e).__name__}: {e}"}


def build_all_projects_ast(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Build AST graphs for every project in a scanned profile."""
    results = []
    for proj in profile.get("projects", []) or []:
        results.append(build_project_ast(proj["path"]))
    return results


def compute_seam_corpus(root: str | Path, profile: dict[str, Any]) -> dict[str, Any]:
    """Compute the curated cross-project contract corpus for the seam graph.

    api_contracts: controller/DTO files from backend (framework nestjs/express)
    frontend_consumers: *.api.* / *.service.* from non-backend projects
    """
    root = Path(root)
    backend_frameworks = {"nestjs", "express", "fastify", "koa", "hono"}
    api_contracts: list[str] = []
    frontend_consumers: list[str] = []

    for proj in profile.get("projects", []) or []:
        ppath = Path(proj["path"])
        is_backend = proj.get("framework") in backend_frameworks
        globs = API_CONTRACT_GLOBS if is_backend else FRONTEND_CONSUMER_GLOBS
        bucket = api_contracts if is_backend else frontend_consumers
        src = ppath / "src" if (ppath / "src").exists() else ppath
        for g in globs:
            for f in src.rglob(g):
                if _excluded(f):
                    continue
                bucket.append(str(f))

    api_contracts = sorted(set(api_contracts))
    frontend_consumers = sorted(set(frontend_consumers))
    return {
        "api_contracts": api_contracts,
        "frontend_consumers": frontend_consumers,
        "all": sorted(set(api_contracts + frontend_consumers)),
        "count": len(set(api_contracts + frontend_consumers)),
    }


def write_seam_manifest(corpus: dict[str, Any], root: str | Path) -> str:
    """Persist the seam corpus so the LLM-driven seam build step can read it."""
    out = Path(root) / "docs" / "agents" / "graph" / "seam" / "corpus.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(corpus, indent=2), encoding="utf-8")
    return str(out)


def build_plan(root: str | Path, profile: dict[str, Any]) -> dict[str, Any]:
    """Describe what a refresh-graph would do, without doing it (for --dry-run)."""
    corpus = compute_seam_corpus(root, profile)
    projects = [p["name"] for p in profile.get("projects", []) or []]
    return {
        "graphify_available": graphify_available(),
        "per_project_ast_builds": projects,
        "per_project_cost": "free (AST, no LLM)",
        "seam_corpus_files": corpus["count"],
        "seam_cost": "semantic extraction over the seam corpus (LLM; bounded by corpus size)",
        "notes": (
            "Per-project graphs are free and deterministic. Only the seam graph "
            "spends tokens, over the curated contract corpus only."
        ),
    }


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.scan import scan_project

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    profile = scan_project(root)
    plan = build_plan(root, profile)
    print(json.dumps(plan, indent=2, default=str))
