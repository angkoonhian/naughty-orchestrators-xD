# Budget-Driven Adaptive Orchestration (v2) — Design

**Date:** 2026-06-10
**Status:** Approved (brainstorm) → implementing
**Scope:** Replace the `orchestrate` skill's **fixed, tier-scaled fan-out** with a **budget-driven, progressively-deepening** engine — with an **unleashed (unlimited)** mode, **hybrid** inline/Workflow execution, **model tiering**, **gate de-duplication**, an explicit **synthesis/verification** layer, and a **spend report**. The 4-tier hierarchy and the bootstrap (scan → infer → generate) are unchanged.

---

## 1. Problem

The current runtime fans out many *independent* agents per request, regardless of need. A single HIGH-impact request:
- DA gate: `da-lead` + 7 core critics + ~N platform-pack critics → ~16 parallel agents
- Pre-impl gate: 7 agents · Post-impl gate: ~14 (incl. `qa-delegator → qa-lead → 8`)
- → **~40–60 subagents / request**, each independently re-reading context → **~3–8M tokens for one request**.

Tiers scale *block-vs-advise* but **not agent count**: a gate that fires, fires *all* its agents. This is the cost sink, and a non-starter for a public tool.

## 2. Goals / Non-goals

**Goals:** 5–15× cheaper on typical requests with quality preserved on risky ones; a single **dial** (`cheap → impact-default → thorough → unleashed`); an **unleashed** mode that ignores budget and engages maximal rigor for MAX-plan users; portable by default (inline) yet rigorous when needed (Workflow); honest (no silent truncation; a spend report).

**Non-goals:** changing the 4-tier hierarchy or the scan/infer/generate bootstrap; *removing* thoroughness (it becomes on-demand, not default).

## 3. The dial + budget model

Every request sits on `cheap → impact-default → thorough → unleashed`. Budget is **tokens**; `unleashed` = `∞`.

- **Impact → default budget** (tunable in config): `LOW ≈ 0` (skip gates, straight to Lead) · `MEDIUM ≈ 150k` · `HIGH ≈ 500k` · `CRITICAL ≈ 1.2M`.
- **Override grammar — EXPLICIT only** (per request): `keep it cheap`/`/cheap` (×0.4) · `be thorough`/`/thorough` (×3) · `budget 300k` (absolute) · `budget +200k` (delta) · `unleash`/`unleashed`/`budget unlimited` (→ unlimited). Bare prose (`max`, `deep`, `quick`, a stray `+10k`) does **nothing** and the detected override is echoed in the spend report. (Hardened after review — `max-width` must never mean ∞.)
- **Hard session ceiling** `max_request_budget` — overrides cannot breach it (except explicit unlimited mode).
- **Config flag** `budget.mode: unlimited` — every request runs unleashed by default (for MAX users). Only a *reduce-intent* one-off (`cheap`/`budget N`/negative delta) dials it down; `thorough`/`+N` stay ∞.
- **Ledger:** Tier 0 sums each `Agent` call's returned `usage` (inline) or reads `budget.spent()` (Workflow). `remaining = budget − spent`, checked before every fan-out.

## 4. Allocation policy — implementation-first

Spend in priority order; never starve the actual work:
1. **Understand once (~5–10%)** → a shared **context pack**: the diff/spec + relevant file excerpts + the graphify snapshot's `hubs`/`co_fire`. Handed to *every* downstream agent so they stop re-reading the repo from scratch (the current system's hidden tax).
2. **Implementation floor (reserved):** enough for the Lead(s) to do the work — gates can never consume it.
3. **Gates spend the *surplus*,** scaled by impact + `remaining`.

## 5. Progressive deepening — the engine

Replaces fixed fan-out. Each gate (DA, pre-impl, post-impl) runs in passes:
- **Pass 1 — one multi-lens reviewer:** a *single* agent evaluates all dimensions in one structured pass → `{ verdict, confidence (0–1), findings: [{ dimension, severity, evidence }] }`.
- **Selective escalation:** for each dimension where `severity ≥ HIGH` **or** `confidence < deepen_threshold`, **and** `remaining ≥ deepen_cost`, spawn a dedicated specialist critic on *just that dimension* (parallel). The 7 core critics + pack critics become **on-demand deepeners**.
- **Short-circuit:** clean + confident Pass 1 → done.
- **Budget exhaustion:** stop deepening, finish the critical path, and **report what was skipped** (no silent truncation).

