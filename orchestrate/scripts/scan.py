"""Codebase scanner — produces a project profile from a directory tree.

Outputs a dict with the shape documented in references/scan-signals.md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

FRAMEWORK_MARKERS_JS = {
    "@nestjs/core": "nestjs",
    "next": "next",
    "nuxt": "nuxt",
    "remix-run": "remix",
    "astro": "astro",
    "@angular/core": "angular",
    "react": "react",
    "vue": "vue",
    "svelte": "svelte",
    "express": "express",
    "fastify": "fastify",
    "koa": "koa",
    "hono": "hono",
}

INFRASTRUCTURE_MARKERS = {
    "real_time": {
        "socket.io": "socket.io",
        "@nestjs/websockets": "socket.io",
        "ws": "ws",
        "sockjs-client": "sockjs",
    },
    "queues": {
        "bull": "bull",
        "bullmq": "bullmq",
        "agenda": "agenda",
        "celery": "celery",
        "amqp": "rabbitmq",
        "amqplib": "rabbitmq",
        "kafkajs": "kafka",
    },
    "cache": {
        "ioredis": "redis",
        "redis": "redis",
        "@nestjs/cache-manager": "redis",
    },
    "observability": {
        "@sentry/node": "sentry",
        "@sentry/react": "sentry",
        "@sentry/nextjs": "sentry",
        "datadog": "datadog",
        "dd-trace": "datadog",
        "newrelic": "newrelic",
        "bugsnag": "bugsnag",
    },
    "orm": {
        "typeorm": "typeorm",
        "prisma": "prisma",
        "sequelize": "sequelize",
        "mongoose": "mongoose",
        "drizzle-orm": "drizzle",
    },
    "file_uploads": {
        "multer": "multer",
        "formidable": "formidable",
        "busboy": "busboy",
        "@nestjs/platform-multer": "multer",
    },
    "payments": {
        "stripe": "stripe",
    },
    "auth_jwt": {
        "passport-jwt": "passport-jwt",
        "@nestjs/jwt": "@nestjs/jwt",
        "jsonwebtoken": "jsonwebtoken",
        "jose": "jose",
    },
    "graphql": {
        "graphql": "graphql",
        "apollo-server": "apollo",
        "@apollo/server": "apollo",
        "type-graphql": "type-graphql",
        "@nestjs/graphql": "nestjs-graphql",
    },
    "timezone": {
        "moment-timezone": "moment-timezone",
        "luxon": "luxon",
    },
    "email": {
        "@aws-sdk/client-ses": "ses",
        "nodemailer": "nodemailer",
        "@sendgrid/mail": "sendgrid",
    },
}

ADAPTIVE_TIER2_FILE_THRESHOLD = 30
ADAPTIVE_TIER2_SUBDOMAIN_THRESHOLD = 5


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _all_deps(pkg: dict) -> dict:
    return {
        **pkg.get("dependencies", {}),
        **pkg.get("devDependencies", {}),
        **pkg.get("peerDependencies", {}),
        **pkg.get("optionalDependencies", {}),
    }


def _detect_framework(deps: dict) -> str | None:
    for marker, framework in FRAMEWORK_MARKERS_JS.items():
        if marker in deps:
            return framework
    return None


def _detect_workspace(root: Path) -> bool:
    markers = ["pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json"]
    return any((root / m).exists() for m in markers)


def _count_source_files(project_path: Path) -> int:
    src = project_path / "src"
    if not src.exists():
        # Fallback: count top-level JS/TS files
        return len(list(project_path.glob("*.ts")) + list(project_path.glob("*.js")) + list(project_path.glob("*.tsx")) + list(project_path.glob("*.jsx")))
    return sum(1 for _ in src.rglob("*.ts")) + sum(1 for _ in src.rglob("*.tsx")) + sum(1 for _ in src.rglob("*.js")) + sum(1 for _ in src.rglob("*.jsx")) + sum(1 for _ in src.rglob("*.py"))


def _detect_subdomains(project_path: Path) -> list[str]:
    """Top-level dirs under src/ (or equivalent) represent subdomains."""
    candidates = [project_path / "src", project_path / "src" / "model", project_path / "src" / "modules", project_path / "src" / "features", project_path / "app"]
    for src in candidates:
        if src.exists() and src.is_dir():
            subs = [d.name for d in src.iterdir() if d.is_dir() and not d.name.startswith(".") and d.name not in ("__pycache__", "node_modules")]
            if subs:
                return sorted(subs)
    return []


def _detect_multi_db_in_project(project_path: Path) -> bool:
    """Detect multiple DB connections by scanning for DataSource / createConnection patterns."""
    patterns = [re.compile(r"new\s+DataSource\("), re.compile(r"createConnection\("), re.compile(r"new\s+Pool\(")]
    count = 0
    for f in project_path.rglob("*.ts"):
        if "node_modules" in f.parts:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            for pat in patterns:
                count += len(pat.findall(content))
            if count >= 2:
                return True
        except Exception:
            continue
        if count >= 2:
            return True
    return count >= 2


def _detect_multi_tenant(project_path: Path) -> bool:
    """Detect multi-tenancy by repeated tenant_id/company_id/organization_id column patterns."""
    tenant_patterns = re.compile(r"\b(tenant_id|company_id|organization_id|workspace_id|tenantId|companyId|organizationId|workspaceId)\b")
    hit_files = 0
    for f in project_path.rglob("*.ts"):
        if "node_modules" in f.parts:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            if tenant_patterns.search(content):
                hit_files += 1
                if hit_files >= 3:
                    return True
        except Exception:
            continue
    return hit_files >= 3


def _detect_growing_tables(project_path: Path) -> bool:
    """Detect growing/log tables — entity names matching *_reading / *_log / *_event / *_audit."""
    pattern = re.compile(r"\b\w+_(reading|log|event|audit)\b")
    for f in project_path.rglob("*.ts"):
        if "node_modules" in f.parts:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(content):
                return True
        except Exception:
            continue
    return False


def _classify_infrastructure(deps: dict) -> dict[str, Any]:
    """Map deps to infrastructure capabilities."""
    infra: dict[str, Any] = {}
    for category, markers in INFRASTRUCTURE_MARKERS.items():
        for dep, name in markers.items():
            if dep in deps:
                if category in ("queues", "observability", "orm"):
                    infra.setdefault(category, []).append(name)
                else:
                    infra[category] = name
                    break
    return infra


def _extract_qa_scripts(pkg: dict) -> dict:
    scripts = pkg.get("scripts", {})
    return {
        "lint": scripts.get("lint") or scripts.get("lint:fix"),
        "test": scripts.get("test"),
        "test_e2e": scripts.get("test:e2e") or scripts.get("e2e"),
        "test_integration": scripts.get("test:integration"),
        "typecheck": scripts.get("typecheck") or scripts.get("build"),
    }


def _scan_project_node(project_path: Path) -> dict[str, Any]:
    pkg = _read_json(project_path / "package.json")
    deps = _all_deps(pkg)
    framework = _detect_framework(deps)
    file_count = _count_source_files(project_path)
    subdomains = _detect_subdomains(project_path)
    complexity = "high" if (file_count >= ADAPTIVE_TIER2_FILE_THRESHOLD or len(subdomains) >= ADAPTIVE_TIER2_SUBDOMAIN_THRESHOLD) else "medium" if file_count >= 10 else "low"

    return {
        "name": pkg.get("name", project_path.name),
        "path": str(project_path),
        "framework": framework,
        "file_count": file_count,
        "subdomains": subdomains,
        "complexity": complexity,
        "deps": deps,
        "qa_scripts": _extract_qa_scripts(pkg),
    }


def _detect_existing_orchestration(root: Path) -> dict[str, Any]:
    return {
        "root_claude_md": (root / "CLAUDE.md").exists(),
        "docs_agents": (root / "docs" / "agents").exists(),
        "config": (root / ".claude" / "orchestration.config.yaml").exists(),
    }


def _load_graph_snapshot(root: Path) -> dict[str, Any] | None:
    """Read the baked orchestration graph snapshot if present AND enabled.

    Returns None when the snapshot is missing, unreadable, or marked disabled —
    in which case scanning behaves exactly as it did before graph integration.
    """
    snap_path = root / ".claude" / "orchestration.graph.json"
    if not snap_path.exists():
        return None
    try:
        data = json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("graph_integration") != "enabled":
        return None
    return data


def _enrich_with_graph(profile: dict[str, Any], snapshot: dict[str, Any]) -> None:
    """Attach graph metrics to the profile in place. Graph complexity wins."""
    gproj = snapshot.get("projects", {}) or {}
    for p in profile.get("projects", []):
        gp = gproj.get(p["name"])
        if not gp:
            continue
        p["graph_metrics"] = {
            "node_count": gp.get("node_count", 0),
            "edge_count": gp.get("edge_count", 0),
            "community_count": gp.get("community_count", 0),
            "hub_count": gp.get("metrics", {}).get("hub_count", 0),
            "hubs": [h.get("label") for h in gp.get("hubs", [])],
            "communities": [c.get("label") for c in gp.get("communities", [])],
        }
        # Graph-derived complexity takes precedence over file/subdomain counting.
        if gp.get("complexity"):
            p["complexity"] = gp["complexity"]

    profile["graph"] = {
        "present": True,
        "built_at": snapshot.get("built_at"),
        "seam_edges": len(snapshot.get("seam_map", []) or []),
        "co_fire": snapshot.get("co_fire", {}) or {},
        "communities_by_project": {
            name: [c.get("label") for c in blk.get("communities", [])]
            for name, blk in gproj.items()
        },
        "hubs_by_project": {
            name: [h.get("label") for h in blk.get("hubs", [])]
            for name, blk in gproj.items()
        },
    }


def scan_project(root: Path) -> dict[str, Any]:
    """Scan a project directory and produce a profile dict."""
    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project root does not exist: {root}")

    package_jsons_at_depth_2 = [
        p for p in root.glob("*/package.json")
        if "node_modules" not in p.parts and "/.backups/" not in str(p).replace("\\", "/")
    ]
    has_root_package = (root / "package.json").exists()
    workspace = _detect_workspace(root)

    if workspace or len(package_jsons_at_depth_2) >= 2:
        shape = "monorepo"
        projects: list[dict] = []
        for pkg_path in package_jsons_at_depth_2:
            projects.append(_scan_project_node(pkg_path.parent))
        if has_root_package and not workspace:
            # Root has its own package; treat as additional project
            projects.append(_scan_project_node(root))
    elif has_root_package:
        shape = "single_app"
        projects = [_scan_project_node(root)]
    else:
        shape = "unknown"
        projects = []

    # Aggregate infrastructure across all projects
    all_deps: dict = {}
    for p in projects:
        all_deps.update(p.get("deps", {}))

    infrastructure = _classify_infrastructure(all_deps)

    # Code-pattern detection across all projects
    multi_db = any(_detect_multi_db_in_project(Path(p["path"])) for p in projects)
    multi_tenant = any(_detect_multi_tenant(Path(p["path"])) for p in projects)
    growing_tables = any(_detect_growing_tables(Path(p["path"])) for p in projects)

    if multi_db:
        infrastructure["multi_db"] = True
    if multi_tenant:
        infrastructure["multi_tenant"] = True
    if growing_tables:
        infrastructure["growing_tables"] = True

    # Strip deps from projects (they're aggregated above; per-project deps not needed downstream)
    for p in projects:
        p.pop("deps", None)

    profile: dict[str, Any] = {
        "shape": shape,
        "primary_language": "typescript" if projects else "unknown",
        "projects": projects,
        "infrastructure": infrastructure,
        "domain_markers": {
            "multi_tenant": multi_tenant,
            "multi_db": multi_db,
            "growing_tables": growing_tables,
        },
        "existing_orchestration": _detect_existing_orchestration(root),
        "graph": None,
    }

    # Optional graph enrichment — only when a baked, enabled snapshot exists.
    snapshot = _load_graph_snapshot(root)
    if snapshot:
        _enrich_with_graph(profile, snapshot)

    return profile


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    profile = scan_project(root)
    print(json.dumps(profile, indent=2, default=str))
