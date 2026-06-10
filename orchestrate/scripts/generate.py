"""Generate the orchestration files into a target project.

Writes:
  - <root>/CLAUDE.md (root orchestrator)
  - <root>/docs/agents/cross-cutting/{architect,da-lead,pre-impl-validator,post-impl-validator,qa-delegator}.md
  - <root>/docs/agents/da/core/*.md  (7 universal critics)
  - <root>/docs/agents/da/<pack>-pack/*.md  (for each confirmed pack)
  - <root>/docs/agents/validators/pre-impl/*.md  (6 validators)
  - <root>/docs/agents/validators/post-impl/*.md  (5 validators)
  - <root>/docs/agents/task-agents/*.md (4 task agents)
  - <root>/.claude/orchestration.config.yaml
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any
import yaml


def _safe_segment(s: str) -> str:
    """Reduce an untrusted value (e.g. a scanned package.json `name`) to ONE safe path
    segment — no traversal, no separators. Prevents writes escaping the project root."""
    base = Path(str(s)).name                       # drop any directory part / traversal
    cleaned = re.sub(r"[^A-Za-z0-9._@-]", "-", base).strip("-.")
    return cleaned or "project"


def _md_cell(s: Any, limit: int = 100) -> str:
    """Sanitize an untrusted value for a Markdown table cell in a generated CLAUDE.md
    (an agent-instruction file): no newlines, escaped pipes, no code-span/backtick or
    brace-token injection, bounded length."""
    t = str("" if s is None else s).replace("\r", " ").replace("\n", " ")
    t = t.replace("`", "").replace("|", "\\|").replace("{{", "{ {").replace("}}", "} }")
    return (t[:limit] + "…") if len(t) > limit else t


def _within(root: Path, target: Path) -> bool:
    """True iff target resolves inside root — used to refuse writes outside the project."""
    try:
        return str(target.resolve()).startswith(str(Path(root).resolve()))
    except Exception:
        return False
import datetime

SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSETS = SKILL_ROOT / "assets"
PACKS = SKILL_ROOT / "platform-packs"

GRAPH_BLOCK_START = "<!-- ORCHESTRATE:GRAPH:START -->"
GRAPH_BLOCK_END = "<!-- ORCHESTRATE:GRAPH:END -->"


def _copy_dir_contents(src: Path, dst: Path, allow_overwrite: bool = False) -> list[Path]:
    """Copy *.md files from src to dst. Returns list of files written."""
    dst.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if not src.exists():
        return written
    for f in sorted(src.glob("*.md")):
        target = dst / f.name
        if target.exists() and not allow_overwrite:
            continue
        shutil.copy2(f, target)
        written.append(target)
    return written


def _copy_file(src: Path, dst: Path, allow_overwrite: bool = False) -> Path | None:
    if not src.exists():
        return None
    if dst.exists() and not allow_overwrite:
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def _render_template(template_path: Path, substitutions: dict[str, str]) -> str:
    """Single-pass {{var}} substitution. Single-pass means a substituted value that itself
    contains a `{{token}}` is NOT re-expanded — closing a second-order injection where a
    scanned value pulls in other generated content. Unknown tokens are left intact."""
    content = template_path.read_text(encoding="utf-8")

    def _repl(m: re.Match) -> str:
        key = m.group(1)
        if key in substitutions:
            v = substitutions[key]
            return "" if v is None else str(v)
        return m.group(0)

    return re.sub(r"\{\{(\w+)\}\}", _repl, content)


def _build_classification_rules_section() -> str:
    rules_file = SKILL_ROOT / "references" / "classification-rules.md"
    if not rules_file.exists():
        return "See `~/.claude/skills/orchestrate/references/classification-rules.md` for the universal default rules."
    return f"See `~/.claude/skills/orchestrate/references/classification-rules.md` for the universal default rules. Default rules ship with the skill; project-specific bumps recorded in `.claude/orchestration.config.yaml`."


def _build_lead_dispatch_table(projects: list[dict]) -> str:
    rows = ["| Project Lead | Path | Scope |", "|---|---|---|"]
    for p in projects:
        rows.append(f"| `{_md_cell(p.get('name', '?'))}-lead` | `{_md_cell(p.get('path', ''))}/CLAUDE.md` | {_md_cell(p.get('framework', 'unknown'))} project |")
    return "\n".join(rows)


def _build_cross_cutting_table() -> str:
    return """| Agent | Location | Purpose |
