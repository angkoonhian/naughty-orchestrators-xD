"""Tests for skills_detect.py — installed-skill discovery + catalog resolution."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import skills_detect as S


def _make_skill(root: Path, name: str, frontmatter_name: str | None = None) -> None:
    d = root / ".claude" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    nm = frontmatter_name if frontmatter_name is not None else name
    (d / "SKILL.md").write_text(f"---\nname: {nm}\ndescription: test\n---\n# {name}\n", encoding="utf-8")


def test_frontmatter_name_parsed(tmp_path: Path):
    _make_skill(tmp_path, "myguide", frontmatter_name="my-guide")
    md = tmp_path / ".claude" / "skills" / "myguide" / "SKILL.md"
    assert S._frontmatter_name(md) == "my-guide"


def test_detect_finds_project_skill(tmp_path: Path):
    _make_skill(tmp_path, "brainstorming")
    detected = S.detect_skills(tmp_path)
    assert "brainstorming" in detected


def test_resolve_picks_detected_over_fallback():
    rows = dict(S.resolve_catalog({"brainstorming": "/x"}))
    assert rows["New feature / design"] == "`superpowers:brainstorming`"


def test_resolve_falls_back_to_builtin_when_skill_absent():
    # nothing installed → design falls back to the built-in feature-brain (in BUILTINS)
    rows = dict(S.resolve_catalog({}))
    assert rows["New feature / design"] == "`feature-brain`"


def test_resolve_inline_when_no_skill_and_no_builtin():
    rows = dict(S.resolve_catalog({}, catalog={"Custom task": ["superpowers:nonexistent", None]}))
    assert "inline" in rows["Custom task"]


def test_build_md_table_renders():
    md = S.build_skill_injection_md()
    assert "| Task type |" in md and "auto-detected" in md
