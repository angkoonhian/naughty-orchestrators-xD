"""Security regression tests — locks in the fixes from the security audit."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import budget as B
from scripts import generate as G
from scripts import visualize as V


# ---------- visualize.py: HTML/JS injection (HIGH) ----------

def test_visualize_no_script_breakout_from_config():
    data = V.collect(Path("/__nonexistent__"))  # generic architecture
    data["nodes"].append({"id": 'lead:"><img src=x onerror=alert(1)>', "label": "</script><b>x</b>",
                          "kind": "lead", "role": "</script>", "file": "a.md", "extra": {}})
    data["title"] = "</script>evil"
    data["subtitle"] = "</title><img src=x onerror=alert(1)>"
    html = V.render_html(data)
    # the embedded JSON must not contain a raw script/title close from tainted data
    assert "</script><img" not in html
    assert "</title><img" not in html
    assert "</script><b>" not in html
    assert "\\u003c/script" in html              # escaped form is what's present
    # title/subtitle are HTML-escaped in their HTML contexts
    assert "&lt;/script&gt;evil" in html or "&lt;/title&gt;" in html


def test_visualize_collect_survives_malformed_config(tmp_path: Path):
    bad = {"profile": None, "platform_pack": None, "adaptive_tier2": "oops", "graph_integration": None}
    d = tmp_path / ".claude"; d.mkdir(parents=True)
    (d / "orchestration.config.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    data = V.collect(tmp_path)               # must not raise
    assert isinstance(data["nodes"], list) and data["installed"] is True
    V.render_html(data)                       # must not raise


def test_visualize_collect_nonstring_names(tmp_path: Path):
    cfg = {"profile": {"projects": [{"name": 123, "subdomains": [None, "a"], "qa_scripts": "notadict"},
                                    "not-a-dict"]}}
    d = tmp_path / ".claude"; d.mkdir(parents=True)
    (d / "orchestration.config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    V.render_html(V.collect(tmp_path))        # must not raise


# ---------- budget.py: robustness (MEDIUM/LOW) ----------

def test_budget_survives_malformed_config():
    cfg = {"defaults": {"HIGH": "notanumber"}, "max_request_budget": "oops"}
    r = B.resolve_budget("HIGH", None, cfg)
    assert r["tokens"] >= 0                    # fell back to a numeric default
    a = B.allocate("notanumber")               # must not raise
    assert a["implementation_floor"] == 0.0


# ---------- generate.py: path traversal + markdown injection (MEDIUM/LOW) ----------

def test_safe_segment_blocks_traversal():
    assert ".." not in G._safe_segment("../../../../tmp/evil")
    assert "/" not in G._safe_segment("@x/../../evil") and "\\" not in G._safe_segment("..\\..\\evil")
    assert G._safe_segment("") == "project"
    assert G._safe_segment("../") == "project"


def test_md_cell_neutralizes_injection():
    c = G._md_cell("a|b `code` \n newline {{skill_injection_table}}")
    assert "\n" not in c and "`" not in c and "{{" not in c
    assert "|" not in c.replace("\\|", "")     # pipes are escaped, not raw


def test_render_template_is_single_pass(tmp_path: Path):
    t = tmp_path / "t.md"; t.write_text("{{a}} {{b}} {{missing}}", encoding="utf-8")
    out = G._render_template(t, {"a": "{{b}}", "b": "SAFE"})
    assert out == "{{b}} SAFE {{missing}}"     # a's value not re-expanded; unknown token kept


def test_within_containment(tmp_path: Path):
    assert G._within(tmp_path, tmp_path / "sub" / "x") is True
    assert G._within(tmp_path, tmp_path / ".." / "evil") is False
