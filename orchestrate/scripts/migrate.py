"""Migrate mode — handles projects with existing CLAUDE.md / docs/agents.

Backs up existing content first, then runs generate (which preserves existing files).
"""
from __future__ import annotations

import shutil
import datetime
from pathlib import Path
from typing import Any
import yaml

from scripts.generate import generate_orchestration


def _create_backup(project_root: Path) -> Path:
    """Back up existing CLAUDE.md + docs/agents tree before modification."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    backup_dir = project_root / ".claude" / f"orchestration.backup-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Back up root CLAUDE.md
    root_claude = project_root / "CLAUDE.md"
    if root_claude.exists():
        shutil.copy2(root_claude, backup_dir / "CLAUDE.md")

    # Back up entire docs/agents tree
    agents_dir = project_root / "docs" / "agents"
    if agents_dir.exists():
        backup_agents = backup_dir / "docs" / "agents"
        backup_agents.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(agents_dir, backup_agents)

    # Write manifest
    manifest = {
        "backed_up_at": datetime.datetime.utcnow().isoformat() + "Z",
        "files_backed_up": {
            "CLAUDE.md": root_claude.exists(),
            "docs/agents": agents_dir.exists(),
        },
        "restore_command": f"/orchestrate restore {backup_dir.name}",
    }
    (backup_dir / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return backup_dir


def _retire_legacy_devils_advocate(project_root: Path, backup_dir: Path) -> bool:
    """If old devils-advocate.md exists, copy to backup (already done via dir copy) and delete from live."""
    da = project_root / "docs" / "agents" / "cross-cutting" / "devils-advocate.md"
    if da.exists():
        try:
            da.unlink()
            return True
        except Exception:
            return False
    return False


def _add_adaptive_tier2_to_lead(project_root: Path, lead_name: str, subdomains: list[str]) -> bool:
    """Append adaptive Tier 2 domain-lead structure to an existing Lead's CLAUDE.md."""
    # Look for the Lead's CLAUDE.md in any project path that matches the lead name
    # Lead name is typically e.g. "api-lead" — find a CLAUDE.md whose containing dir matches.
    lead_path = None
    for f in project_root.rglob("CLAUDE.md"):
        if "node_modules" in f.parts:
            continue
        if f.parent.name.startswith(lead_name.replace("-lead", "")):
            lead_path = f
            break
    if lead_path is None:
        return False

    section = f"\n\n## Tier 2 — Adaptive depth (domain leads)\n\n"
    section += "This Lead's scope exceeded the adaptive-Tier-2 threshold. Sub-specialists are organized under Domain Leads:\n\n"
    for sub in subdomains:
        section += f"- **{sub}-domain-lead** (Tier 2a) — orchestrates specialists within `{sub}/`\n"
    section += "\nSee `~/.claude/skills/orchestrate/references/adaptive-tier2.md` for the pattern.\n"

    try:
        existing = lead_path.read_text(encoding="utf-8")
        if "Adaptive depth" not in existing:
            lead_path.write_text(existing + section, encoding="utf-8")
        return True
    except Exception:
        return False


def migrate(
    project_root: Path,
    profile: dict[str, Any],
    recommendations: dict[str, Any],
    user_choices: dict[str, Any],
) -> dict[str, Any]:
    """Migrate an existing project — back up, then generate additive content."""
    project_root = Path(project_root).resolve()

    # Phase 1: backup
    backup_dir = _create_backup(project_root)

    # Phase 2: retire legacy devils-advocate.md if user agreed
    retired = False
    if user_choices.get("replace_devils_advocate", True):
        retired = _retire_legacy_devils_advocate(project_root, backup_dir)

    # Phase 3: run generate (preserves existing CLAUDE.md, adds new pieces)
    gen_manifest = generate_orchestration(project_root, profile, recommendations, user_choices)

    # Phase 4: adaptive Tier 2 — add domain-lead structure to qualifying Leads
    adaptive_applied: list[str] = []
    for lead_name in user_choices.get("enable_adaptive_tier2", []):
        # Look up subdomains from profile
        for proj in profile.get("projects", []):
            if proj["name"] == lead_name or f"{proj['name']}-lead" == lead_name:
                subs = proj.get("subdomains", [])
                if subs and _add_adaptive_tier2_to_lead(project_root, lead_name + "-lead" if not lead_name.endswith("-lead") else lead_name, subs):
                    adaptive_applied.append(lead_name)
                break

    manifest: dict[str, Any] = {
        "mode": "migrate",
        "backup_dir": str(backup_dir),
        "legacy_devils_advocate_retired": retired,
        "adaptive_tier2_applied_to": adaptive_applied,
        **gen_manifest,
    }
    return manifest


if __name__ == "__main__":
    import json
    import sys
    from scripts.scan import scan_project
    from scripts.infer import infer_recommendations

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    profile = scan_project(target)
    recs = infer_recommendations(profile)
    choices = {
        "install_packs": recs["recommended_platform_packs"],
        "install_personas": [],
        "enable_adaptive_tier2": recs["adaptive_tier2_leads"],
        "replace_devils_advocate": True,
        "preserve_qa_lead": True,
    }
    manifest = migrate(target, profile, recs, choices)
    print(json.dumps(manifest, indent=2, default=str))