|---|---|---|
| architect | `docs/agents/cross-cutting/architect.md` | Cross-repo / cross-module change manifests |
| da-lead | `docs/agents/cross-cutting/da-lead.md` | DA gate router |
| pre-impl-validator | `docs/agents/cross-cutting/pre-impl-validator.md` | Pre-impl gate router |
| post-impl-validator | `docs/agents/cross-cutting/post-impl-validator.md` | Post-impl gate router |
| qa-delegator | `docs/agents/cross-cutting/qa-delegator.md` | Wraps project QA infrastructure |"""


def _build_skill_injection_table() -> str:
    return """| Task type | Skills to inject |
|---|---|
| New feature / design | `superpowers:brainstorming` |
| Implementation from plan | `superpowers:subagent-driven-development` |
| Plan creation | `superpowers:writing-plans` |
| Bug fix / debug | `superpowers:systematic-debugging` |
| Refactor / tests | `superpowers:test-driven-development` |
| UI redesign | `ui-ux-pro-max:ui-ux-pro-max` |"""


def _skill_injection_table(project_root: Path) -> str:
    """Dynamic, auto-detected skill-injection table (only skills actually installed,
    with graceful fallbacks). Falls back to the static table if detection fails."""
    try:
        from scripts import skills_detect
        return skills_detect.build_skill_injection_md(project_root)
    except Exception:
        return _build_skill_injection_table()


def _capabilities_table(project_root: Path) -> str:
    """Capability-aware dispatch: route orchestration roles to installed plugin specialist
    sub-agents (+ surface MCP tools). Empty string if detection is unavailable."""
    try:
        from scripts import capabilities_detect
        return capabilities_detect.build_capabilities_md(project_root)
    except Exception:
        return ""


def _render_qa_delegator(qa_wiring: dict[str, Any], qa_lead_present: bool) -> str:
    template = (ASSETS / "cross-cutting" / "qa-delegator.template.md").read_text(encoding="utf-8")
    commands = qa_wiring.get("commands", {}) or {}
    subs = {
        "qa_lead_present": "true" if qa_lead_present else "false",
        "qa_e2e_cmd": commands.get("test_e2e") or "",
        "qa_integration_cmd": commands.get("test_integration") or "",
        "qa_unit_cmd": commands.get("test") or "",
        "qa_typecheck_cmd": commands.get("typecheck") or "",
        "qa_lint_cmd": commands.get("lint") or "",
    }
    for k, v in subs.items():
        template = template.replace(f"{{{{{k}}}}}", v)
    return template


def _render_graph_block(snapshot: dict[str, Any] | None) -> str:
    """Render the runtime graph-aware impact & routing guidance for CLAUDE.md.

    When `snapshot` is None the integration is enabled but not yet built — render
    a placeholder pointing at `/orchestrate refresh-graph`.
    """
    lines = [
        GRAPH_BLOCK_START,
        "",
        "## Graph-Aware Impact & Routing (graphify integration)",
        "",
        "This project has the graphify integration **enabled**. The orchestrator reads the",
        "baked snapshot at `.claude/orchestration.graph.json` during **ASSESS IMPACT** and",
        "**ROUTE**. This block is managed by the orchestrate skill — edits between the markers",
        "are overwritten on the next `/orchestrate refresh-graph`.",
        "",
    ]

    if snapshot is None or not snapshot.get("projects"):
        lines += [
            "**Status: awaiting first build.** No snapshot present yet. Run",
            "`/orchestrate refresh-graph` to build per-project AST graphs + the seam graph and",
            "bake the snapshot. Until then, impact/routing fall back to the heuristic rules.",
            "",
            GRAPH_BLOCK_END,
        ]
        return "\n".join(lines)

    lines += [
        f"**Snapshot built:** {snapshot.get('built_at', 'unknown')}",
        "",
        "**How to use it each turn:**",
        "1. Read `.claude/orchestration.graph.json`. If absent/disabled, use the heuristic rules only.",
        "2. If the task names specific files/modules, optionally run "
        "`python ~/.claude/skills/orchestrate/scripts/blast_radius.py <project>/graphify-out/graph.json \"<target>\"` "
        "for precise dependents.",
        "3. **Trust model:** a touched hub (EXTRACTED) or a large blast radius raises impact one "
        "tier (never above CRITICAL, never below the rule floor). A `co_fire` hit adds the coupled "
        "project's Lead — blocking co-dispatch if EXTRACTED, advisory \"graph consideration\" if INFERRED.",
        "4. Log every graph-driven adjustment with its provenance in the synthesis.",
        "",
        "**Cross-project co-fire map (seam graph):**",
    ]
    co_fire = snapshot.get("co_fire", {}) or {}
    if co_fire:
        lines.append("| Touching this project | Also dispatch Lead(s) for |")
        lines.append("|---|---|")
        for proj in sorted(co_fire):
            lines.append(f"| `{proj}` | {', '.join(f'`{c}`' for c in co_fire[proj])} |")
    else:
        lines.append("_(no cross-project contract edges detected in the seam graph)_")
    lines.append("")

    lines.append("**Per-project hubs (touching these bumps impact):**")
    projects = snapshot.get("projects", {}) or {}
    any_hub = False
    for name in sorted(projects):
        hubs = projects[name].get("hubs", []) or []
        if not hubs:
            continue
        any_hub = True
        hub_labels = ", ".join(f"`{h.get('label')}` ({h.get('in_degree')})" for h in hubs[:6])
        lines.append(f"- **{name}**: {hub_labels}")
    if not any_hub:
        lines.append("_(no hubs detected yet — per-project graphs may be unbuilt)_")
    lines += ["", GRAPH_BLOCK_END]
    return "\n".join(lines)


def _inject_managed_block(path: Path, block: str) -> str:
    """Idempotently insert/replace the graph managed block in a file.

    Returns one of: created | replaced | appended.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block + "\n", encoding="utf-8")
        return "created"
    content = path.read_text(encoding="utf-8")
    if GRAPH_BLOCK_START in content and GRAPH_BLOCK_END in content:
        pre = content.split(GRAPH_BLOCK_START)[0]
        post = content.split(GRAPH_BLOCK_END, 1)[1]
        path.write_text(pre + block + post, encoding="utf-8")
        return "replaced"
    sep = "" if content.endswith("\n\n") else ("\n" if content.endswith("\n") else "\n\n")
    path.write_text(content + sep + "\n" + block + "\n", encoding="utf-8")
    return "appended"


