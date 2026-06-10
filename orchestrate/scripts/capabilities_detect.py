"""capabilities_detect — discover the installed plugin surface the orchestrator can
LEVERAGE beyond skills: dispatchable **sub-agents** and **MCP tool servers**.

Companion to `skills_detect` (thinking skills). Auto-route catalog maps orchestration
roles to installed specialist sub-agents — so the orchestrator conducts the user's real
specialists (security-auditor, code-architect, test-engineer, …) instead of always
spawning generic agents — falling back to a generic agent when none is installed.

Pure stdlib. Detection means installed/available; MCP servers may still need connecting.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HOME = Path.home()

_VERSION_RE = re.compile(r"^(?:unknown|v?[0-9][0-9.]*)$", re.I)


# ----------------------------------------------------------------- sub-agents

def _agent_globs(project_root: Path | None) -> list[tuple[Path, str]]:
    roots: list[tuple[Path, str]] = [
        (HOME / ".claude" / "plugins", "**/agents/*.md"),
        (HOME / ".claude" / "agents", "*.md"),
    ]
    if project_root:
        roots.append((Path(project_root) / ".claude" / "agents", "*.md"))
    return roots


def _frontmatter(md_path: Path) -> tuple[str, str]:
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return md_path.stem, ""
    m = re.search(r"^---\s*$(.*?)^---\s*$", text, re.S | re.M)
    block = m.group(1) if m else text[:600]
    nm = re.search(r"^\s*name\s*:\s*(.+?)\s*$", block, re.M)
    name = nm.group(1).strip().strip("'\"").split()[0] if nm else md_path.stem
    ds = re.search(r"^\s*description\s*:\s*(.*)$", block, re.M)
    desc = (ds.group(1).strip().strip("'\"") if ds else "")
    if desc in ("", "|", ">", "|-", ">-"):                 # block scalar → first following line
        after = block[ds.end():] if ds else ""
        for line in after.splitlines():
            if line.strip():
                desc = line.strip()
                break
    return name, desc[:160]


def _plugin_of(md_path: Path) -> str:
    """Best-effort plugin name for an agent path (the dir above agents/, skipping version dirs)."""
    parts = md_path.parts
    try:
        i = len(parts) - 1 - parts[::-1].index("agents")
    except ValueError:
        return ""
    for seg in reversed(parts[:i]):
        if not _VERSION_RE.match(seg) and seg not in ("plugins", "cache", "marketplaces", ".claude"):
            return seg
    return ""


def detect_agents(project_root: Path | str | None = None) -> dict[str, dict[str, str]]:
    """Return { agent_name: {description, plugin, source} } for installed sub-agents."""
    found: dict[str, dict[str, str]] = {}
    for root, pattern in _agent_globs(Path(project_root) if project_root else None):
        if not root.exists():
            continue
        for md in root.glob(pattern):
            if "node_modules" in md.parts:
                continue
            name, desc = _frontmatter(md)
            if name and name not in found:
                found[name] = {"description": desc, "plugin": _plugin_of(md), "source": str(md.parent)}
    return found


# ----------------------------------------------------------------- MCP servers

def detect_mcp(project_root: Path | str | None = None) -> dict[str, dict[str, str]]:
    """Return { server_name: {source} } for MCP servers shipped by plugins / configured
    for the user or project. Installed/available — may still need connecting."""
    servers: dict[str, dict[str, str]] = {}
    files: list[Path] = []
    pdir = HOME / ".claude" / "plugins"
    if pdir.exists():
        files += list(pdir.glob("**/.mcp.json"))
    for extra in (HOME / ".claude" / ".mcp.json", HOME / ".mcp.json",
                  (Path(project_root) / ".mcp.json") if project_root else None):
        if extra and extra.exists():
            files.append(extra)
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        srv = data.get("mcpServers") if isinstance(data, dict) else None
        if isinstance(srv, dict) and srv:
            for name in srv:
                servers.setdefault(str(name), {"source": str(f)})
        else:
            # derive the server/plugin name from the path: first ancestor dir (above the
            # filename) that isn't a version or wrapper dir.
            name = ""
            for seg in reversed(f.parts[:-1]):
                if not _VERSION_RE.match(seg) and seg not in (
                        "plugins", "cache", "marketplaces", ".claude", "external_plugins"):
                    name = seg
                    break
            if name:
                servers.setdefault(name, {"source": str(f)})
    return servers


# ----------------------------------------------------------------- catalogs

# Orchestration role → preferred installed specialist sub-agents (first match wins).
SPECIALIST_CATALOG: dict[str, list[str]] = {
    "architect (cross-project planning)": ["code-architect"],
    "understand / code exploration": ["code-explorer"],
    "DA · security deepener": ["security-auditor"],
    "DA · failure-mode deepener": ["silent-failure-hunter"],
    "DA · tech-debt deepener": ["code-simplifier"],
    "DA · consistency / types deepener": ["type-design-analyzer"],
    "DA · performance / architecture deepener": ["architecture-critic"],
    "post-impl · regression / tests": ["test-engineer", "pr-test-analyzer"],
    "post-impl · code review": ["code-reviewer"],
    "refactor / legacy analysis": ["legacy-analyst", "business-rules-extractor"],
}

# MCP server → where the orchestrator can use it.
MCP_USES: dict[str, str] = {
    "github": "branch finalization / PR prep",
    "playwright": "post-impl smoke-test / UI verification",
    "notion": "spec & docs capture",
    "context7": "library / API docs lookup during design",
    "firebase": "backend / data operations",
    "asana": "task / project sync",
    "railway": "deploy / infra operations",
}


def resolve_specialists(detected_agents: dict, catalog: dict | None = None) -> list[tuple[str, str | None]]:
    """[(role, chosen_agent_or_None)] — None means fall back to a generic agent."""
    catalog = catalog or SPECIALIST_CATALOG
    avail = set(detected_agents or {})
    return [(role, next((a for a in prefs if a in avail), None)) for role, prefs in catalog.items()]


def build_capabilities_md(project_root: Path | str | None = None) -> str:
    """Render the capability-aware-dispatch section for the generated CLAUDE.md."""
    agents = detect_agents(project_root)
    mcp = detect_mcp(project_root)
    rows = resolve_specialists(agents)
    out = [
        "### Capability-aware dispatch (auto-detected)",
        "",
        "Route these roles to installed **specialist sub-agents** via the Agent tool's `agentType` "
        "(fall back to a generic agent when none is installed):",
        "",
        "| Orchestration role | Specialist `agentType` | Plugin |",
        "|---|---|---|",
    ]
    for role, chosen in rows:
        plugin = agents.get(chosen, {}).get("plugin", "") if chosen else ""
        out.append(f"| {role} | {'`' + chosen + '`' if chosen else '_(generic)_'} | {plugin or '—'} |")
    installed = sorted(mcp)
    if installed:
        out += ["", "**Available MCP tools** (use where relevant; connect if not already):"]
        for n in installed[:14]:
            use = MCP_USES.get(n, "")
            out.append(f"- `{n}`" + (f" — {use}" if use else ""))
    out += ["", "_Auto-detected at bootstrap from `~/.claude/plugins` + `~/.claude/agents`. "
            "Re-run `/orchestrate update` after installing plugins._"]
    return "\n".join(out)


if __name__ == "__main__":
    import sys

    root = sys.argv[1] if len(sys.argv) > 1 else None
    ag = detect_agents(root)
    mc = detect_mcp(root)
    print(f"AGENTS ({len(ag)}):", json.dumps(sorted(ag.keys()), indent=2))
    print(f"\nMCP ({len(mc)}):", json.dumps(sorted(mc.keys()), indent=2))
    print("\n" + build_capabilities_md(root))
