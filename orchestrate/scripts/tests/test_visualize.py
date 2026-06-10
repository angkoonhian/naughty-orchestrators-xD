"""Tests for visualize.py — orchestration map generator."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import visualize as V


def test_generic_structure_without_config(tmp_path: Path):
    data = V.collect(tmp_path)
    assert data["installed"] is False
    ids = {n["id"] for n in data["nodes"]}
    assert "root" in ids and "da-lead" in ids and "synthesis-verifier" in ids
    assert "critic:security" in ids                       # 7 core critics always present
    assert sum(1 for n in data["nodes"] if n["kind"] == "critic") == 7
    assert any(n["kind"] == "validator" for n in data["nodes"])


def _write_cfg(tmp_path: Path) -> None:
    import yaml
    cfg = {
        "generated_at": "2026-06-10T00:00:00Z",
        "profile": {"shape": "monorepo", "projects": [
            {"name": "api", "framework": "nestjs", "file_count": 902, "complexity": "high",
             "subdomains": ["auth", "model", "services", "guards", "config", "libs"],
             "qa_scripts": {"lint": "eslint", "test": "jest"}},
            {"name": "web", "framework": "react", "file_count": 20, "complexity": "low", "subdomains": ["pages"]},
        ]},
        "platform_pack": {"name": "oxen-pack", "critics": ["jwt-auth", "multi-tenant"], "custom_critics": []},
        "adaptive_tier2": {"enabled_leads": ["api"], "file_count_threshold": 30, "subdomain_count_threshold": 5},
        "graph_integration": {"enabled": True, "snapshot": ".claude/orchestration.graph.json",
                              "hub_top_n": 8, "trust": {"raise_impact_on_hub": True, "cofire_blocking_when": "EXTRACTED"}},
    }
    d = tmp_path / ".claude"; d.mkdir(parents=True, exist_ok=True)
    (d / "orchestration.config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")


def test_live_overlay_with_config(tmp_path: Path):
    _write_cfg(tmp_path)
    data = V.collect(tmp_path)
    assert data["installed"] is True
    ids = {n["id"] for n in data["nodes"]}
    assert "lead:api" in ids and "lead:web" in ids              # leads from config
    assert "pack:jwt-auth" in ids                                # pack critic overlaid
    assert "t2:api" in ids and "t2:web" not in ids               # only the adaptive lead gets Tier-2
    assert data["graph"]["enabled"] is True
    assert data["counts"]["leads"] == 2


def test_render_html_is_self_contained(tmp_path: Path):
    _write_cfg(tmp_path)
    html = V.render_html(V.collect(tmp_path))
    assert "__DATA__" not in html and "__TITLE__" not in html    # placeholders substituted
    assert "<svg" in html and "const DATA =" in html
    assert "Budget engine" in html and "lead:api" in html
    assert "http://" not in html and "cdn" not in html.lower()   # no external deps


def test_budget_defaults_present_even_when_config_lacks_budget(tmp_path: Path):
    _write_cfg(tmp_path)  # this config has no `budget:` block
    data = V.collect(tmp_path)
    assert data["budget"]["defaults"]["HIGH"] == 500000          # falls back to budget.py defaults
    assert "unleashed" in data["budget"]