def wire_graph_integration(
    project_root: Path,
    *,
    enabled: bool,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn graph integration on/off for a project: update config + manage the
    CLAUDE.md block. Safe to call repeatedly (idempotent). When `enabled` is
    False the managed block is removed if present and config is updated.
    """
    project_root = Path(project_root).resolve()
    result: dict[str, Any] = {"enabled": enabled}

    # 1. Update config graph_integration block (preserve the rest of the config).
    config_path = project_root / ".claude" / "orchestration.config.yaml"
    config: dict[str, Any] = {}
    if config_path.exists():
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            config = {}
    gi = config.get("graph_integration") or {}
    gi.update(
        {
            "enabled": enabled,
            "snapshot": ".claude/orchestration.graph.json",
            "per_project_graphs": True,
            "seam_graph": True,
            "agent_grounding": gi.get("agent_grounding", False),
            "mcp_live": gi.get("mcp_live", False),
            "hub_top_n": gi.get("hub_top_n", 8),
            "trust": gi.get("trust", {"raise_impact_on_hub": True, "cofire_blocking_when": "EXTRACTED"}),
        }
    )
    config["graph_integration"] = gi
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False, default_flow_style=False), encoding="utf-8")
    result["config"] = str(config_path)

    # 2. Manage the CLAUDE.md block.
    root_claude = project_root / "CLAUDE.md"
    if enabled:
        block = _render_graph_block(snapshot)
        result["claude_md"] = _inject_managed_block(root_claude, block)
    elif root_claude.exists():
        content = root_claude.read_text(encoding="utf-8")
        if GRAPH_BLOCK_START in content and GRAPH_BLOCK_END in content:
            pre = content.split(GRAPH_BLOCK_START)[0].rstrip("\n")
            post = content.split(GRAPH_BLOCK_END, 1)[1].lstrip("\n")
            root_claude.write_text((pre + "\n" + post).strip() + "\n", encoding="utf-8")
            result["claude_md"] = "block_removed"
    return result


def generate_orchestration(
    project_root: Path,
    profile: dict[str, Any],
    recommendations: dict[str, Any],
    user_choices: dict[str, Any],
) -> dict[str, list[str]]:
    """Generate orchestration files. Returns a manifest of files created/modified."""
    project_root = Path(project_root).resolve()
    manifest: dict[str, list[str]] = {"created": [], "modified": [], "backed_up": []}

    docs_agents = project_root / "docs" / "agents"

    # 1. Cross-cutting agents (preserve existing architect.md if present)
    cc_dst = docs_agents / "cross-cutting"
    cc_dst.mkdir(parents=True, exist_ok=True)

    for name in ["architect.md", "da-lead.md", "pre-impl-validator.md", "post-impl-validator.md"]:
        target = cc_dst / name
        if not target.exists():
            shutil.copy2(ASSETS / "cross-cutting" / name, target)
            manifest["created"].append(str(target))

    # qa-delegator: render template
    qa_lead_present = (docs_agents / "qa" / "lead.md").exists()
    qa_delegator_content = _render_qa_delegator(recommendations.get("qa_wiring", {}), qa_lead_present)
    qa_delegator_path = cc_dst / "qa-delegator.md"
    if not qa_delegator_path.exists():
        qa_delegator_path.write_text(qa_delegator_content, encoding="utf-8")
        manifest["created"].append(str(qa_delegator_path))

    # 2. Universal core DA critics
    core_written = _copy_dir_contents(ASSETS / "core-critics", docs_agents / "da" / "core")
    manifest["created"].extend(str(p) for p in core_written)

    # 3. Platform-pack critics — for each confirmed pack
    _raw_slug = user_choices.get("project_pack_slug") or (profile.get("projects") or [{}])[0].get("name") or "project"
    pack_slug = _safe_segment(str(_raw_slug)) + "-pack"   # one safe path segment — no traversal
    pack_dest = docs_agents / "da" / pack_slug
    for pack_name in user_choices.get("install_packs", []):
        pack_dir = PACKS / pack_name
        if pack_dir.exists():
            for f in pack_dir.glob("*.md"):
                target = pack_dest / f.name
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    manifest["created"].append(str(target))

    # 4. Pre-impl validators
    pre_written = _copy_dir_contents(ASSETS / "pre-impl-validators", docs_agents / "validators" / "pre-impl")
    manifest["created"].extend(str(p) for p in pre_written)

    # 5. Post-impl validators
    post_written = _copy_dir_contents(ASSETS / "post-impl-validators", docs_agents / "validators" / "post-impl")
    manifest["created"].extend(str(p) for p in post_written)

    # 6. Task agents (universal)
    task_written = _copy_dir_contents(ASSETS / "task-agents", docs_agents / "task-agents")
    manifest["created"].extend(str(p) for p in task_written)

    # 7. Root CLAUDE.md — only created if absent (Migrate mode preserves existing)
    root_claude = project_root / "CLAUDE.md"
    if not root_claude.exists():
        template = ASSETS / "tier0-root.template.md"
        substitutions = {
            "project_name": project_root.name,
            "project_description": f"Auto-generated for {project_root.name}",
            "repository_structure": "(scan output)",
            "impact_classification_rules": _build_classification_rules_section(),
            "lead_dispatch_table": _build_lead_dispatch_table(profile.get("projects", [])),
            "cross_cutting_table": _build_cross_cutting_table(),
            "migration_writer_row": "| migration-writer | `docs/agents/task-agents/migration-writer.md` | DB migration writing |" if user_choices.get("install_migration_writer", True) else "",
            "persona_table": "(no personas installed; add via `/orchestrate add-persona`)",
            "skill_injection_table": _skill_injection_table(project_root),
            "capabilities_table": _capabilities_table(project_root),
            "tech_stack": "(detected by bootstrap)",
            "code_style": "(per project)",
            "commands": "(per project)",
        }
        rendered = _render_template(template, substitutions)
        root_claude.write_text(rendered, encoding="utf-8")
        manifest["created"].append(str(root_claude))

    # 8. Per-project Lead CLAUDE.md — only if project's CLAUDE.md doesn't exist
    lead_template_path = ASSETS / "lead.template.md"
    for proj in profile.get("projects", []):
        if not isinstance(proj, dict) or not proj.get("path"):
            continue
        proj_path = Path(str(proj["path"]))
        if not _within(project_root, proj_path):
            continue  # refuse to write a CLAUDE.md outside the project root (tampered config)
        lead_md = proj_path / "CLAUDE.md"
        if lead_md.exists():
            continue
        subs = {
            "lead_name": f"{_md_cell(proj.get('name', '?'))}-lead",
            "project_name": _md_cell(proj.get("name", "?")),
            "project_description": f"{_md_cell(proj.get('framework', 'unknown'))} project at `{_md_cell(proj.get('path', ''))}`",
            "lead_scope": f"Code under `{_md_cell(proj.get('path', ''))}`",
            "tech_stack": _md_cell(proj.get("framework", "unknown")),
            "sub_specialists": "(to be defined — add via /orchestrate add-specialist)",
            "dispatch_rows": "| (pattern) | (specialist) | (skill) |",
            "patterns": "(per project conventions)",
            "constraints": "Stay within this Lead's scope; escalate cross-domain work.",
        }
        rendered = _render_template(lead_template_path, subs)
        try:
            lead_md.write_text(rendered, encoding="utf-8")
            manifest["created"].append(str(lead_md))
        except Exception:
            continue  # may not have write access on the path

    # 9. Write skill state
    config_path = project_root / ".claude" / "orchestration.config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_data = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "profile": profile,
        "recommendations": recommendations,
        "user_choices": user_choices,
        "platform_pack": {
            "name": pack_slug,
            "critics": user_choices.get("install_packs", []),
            "custom_critics": [],
            "pre_impl_validators": [],
            "post_impl_validators": [],
        },
        "adaptive_tier2": {
            "enabled_leads": user_choices.get("enable_adaptive_tier2", []),
            "file_count_threshold": 30,
            "subdomain_count_threshold": 5,
        },
        "graph_integration": user_choices.get("graph_integration") or {"enabled": False},
        "budget": user_choices.get("budget") or {
            "mode": "budgeted",  # budgeted | unlimited (set 'unlimited' for MAX-plan users)
            "defaults": {"LOW": 0, "MEDIUM": 150000, "HIGH": 500000, "CRITICAL": 1200000},
            "max_request_budget": 2000000,
            "overrides": {"cheap": 0.4, "thorough": 3.0},
            "deepen_threshold": 0.7,
            "deepen_cost": 40000,
            "verify_cost": 25000,
            "workflow_threshold": 12,
            "force_deepen_dimensions": ["security", "auth", "data-loss", "migrations", "cross-tenant"],
            "unleashed": {"max_rounds": 5, "convergence_clean_rounds": 2, "agent_ceiling": 800},
            "models": {"mechanical": "haiku", "judgment": "opus"},
        },
    }
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False, default_flow_style=False), encoding="utf-8")
    manifest["created"].append(str(config_path))

    # Optional: wire the graph managed block when the user opted in at bootstrap.
    gi = config_data["graph_integration"]
    if isinstance(gi, dict) and gi.get("enabled"):
        snap_path = project_root / ".claude" / "orchestration.graph.json"
        snapshot = None
        if snap_path.exists():
            import json as _json
            try:
                snapshot = _json.loads(snap_path.read_text(encoding="utf-8"))
            except Exception:
                snapshot = None
        wire_result = wire_graph_integration(project_root, enabled=True, snapshot=snapshot)
        if wire_result.get("claude_md") in ("created", "appended", "replaced"):
            manifest["modified"].append(str(project_root / "CLAUDE.md"))

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
    }
    manifest = generate_orchestration(target, profile, recs, choices)
    print(json.dumps(manifest, indent=2, default=str))