## 6. Synthesis / verification layer (makes "more" into "better")

The component that converts extra agents into *signal* rather than noise. After any fan-out (deepeners or unleashed panels), before findings reach the user / drive a gate verdict:
1. **Dedup** — merge findings referring to the same `file:line`/issue.
2. **Severity-rank** — order by severity × confidence; demote nitpicks.
3. **Adversarial verify-before-surface (severity-asymmetric)** — each surviving HIGH/CRITICAL finding is checked by an independent skeptic prompted to *refute* it. **CRITICAL findings that can't be conclusively refuted are surfaced as advisories, never silently dropped** (default-refuted is reserved for MINOR/MEDIUM noise); refutation must carry its own `why_refuted` evidence. (Cheap when few findings; scales with budget.)
4. **Synthesize** — one consolidated verdict + ranked, verified findings with provenance.

This layer is **mandatory in unleashed mode** (where fan-out is largest) and **scaled by budget** otherwise.

## 7. Unleashed mode (`∞`)

- No cap, no budget short-circuit. Engages **maximal-rigor patterns**: full parallel critic panel + all validators every time, max Tier-2 depth, personas, FOR/AGAINST debate — **plus** depth the current system lacks: **loop-until-dry** (re-review until convergence), **multi-attempt tournaments** (N independent solution attempts → judge → synthesize, for ambiguous design), **perspective-diverse verification** (N skeptics per finding).
- **Termination = convergence:** stop when **K consecutive review rounds find nothing new AND all blocker findings are resolved**. Non-token **sanity backstop**: `max_rounds` (default 5) **and** a **code-enforced** `agent_ceiling` (default 800 — the workflow counts agents and stops, not just prose). No token ceiling. Convergence is a stability stop, **not** a correctness proof — guarded by per-round lens rotation + live-file re-reads.
- **Always runs on the Workflow engine** (real parallelism + deterministic ledger + `/workflows` visibility + resumability).

## 8. Hybrid execution

- **Default (inline, portable):** Tier 0 self-meters via `Agent` `usage` and follows the budget + deepening rules inline. No dependency on the Workflow feature.
- **Escalate to a generated Workflow** when: `estimated_agents > workflow_threshold` (default 12) **OR** `impact == CRITICAL` **OR** `mode == unleashed`. The Workflow's `budget` primitive enforces the cap natively (or runs the convergence loop for unleashed).

## 9. Model tiering

Cheap/fast model (e.g. Haiku) for **mechanical + Pass-1** work (lint/regression/smoke/spec-conformance line-matching, the multi-lens scan, dedup); top model (Opus) for **judgment/implementation/debate** (architect, security deep-dive, the implementing Leads, CRITICAL debate, adversarial verify). Stretches the budget; unleashed may run top-tier throughout. Mapping lives in config (`budget.models`).

## 10. Gate de-duplication

- Collapse `qa-delegator → qa-lead → 8 specialists`: run the project's real lint/test/typecheck **once** (deterministic commands, ~free — not LLM agents) and let post-impl validators be Pass-1 + selective deepen. Removes the double-review overlap.
- Drop the always-on 16-agent DA swarm at MEDIUM → Pass-1 reviewer + selective deepen.

## 11. Spend report (trust)

Every response ends with a compact report:
```
⟦orchestration⟧ impact=HIGH · mode=budgeted · budget=500k · spent≈320k
agents: 1 understand · 1 pre · 2 impl · 3 review (1 deepened: security)
skipped (budget): perf deep-dive
```
Makes the dial legible — essential for a public, budget-driven tool.

## 12. Config schema (`.claude/orchestration.config.yaml`)

