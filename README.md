# Claude Code Skills

Custom [Claude Code](https://claude.com/claude-code) skills, version-controlled so they can be
shared and replicated across machines. These live in `~/.claude/skills/`.

## Skills

- **orchestrate** — bootstraps and operates a multi-tier agent orchestration system in any
  codebase (scan → infer → generate): a 4-tier hierarchy, a Devil's-Advocate review gate,
  pre/post-implementation validation gates with smart routing, platform-packs, and an optional
  **graphify** knowledge-graph integration (blast-radius-aware impact & routing).
- **graphify** — turns any folder (code, docs, papers, images) into a navigable knowledge graph
  with community detection and an honest EXTRACTED/INFERRED audit trail.

## Replicate on another machine

```bash
git clone <this-repo-url> ~/.claude/skills
```

If `~/.claude/skills` already exists, clone elsewhere and copy the `orchestrate/` and `graphify/`
folders into it.

### Runtime dependency
The graphify skill drives the `graphifyy` Python package:

```bash
pip install graphifyy
```

## Layout
- `orchestrate/` — `SKILL.md`, `scripts/` (scan/infer/generate + graph_bake/blast_radius/graph_build),
  `assets/`, `platform-packs/`, `references/`
- `graphify/` — `SKILL.md`
