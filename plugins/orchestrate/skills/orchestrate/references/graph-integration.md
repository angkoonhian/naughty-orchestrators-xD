# Graph Integration (graphify) — Reference

Optional integration that lets orchestrate consume a [graphify](https://github.com/safishamsi/graphify)
knowledge graph to make impact assessment, routing, and Tier-2 boundaries structure-aware
instead of heuristic-only. **Strictly additive and optional** — when disabled or when no
snapshot exists, orchestrate behaves exactly as it did before.

## The three-layer graph contract

| Layer | Location | Built by | Refresh | Cost |
|---|---|---|---|---|
| Per-project graphs | `<project>/graphify-out/graph.json` | graphify **AST path** (`--directed`, no LLM) | git post-commit hook (free) | **free** |
| Seam graph | `docs/agents/graph/seam/graphify-out/graph.json` | targeted **semantic** extraction over a curated contract corpus | `/orchestrate refresh-graph` | bounded (small corpus) |
| Orchestration snapshot | `.claude/orchestration.graph.json` | `scripts/graph_bake.py` (stdlib only) | every bootstrap/update + refresh | free (pure-python) |

Only the **snapshot** is read at runtime. Per-project and seam graphs are inputs to the bake.

## Snapshot schema (`.claude/orchestration.graph.json`)

```json
{
  "schema_version": 1,
  "built_at": "<iso8601>",
  "graph_integration": "enabled|disabled",
  "source": { "per_project_graphs": {"<project>": "<path>"}, "seam_graph": "<path|null>" },
  "projects": {
    "<project>": {
      "node_count": 0, "edge_count": 0, "community_count": 0,
      "complexity": "high|medium|low",
      "metrics": {"hub_count": 0, "modularity": null},
      "communities": [{"id":"c0","label":"Auth","size":0,"members":[],"provenance":"graphify"}],
      "hubs": [{"id":"...","label":"...","source_file":"...","in_degree":0,"degree":0,"provenance":"EXTRACTED|INFERRED"}]
    }
  },
  "seam_map": [{"from_project":"...","from":"...","to_project":"...","to":"...","relation":"shares_data_with","confidence":"INFERRED","confidence_score":0.85,"provenance":"INFERRED"}],
  "co_fire": {"<project>": ["<project>"]}
}
```

- **hubs** are ranked by fan-in (in-degree); high fan-in = touching it ripples widely.
- **communities** come from graphify's clustering (`node.community`); used to name Tier-2 domain-lead boundaries.
- **seam_map / co_fire** capture cross-project contract coupling (API route/DTO ↔ frontend consumer) — the coupling AST cannot see.

## Trust model (honest by construction)

Every graph fact carries `provenance`:
- **EXTRACTED** (AST / structural): may **raise** impact and **add** Leads autonomously (blocking co-dispatch).
- **INFERRED** (semantic / seam): **advisory only** — surfaced as a "graph consideration," never a silent gate; co-dispatch is advisory.
- The graph **never lowers** impact below the rule-based floor in `classification-rules.md`.
- Every graph-driven adjustment is logged with its provenance in the synthesis.

Configured under `graph_integration.trust` in `.claude/orchestration.config.yaml`
(`raise_impact_on_hub`, `cofire_blocking_when`).

## Runtime usage (Tier 0)

During **ASSESS IMPACT** and **ROUTE**, the orchestrator (per the managed block in the
generated `CLAUDE.md`):

1. Reads `.claude/orchestration.graph.json`. Absent/disabled → heuristic rules only.
2. Maps the task to project(s); reads their `hubs` + `co_fire`.
3. For a task naming specific files/modules, optionally escalates to:
   ```
   python scripts/blast_radius.py <project>/graphify-out/graph.json "<target>"
   ```
   → dependents (≤3 hops), `is_hub`, `hub_rank`.
4. Applies the trust model: hub hit / large blast radius → +1 impact tier; `co_fire` hit → add the coupled Lead.

## Agent grounding (SP4, opt-in)

When `graph_integration.agent_grounding: true`, dispatch prompts gain a **Graph context**
block: the relevant project's hubs + the task's blast-radius / seam neighbors, so a freshly
spawned Lead/critic/architect orients without re-reading files. When `mcp_live: true`, agents
may also query the graphify MCP server (`query_graph`, `get_neighbors`, `god_nodes`,
`shortest_path`) for live traversal. Both off by default.

## Building & refreshing

- `/orchestrate refresh-graph` — (1) build per-project AST graphs via `scripts/graph_build.py`
  (free, no LLM), (2) build the seam graph by **semantic** extraction over the curated corpus
  (`docs/agents/graph/seam/corpus.json`, written by `graph_build.compute_seam_corpus`), (3) bake
  the snapshot, (4) re-render the CLAUDE.md managed block.
- `/orchestrate update` — re-bakes the snapshot from existing graphs and diffs new hubs / seam edges.
- Per-project freshness can ride graphify's free git post-commit hook (`graphify hook install`).

### Seam corpus selection

`graph_build.compute_seam_corpus` collects, per project:
- backend (nestjs/express/…): `*.controller.ts`, `*.dto.ts`, `*.resolver.ts`, `*.gateway.ts`
- frontend: `*.api.ts|js`, `*.service.ts|js`

Small, curated corpus ⇒ the only paid extraction, and bounded.

## Degradation matrix

| Situation | Behavior |
|---|---|
| graphify not installed | `graph_build` reports cleanly; integration stays disabled |
| graphify installed, no snapshot | runtime uses heuristic rules; `refresh-graph` builds it |
| snapshot present but stale | used; staleness surfaced via `built_at` |
| fact is `INFERRED` | advisory only, never a silent gate |
| `graph_integration.enabled: false` | scan/infer/generate/update behave identically to pre-integration |

## Config block

```yaml
graph_integration:
  enabled: false
  snapshot: .claude/orchestration.graph.json
  per_project_graphs: true
  seam_graph: true
  agent_grounding: false
  mcp_live: false
  hub_top_n: 8
  trust:
    raise_impact_on_hub: true
    cofire_blocking_when: EXTRACTED   # else advisory
```

## Scripts

| Script | Role | Dependencies |
|---|---|---|
| `scripts/graph_build.py` | build AST per-project graphs (via graphify), compute seam corpus, build plan | graphify (optional) |
| `scripts/graph_bake.py` | distill graphs → snapshot | stdlib only |
| `scripts/blast_radius.py` | runtime "what depends on X" + hub check | stdlib only |
| `scripts/generate.py::wire_graph_integration` | config + CLAUDE.md managed block | pyyaml |