```yaml
budget:
  mode: budgeted              # budgeted | unlimited
  defaults: { LOW: 0, MEDIUM: 150000, HIGH: 500000, CRITICAL: 1200000 }
  max_request_budget: 2000000 # hard session ceiling (budgeted mode)
  overrides: { cheap: 0.4, thorough: 3.0 }
  deepen_threshold: 0.7       # confidence below this → consider deepening
  deepen_cost: 40000          # one specialist deepener (sized so ≥1 fits the MEDIUM gates slice)
  verify_cost: 25000          # one adversarial verify per surfaced HIGH/CRITICAL finding
  workflow_threshold: 12      # estimated agents above which → Workflow engine
  force_deepen_dimensions: [security, auth, data-loss, migrations, cross-tenant]
  unleashed: { max_rounds: 5, convergence_clean_rounds: 2, agent_ceiling: 800 }
  models:
    mechanical: haiku
    judgment: opus
```

## 13. Build surface (skill)

- **New** `scripts/budget.py` — impact→budget defaults, override-grammar parsing, mode resolution, allocation, deepening-decision + spend-ledger helpers. Pure stdlib, **tested**.
- **New** `scripts/tests/test_budget.py`.
- **New** `references/budget-model.md` — the full contract (dial, table, grammar, allocation, deepening, synthesis, unleashed/convergence, model-tiering, spend report).
- **Rewrite** `references/loop-semantics.md` — budget-driven dispatch loop + progressive deepening + hybrid engine + unleashed.
- **Rewrite** `assets/cross-cutting/da-lead.md` — Pass-1 multi-lens + on-demand deepeners + the synthesis/verification layer.
- **New** `assets/cross-cutting/synthesis-verifier.md` — the dedup/rank/refute/synthesize agent.
- **New** `assets/workflows/unleashed-review.workflow.js` — the convergence-loop Workflow template (heavy/unleashed path).
- **Update** `assets/tier0-root.template.md` — embed the budget loop + spend report + a slimmer structure.
- **Update** `scripts/generate.py` — write the `budget` config block; slimmer `CLAUDE.md`.
- **Update** `SKILL.md` — document the dial, modes, and budget engine.

## 14. Success criteria

1. `budget.py` resolves impact→budget, parses every override (`cheap`/`thorough`/`budget N`/`+N`/`unleash`), enforces the hard cap, and decides deepening from `{severity, confidence, remaining}` — all unit-tested.
2. `mode: unlimited` (or `unleash`) yields `budget = ∞`, routes to the Workflow path, and terminates on convergence + backstop (proven by a budget.py mode-resolution test + the workflow template).
3. The contracts (`budget-model.md`, rewritten `loop-semantics.md`, `da-lead.md`, `synthesis-verifier.md`) describe Pass-1 → selective deepen → synthesis/verify, the spend report, and the degradation path with **no contradictions**.
4. `generate.py` writes the `budget` config block; existing generate/scan/infer tests still pass.
5. A user-agent review pass (cost + quality + public-readiness skeptics + a code reviewer)
   returns PASS / PASS-WITH-CHANGES with findings addressed.
6. **Recall benchmark (pre-public gate).** Run a fixed seeded-defect set across impact tiers and
   measure detection rate of (a) v1 full fan-out, (b) v2 Pass-1-only, (c) v2 Pass-1 + deepen +
   force-deepen. Ship only if (c) is within an acceptable delta of (a). Until that's run, the
   "preserved quality" claim is labelled **expected, unmeasured**.

## 15. Expected impact — a *distribution*, not a single number

| Request shape | Today | v2 |
|---|---|---|
| Clean / trivial (majority by count) | ~16–30 agents | ~1–2 (Pass-1 short-circuits) → **~5–15× cheaper** |
| Surfaces findings | ~16–30 | Pass-1 + 1–2 deepeners + verify → **~2–4× cheaper** |
| CRITICAL / unleashed | full | full **and beyond** (loop-until-dry, tournaments) — **break-even or more, intentional, on demand** |

The find-something path costs `deepen_cost + verify_cost` per hot dimension; the headline 5–15×
is the clean-path case. Convergence is a stability/diminishing-returns stop, **not** a correctness
proof; force-deepen + lens-rotation + live-file re-reads guard catch-rate, pending the §14.6 benchmark.
