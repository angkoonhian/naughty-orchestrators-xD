"""Tests for capabilities_detect.py — plugin sub-agent + MCP discovery and routing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import capabilities_detect as C


def _agent(root: Path, name: str, desc: str = "does things") -> None:
    d = root / ".claude" / "agents"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\n", encoding="utf-8")


# ---- sub-agents ----

def test_detect_project_agent(tmp_path: Path):
    # unique name so it can't collide with a real installed agent (dedup is first-wins)
    _agent(tmp_path, "zzz-proj-specialist", "find vulnerabilities")
    a = C.detect_agents(tmp_path)
    assert "zzz-proj-specialist" in a and "vulnerabilities" in a["zzz-proj-specialist"]["description"]


def test_frontmatter_block_scalar_description(tmp_path: Path):
    d = tmp_path / ".claude" / "agents"; d.mkdir(parents=True)
    (d / "x.md").write_text("---\nname: x\ndescription: |\n  Use this for thing Y\n---\n", encoding="utf-8")
    name, desc = C._frontmatter(d / "x.md")
    assert name == "x" and "Use this for thing Y" in desc


def test_plugin_of_skips_version_dirs():
    p = Path("/r/.claude/plugins/cache/claude-plugins-official/feature-dev/unknown/agents/code-architect.md")
    assert C._plugin_of(p) == "feature-dev"


# ---- routing catalog ----

def test_resolve_specialists_matches_and_falls_back():
    rows = dict(C.resolve_specialists({"security-auditor": {}, "code-architect": {}}))
    assert rows["DA · security deepener"] == "security-auditor"
    assert rows["architect (cross-project planning)"] == "code-architect"
    assert rows["post-impl · code review"] is None        # not installed → generic fallback


def test_resolve_uses_preference_order():
    # test-engineer is preferred over pr-test-analyzer for the regression role
    rows = dict(C.resolve_specialists({"pr-test-analyzer": {}}))
    assert rows["post-impl · regression / tests"] == "pr-test-analyzer"
    rows2 = dict(C.resolve_specialists({"test-engineer": {}, "pr-test-analyzer": {}}))
    assert rows2["post-impl · regression / tests"] == "test-engineer"


# ---- MCP ----

def test_detect_mcp_project_and_no_literal(tmp_path: Path):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"github": {}, "playwright": {}}}), encoding="utf-8")
    m = C.detect_mcp(tmp_path)
    assert "github" in m and "playwright" in m
    assert ".mcp.json" not in m                            # regression: filename must not leak as a server


# ---- rendered section ----

def test_build_capabilities_md(tmp_path: Path):
    _agent(tmp_path, "code-architect")
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"github": {}}}), encoding="utf-8")
    md = C.build_capabilities_md(tmp_path)
    assert "Capability-aware dispatch" in md
    assert "`code-architect`" in md                        # matched specialist rendered as agentType
    assert "github" in md                                   # MCP surfaced
    assert ".mcp.json" not in md
