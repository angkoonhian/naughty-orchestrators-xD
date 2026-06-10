"""skills_detect — discover which "thinking" skills are actually installed, and
resolve the orchestrate task-type → skill mapping against them.

The generated CLAUDE.md must not tell agents to invoke skills that aren't present
(e.g. `superpowers:brainstorming` on a machine without superpowers). This scans the
real skill locations, then resolves a known-skills catalog (task-type → ordered
preference + fallbacks) against what's available, so the skill-injection table is
DYNAMIC and degrades gracefully (built-in skill or plain inline guidance).

Pure stdlib. Detection is best-effort by SKILL.md frontmatter `name:`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

HOME = Path.home()

# Where skills live: plugin caches/marketplaces, user skills, project skills.
def _skill_md_globs(project_root: Path | None) -> list[tuple[Path, str]]:
    roots: list[tuple[Path, str]] = [
        (HOME / ".claude" / "plugins", "**/skills/*/SKILL.md"),
        (HOME / ".claude" / "plugins", "**/.claude/skills/*/SKILL.md"),
        (HOME / ".claude" / "skills", "*/SKILL.md"),
    ]
    if project_root:
        roots.append((Path(project_root) / ".claude" / "skills", "*/SKILL.md"))
    return roots


def _frontmatter_name(md_path: Path) -> str | None:
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    m = re.search(r"^---\s*$(.*?)^---\s*$", text, re.S | re.M)
    block = m.group(1) if m else text[:400]
    nm = re.search(r"^\s*name\s*:\s*(.+?)\s*$", block, re.M)
    if nm:
        return nm.group(1).strip().strip("'\"").split()[0]
    return md_path.parent.name  # fall back to the skill directory name


def detect_skills(project_root: Path | str | None = None) -> dict[str, str]:
    """Return { base_skill_name: source_path } for every installed skill found.

    `base_skill_name` is the SKILL.md frontmatter `name` (or dir name) — the part you
    match a `plugin:skill` candidate's suffix against.
    """
    found: dict[str, str] = {}
    for root, pattern in _skill_md_globs(Path(project_root) if project_root else None):
        if not root.exists():
            continue
        for md in root.glob(pattern):
            if "node_modules" in md.parts:
                continue
            name = _frontmatter_name(md)
            if name and name not in found:
                found[name] = str(md.parent)
    return found


# Built-in skills/sub-agents the harness provides (can't be detected on disk; assume present).
BUILTINS = {"feature-brain", "Plan", "frontend-design", "code-reviewer", "react-ui-expert"}

# task-type → ordered preference. `None` = no skill (inline guidance). A candidate is
# `plugin:skill` or a bare built-in name; resolution matches on the suffix after ':'.
SKILL_CATALOG: dict[str, list[str | None]] = {
    "New feature / design": ["superpowers:brainstorming", "feature-brain", None],
    "Writing an implementation plan": ["superpowers:writing-plans", "Plan", None],
    "Implementation from a plan": ["superpowers:subagent-driven-development", "superpowers:executing-plans", None],
    "Bug fix / debugging": ["superpowers:systematic-debugging", None],
    "Refactor / any change touching tests": ["superpowers:test-driven-development", None],
    "UI / UX work": ["ui-ux-pro-max:ui-ux-pro-max", "frontend-design", None],
    "Code review": ["superpowers:requesting-code-review", "code-reviewer", None],
    "Before declaring done": ["superpowers:verification-before-completion", None],
}


def _suffix(candidate: str) -> str:
    return candidate.split(":", 1)[1] if ":" in candidate else candidate


def resolve_catalog(detected: dict[str, str], catalog: dict | None = None) -> list[tuple[str, str]]:
    """For each task-type, pick the first available candidate (installed skill or built-in),
    else 'inline'. Returns [(task_type, chosen)]."""
    catalog = catalog or SKILL_CATALOG
    avail = set(detected.keys())
    rows: list[tuple[str, str]] = []
    for task, candidates in catalog.items():
        chosen = "inline (no skill installed — use your own judgment)"
        for c in candidates:
            if c is None:
                break
            suf = _suffix(c)
            if suf in avail or c in BUILTINS or suf in BUILTINS:
                chosen = f"`{c}`"
                break
        rows.append((task, chosen))
    return rows


def build_skill_injection_md(project_root: Path | str | None = None) -> str:
    """Render the dynamic skill-injection table for the generated CLAUDE.md."""
    detected = detect_skills(project_root)
    rows = resolve_catalog(detected)
    out = ["| Task type | Skill to inject (auto-detected) |", "|---|---|"]
    for task, chosen in rows:
        out.append(f"| {task} | {chosen} |")
    note = (
        "\n_Detected at bootstrap from `~/.claude/plugins`, `~/.claude/skills`, and "
        "`./.claude/skills`. Skills not installed fall back to a built-in or to plain inline "
        "guidance — agents are never told to invoke a skill that isn't present. Re-run "
        "`/orchestrate update` after installing new skills to refresh this table._"
    )
    return "\n".join(out) + "\n" + note


if __name__ == "__main__":
    import json
    import sys

    root = sys.argv[1] if len(sys.argv) > 1 else None
    det = detect_skills(root)
    print("DETECTED:", json.dumps(sorted(det.keys()), indent=2))
    print("\nINJECTION TABLE:\n" + build_skill_injection_md(root))
