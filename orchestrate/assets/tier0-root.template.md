# CLAUDE.md — {{project_name}}

{{project_description}}

## Repository Structure

{{repository_structure}}

## Orchestrator Agent System

This project uses a 4-tier agent system. Claude Code acts as the **root orchestrator** (Tier 0) — it never implements code directly. Instead, it classifies incoming tasks, assesses impact, applies the gate machinery, and dispatches to specialized agents.

### Dispatch loop (8 steps)

```
1. CLASSIFY         request type
2. ASSESS IMPACT    LOW / MEDIUM / HIGH / CRITICAL
3. DA GATE          da-lead + critics (tier-scaled)
4. ARCHITECT        (if cross-repo) produces spec
4.5 PRE-IMPL GATE   spec validators (smart loop-back)
5. ROUTE            dispatch to Lead(s)
6. EXECUTE          Leads + sub-specialists
6.5 POST-IMPL GATE  code validators (smart loop-back)
7. SYNTHESIZE       unify, present to user
```

Full semantics in `~/.claude/skills/orchestrate/references/loop-semantics.md`.

### Impact classification

{{impact_classification_rules}}

### Devil's Advocate tiered gate

| Impact | DA Behavior |
|--------|-------------|
| LOW | Skip — no DA review |
| MEDIUM | Advise — runs in parallel; findings included but don't block |
| HIGH | Block — must review BEFORE implementation begins |
| CRITICAL | Block + Debate — DA presents structured FOR/AGAINST; user decides |

### Validation gates

- Pre-impl gate: runs after spec exists, before any Lead is dispatched. 6 universal validators + applicable platform-pack validators. Smart routing on failure (see loop-semantics).
- Post-impl gate: runs after Lead(s) finish, before declaring done. 6 universal validators (5 + qa-delegator). Smart routing on failure.

### Project Leads (Tier 1)

{{lead_dispatch_table}}

### Cross-cutting agents

{{cross_cutting_table}}

### Task agents (Tier 3)

| Agent | Location | Scope |
|---|---|---|
| bug-fixer | `docs/agents/task-agents/bug-fixer.md` | Systematic debugging |
| feature-builder | `docs/agents/task-agents/feature-builder.md` | End-to-end feature implementation |
| refactor | `docs/agents/task-agents/refactor.md` | Safe refactoring with test preservation |
{{migration_writer_row}}

### Personas (Tier 3)

{{persona_table}}

### Skill injection at dispatch

Subagents do not inherit parent skills. Tier 0 includes required-skill instructions in each dispatch using this template:

```
REQUIRED SKILLS — invoke before starting:
1. <skill-id> — <reason>
2. <skill-id> — <reason>
```

Task-type → skill mapping:

{{skill_injection_table}}

## Tech stack

{{tech_stack}}

## Code style

{{code_style}}

## Commands

{{commands}}
