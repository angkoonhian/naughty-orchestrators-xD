"""Update mode — re-scan the project, diff against stored config, report new detections."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
import yaml

from scripts.scan import scan_project
from scripts.infer import infer_recommendations
from scripts import graph_bake


def _load_config(project_root: Path) -> dict[str, Any] | None:
    config_path = project_root / ".claude" / "orchestration.config.yaml"
    if not config_path.exists():
        return None
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def update(project_root: Path) -> dict[str, Any]:
    """Re-scan and diff against stored config. Returns new detections."""
    project_root = Path(project_root).resolve()
    stored = _load_config(project_root)
    new_profile = scan_project(project_root)
    new_recs = infer_recommendations(new_profile)

    if stored is None:
        return {
            "mode": "update",
            "stored_config_present": False,
            "message": "No prior orchestration.config.yaml — run /orchestrate (without --update) first.",
            "current_profile": new_profile,
            "current_recommendations": new_recs,
        }

    stored_packs = set(stored.get("platform_pack", {}).get("critics", []) or [])
    new_packs = set(new_recs.get("recommended_platform_packs", []))
    added_packs = sorted(new_packs - stored_packs)
    removed_packs = sorted(stored_packs - new_packs)

    stored_leads = stored.get("adaptive_tier2", {}).get("enabled_leads", []) or []
    new_leads = new_recs.get("adaptive_tier2_leads", [])
    added_leads = sorted(set(new_leads) - set(stored_leads))

    result = {
        "mode": "update",
        "stored_config_present": True,
        "added_platform_packs": added_packs,
        "removed_platform_packs": removed_packs,
        "added_adaptive_tier2_leads": added_leads,
        "current_profile": new_profile,
        "current_recommendations": new_recs,
        "summary": f"+{len(added_packs)} packs, -{len(removed_packs)} packs, +{len(added_leads)} adaptive Tier 2 leads",
    }

    # Re-bake the graph snapshot + diff, only when integration is enabled.
    if (stored.get("graph_integration") or {}).get("enabled"):
        result["graph"] = _rebake_and_diff(project_root)

    return result


def _rebake_and_diff(project_root: Path) -> dict[str, Any]:
    """Re-bake the snapshot from current per-project + seam graphs; diff vs prior."""
    snap_path = project_root / ".claude" / "orchestration.graph.json"
    prior = {}
    if snap_path.exists():
        try:
            prior = json.loads(snap_path.read_text(encoding="utf-8"))
        except Exception:
            prior = {}

    per_project = graph_bake.discover_per_project_graphs(project_root)
    if not per_project:
        return {"status": "no_graphs", "message": "No per-project graphs found — run /orchestrate refresh-graph."}

    seam = project_root / "docs" / "agents" / "graph" / "seam" / "graphify-out" / "graph.json"
    built_at = datetime.datetime.utcnow().isoformat() + "Z"
    snapshot = graph_bake.bake(
        per_project,
        str(seam) if seam.exists() else None,
        list(per_project.keys()),
        built_at=built_at,
    )
    graph_bake.write_snapshot(snapshot, snap_path)

    def _hub_set(snap: dict) -> set:
        return {
            (name, h.get("label"))
            for name, blk in (snap.get("projects", {}) or {}).items()
            for h in (blk.get("hubs", []) or [])
        }

    def _seam_set(snap: dict) -> set:
        return {(e["from_project"], e["to_project"]) for e in (snap.get("seam_map", []) or [])}

    new_hubs = sorted(f"{n}:{l}" for n, l in (_hub_set(snapshot) - _hub_set(prior)))
    new_seams = sorted(f"{a}→{b}" for a, b in (_seam_set(snapshot) - _seam_set(prior)))
    return {
        "status": "rebaked",
        "projects": len(snapshot.get("projects", {})),
        "seam_edges": len(snapshot.get("seam_map", [])),
        "new_hubs": new_hubs,
        "new_seam_edges": new_seams,
        "built_at": built_at,
    }


if __name__ == "__main__":
    import json
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    result = update(target)
    print(json.dumps(result, indent=2, default=str))
