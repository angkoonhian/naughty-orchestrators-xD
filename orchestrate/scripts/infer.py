"""Infer recommendations from a scanned project profile.

Outputs:
  - recommended_platform_packs: list[str]
  - recommended_personas: list[str]   (empty unless domain hint provided)
  - qa_wiring: dict
  - adaptive_tier2_leads: list[str]
  - impact_bumps: list[dict]
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml

# Pack discovery — read packs/ directory at runtime so adding packs doesn't require code changes.
SKILL_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_PACKS_DIR = SKILL_ROOT / "platform-packs"


def _load_pack_manifests() -> list[dict[str, Any]]:
    packs = []
    if not PLATFORM_PACKS_DIR.exists():
        return packs
    for pack_dir in sorted(PLATFORM_PACKS_DIR.iterdir()):
        if not pack_dir.is_dir():
            continue
        manifest_path = pack_dir / "pack.yaml"
        if not manifest_path.exists():
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest["_pack_dir"] = pack_dir.name
            packs.append(manifest)
        except Exception:
            continue
    return packs


def _profile_signals(profile: dict[str, Any]) -> dict[str, Any]:
    """Flatten profile into a set of signals for trigger matching."""
    infra = profile.get("infrastructure", {}) or {}
    domain = profile.get("domain_markers", {}) or {}

    # Collect all "deps_present" signals — direct framework / infra dep names.
    deps_present: set[str] = set()

    # Real-time
    rt = infra.get("real_time")
    if rt:
        deps_present.add(rt)
    # Queues
    for q in infra.get("queues", []) or []:
        deps_present.add(q)
    # Observability
    for o in infra.get("observability", []) or []:
        if o == "sentry":
            deps_present.update({"@sentry/node", "@sentry/react", "sentry-sdk"})
        else:
            deps_present.add(o)
    # File uploads
    fu = infra.get("file_uploads")
    if fu:
        deps_present.add(fu)
    # Payments
    pay = infra.get("payments")
    if pay:
        deps_present.add(pay)
    # JWT
    jwt = infra.get("auth_jwt")
    if jwt:
        deps_present.add(jwt)
    # Timezone
    tz = infra.get("timezone")
    if tz:
        deps_present.add(tz)
    # Email — usually informs but doesn't trigger a pack
    # GraphQL
    gql = infra.get("graphql")
    if gql:
        deps_present.add(gql)

    return {
        "deps_present": deps_present,
        "multi_tenant": domain.get("multi_tenant", False),
        "multi_db": domain.get("multi_db", False),
        "growing_tables": domain.get("growing_tables", False),
    }


def _pack_matches(pack: dict[str, Any], signals: dict[str, Any]) -> bool:
    triggers = pack.get("triggers", {}) or {}
    any_of = triggers.get("any_of", []) or []
    all_of = triggers.get("all_of", []) or []

    def _check_clause(clause: dict[str, Any]) -> bool:
        if "dep_present" in clause:
            return clause["dep_present"] in signals["deps_present"]
        if "code_pattern" in clause:
            # Map common code patterns to our domain flags
            pattern = clause["code_pattern"]
            if pattern in ("tenant_id", "company_id", "organization_id", "workspace_id", "tenantId", "companyId", "organizationId", "workspaceId"):
                return signals["multi_tenant"]
            if pattern in ("new DataSource", "createConnection", "createPool", "new Pool", "DATABASES = {"):
                return signals["multi_db"]
            if pattern.endswith("_reading") or pattern.endswith("_log") or pattern.endswith("_event") or pattern.endswith("_audit"):
                return signals["growing_tables"]
            return False
        return False

    if all_of and not all(_check_clause(c) for c in all_of):
        return False
    if any_of and not any(_check_clause(c) for c in any_of):
        return False
    return bool(any_of or all_of)


def _qa_wiring(profile: dict[str, Any]) -> dict[str, Any]:
    """Choose QA commands from the first project that has them, or merged."""
    for proj in profile.get("projects", []) or []:
        scripts = proj.get("qa_scripts") or {}
        if any(scripts.values()):
            return {
                "type": "npm_scripts",
                "commands": {k: v for k, v in scripts.items() if v},
                "project_path": proj.get("path"),
            }
    return {"type": "none", "commands": {}}


def _adaptive_tier2_leads(profile: dict[str, Any]) -> list[str]:
    return [proj["name"] for proj in profile.get("projects", []) if proj.get("complexity") == "high"]


def _impact_bumps(profile: dict[str, Any]) -> list[dict[str, str]]:
    bumps = []
    if profile.get("domain_markers", {}).get("multi_tenant"):
        bumps.append({"condition": "touches tenant-scoped data", "bump_to_minimum": "HIGH"})
    # Graph-derived bump: changing a high-fan-in hub module ripples widely.
    if profile.get("graph", {}) and profile["graph"].get("present"):
        bumps.append(
            {
                "condition": "touches a graph hub (high-fan-in module)",
                "bump_to_minimum": "HIGH",
                "provenance": "EXTRACTED",
            }
        )
    # Other domain-based bumps can be added by user via config
    return bumps


def _graph_recommendations(profile: dict[str, Any]) -> dict[str, Any]:
    """Recommendations derived from the baked graph snapshot, if present.

    Empty/neutral when there is no graph — so callers can merge unconditionally.
    """
    graph = profile.get("graph")
    if not graph or not graph.get("present"):
        return {"tier2_domain_boundaries": {}, "seam_routing": {}}

    high_complexity = {p["name"] for p in profile.get("projects", []) if p.get("complexity") == "high"}
    communities_by_project = graph.get("communities_by_project", {}) or {}
    # Domain-lead boundaries: communities of the deep (high-complexity) projects.
    tier2_boundaries = {
        name: communities_by_project.get(name, [])
        for name in sorted(high_complexity)
        if communities_by_project.get(name)
    }
    return {
        "tier2_domain_boundaries": tier2_boundaries,
        "seam_routing": graph.get("co_fire", {}) or {},
    }


def infer_recommendations(profile: dict[str, Any]) -> dict[str, Any]:
    signals = _profile_signals(profile)
    packs = _load_pack_manifests()
    recommended = [p["name"] for p in packs if _pack_matches(p, signals)]

    recs = {
        "recommended_platform_packs": sorted(recommended),
        "recommended_personas": [],  # Filled in interactive ask phase
        "qa_wiring": _qa_wiring(profile),
        "adaptive_tier2_leads": _adaptive_tier2_leads(profile),
        "impact_bumps": _impact_bumps(profile),
    }
    recs.update(_graph_recommendations(profile))
    return recs


if __name__ == "__main__":
    import json
    import sys
    profile_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if profile_path and profile_path.exists():
        profile = json.loads(profile_path.read_text())
    else:
        from scripts.scan import scan_project
        profile = scan_project(Path.cwd())
    print(json.dumps(infer_recommendations(profile), indent=2, default=str))
