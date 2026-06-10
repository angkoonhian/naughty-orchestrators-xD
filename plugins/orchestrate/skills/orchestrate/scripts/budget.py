"""budget — the budget-driven orchestration engine's deterministic core.

Turns an impact tier + an optional per-request override + project config into a
concrete token budget and the decisions that flow from it: which execution engine
to use (inline vs Workflow), how to split the budget (understand / implementation
floor / gates), whether to deepen a review dimension, and which model tier to use.

Pure stdlib + deterministic, so it unit-tests in isolation. See
references/budget-model.md for the full contract.

OVERRIDE GRAMMAR IS OPT-IN. To avoid silently rescaling spend from ordinary prose
('add a max-width', 'deep link', 'quick fix'), directives must be EXPLICIT:
  - the standalone word `unleash` / `unleashed`  → unlimited
  - `budget unlimited`                            → unlimited
  - `budget 300k`                                 → absolute
  - `budget +200k` / `budget -50k`                → delta
  - `/cheap` or `keep it cheap` or `budget cheap` → ×0.4
  - `/thorough` or `be thorough` or `budget thorough` → ×3
Bare adjectives (`max`, `deep`, `quick`, `minimal`, `careful`, `lite`) and bare
signed numbers do NOT change the budget. The resolved override is always echoed in
the spend report so any (mis)parse is visible.
"""
from __future__ import annotations

import math
import re
from typing import Any

UNLIMITED = math.inf

# Impact → default token budget (tunable via config.budget.defaults).
IMPACT_DEFAULTS: dict[str, float] = {
    "LOW": 0,
    "MEDIUM": 150_000,
    "HIGH": 500_000,
    "CRITICAL": 1_200_000,
}

# High-blast-radius review dimensions that ALWAYS deepen on HIGH/CRITICAL impact
# (budget permitting), regardless of Pass-1's self-reported confidence.
FORCE_DEEPEN_DIMENSIONS = {
    "security", "auth", "authn", "authz", "authorization", "authentication",
    "data-loss", "data_loss", "migration", "migrations", "cross-tenant", "cross_tenant",
}

DEFAULTS = {
    "mode": "budgeted",                 # budgeted | unlimited
    "max_request_budget": 2_000_000,    # hard session ceiling (budgeted mode)
    "overrides": {"cheap": 0.4, "thorough": 3.0},
    "deepen_threshold": 0.7,            # confidence below this → consider deepening
    "deepen_cost": 40_000,              # est. cost of one specialist deepener (critic + a dimension-relevant pack SLICE)
    "verify_cost": 25_000,             # est. cost of an adversarial verify per surfaced HIGH/CRITICAL finding
    "workflow_threshold": 12,           # estimated agents above which → Workflow engine
    "force_deepen_dimensions": sorted(FORCE_DEEPEN_DIMENSIONS),
    "unleashed": {"max_rounds": 5, "convergence_clean_rounds": 2, "agent_ceiling": 800},
    "models": {"mechanical": "haiku", "judgment": "opus"},
}

SEVERITY_RANK = {"CRITICAL": 3, "HIGH": 2, "IMPORTANT": 2, "MEDIUM": 1, "MINOR": 0, "LOW": 0}


# ---------------------------------------------------------------- parsing

def parse_amount(s: str | int | float) -> int:
    """'300k' -> 300000, '1.2m' -> 1200000, '200000' -> 200000, 250000 -> 250000."""
    if isinstance(s, (int, float)):
        return int(s)
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([kmKM])?\s*", str(s))
    if not m:
        raise ValueError(f"unparseable amount: {s!r}")
    val = float(m.group(1))
    unit = (m.group(2) or "").lower()
    mult = {"": 1, "k": 1_000, "m": 1_000_000}[unit]
    return int(val * mult)


# Explicit, opt-in directives only — never bare adjectives / bare signed numbers.
_UNLIMITED_RE = re.compile(r"(?:^|\s)(?:/unleash|unleash(?:ed)?)\b|\bbudget[:\s]+(?:unlimited|infinite|none)\b", re.I)
_DELTA_RE = re.compile(r"\b(?:/budget|budget)[:\s]+([+\-])\s*([0-9]*\.?[0-9]+\s*[kmKM]?)\b", re.I)
_ABS_RE = re.compile(r"\b(?:/budget|budget)[:\s]+([0-9]*\.?[0-9]+\s*[kmKM]?)\b", re.I)
_CHEAP_RE = re.compile(r"(?:^|\s)/cheap\b|\bbudget[:\s]+cheap\b|\b(?:keep it|go|be)\s+cheap\b", re.I)
_THOROUGH_RE = re.compile(r"(?:^|\s)/thorough\b|\bbudget[:\s]+thorough\b|\b(?:be|go)\s+thorough\b", re.I)


def parse_override(request_text: str | None) -> dict[str, Any] | None:
    """Extract an EXPLICIT budget directive from text. Returns {kind, value?, matched} or None."""
    if not request_text:
        return None
    t = str(request_text)
    if _UNLIMITED_RE.search(t):
        return {"kind": "unlimited", "matched": "unleash"}
    m = _DELTA_RE.search(t)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        return {"kind": "delta", "value": sign * parse_amount(m.group(2)), "matched": m.group(0).strip()}
    m = _ABS_RE.search(t)
    if m:
        return {"kind": "absolute", "value": parse_amount(m.group(1)), "matched": m.group(0).strip()}
    if _CHEAP_RE.search(t):
        return {"kind": "multiplier", "name": "cheap", "matched": "cheap"}
    if _THOROUGH_RE.search(t):
        return {"kind": "multiplier", "name": "thorough", "matched": "thorough"}
    return None


# ---------------------------------------------------------------- resolution

def _cfg(config: dict | None) -> dict:
    c = dict(DEFAULTS)
    if config:
        for k, v in (config or {}).items():
            if isinstance(v, dict) and isinstance(c.get(k), dict):
                c[k] = {**c[k], **v}
            else:
                c[k] = v
    return c


def _is_reduce(ov: dict | None) -> bool:
    """An override that REDUCES spend (used to dial a config-unlimited request down)."""
    if not ov:
        return False
    return (
        (ov["kind"] == "multiplier" and ov.get("name") == "cheap")
        or ov["kind"] == "absolute"
        or (ov["kind"] == "delta" and ov.get("value", 0) < 0)
    )


def resolve_budget(impact: str, request_text: str | None = None, config: dict | None = None) -> dict[str, Any]:
    """Resolve the concrete budget for a request.

    Returns { tokens (int|inf), mode, impact, base, source, override }.
    Precedence: explicit `unleash` → unlimited. A config-`unlimited` MAX user stays
    unlimited unless a REDUCE-intent override (cheap / budget N / negative delta) dials
    it down — `thorough`/`+N` do NOT downgrade an unlimited user (they are no-ops there).
    """
    impact = (impact or "MEDIUM").upper()
    c = _cfg(config)
    defaults = {**IMPACT_DEFAULTS, **(c.get("defaults") or {})}
    try:
        base = float(defaults.get(impact, IMPACT_DEFAULTS.get(impact, 150_000)))
    except (TypeError, ValueError):
        base = float(IMPACT_DEFAULTS.get(impact, 150_000))
    try:
        cap = float(c.get("max_request_budget", DEFAULTS["max_request_budget"]))
    except (TypeError, ValueError):
        cap = float(DEFAULTS["max_request_budget"])
    ov = parse_override(request_text)
    matched = ov.get("matched") if ov else None
    config_unlimited = c.get("mode") == "unlimited"

    if ov and ov["kind"] == "unlimited":
        return {"tokens": UNLIMITED, "mode": "unlimited", "impact": impact, "base": base,
                "source": "override:unleash", "override": matched}
    if config_unlimited and not _is_reduce(ov):
        return {"tokens": UNLIMITED, "mode": "unlimited", "impact": impact, "base": base,
                "source": "config:unlimited", "override": matched}

    # Budgeted: apply override to the base.
    tokens, source = base, "impact-default"
    if ov:
        if ov["kind"] == "absolute":
            tokens, source = float(ov["value"]), "override:budget"
        elif ov["kind"] == "delta":
            tokens, source = max(0.0, base + ov["value"]), "override:delta"
        elif ov["kind"] == "multiplier":
            mult = (c.get("overrides") or {}).get(ov["name"], 1.0)
            tokens, source = base * mult, f"override:{ov['name']}"

    tokens = min(tokens, float(cap))  # hard session ceiling
    return {"tokens": int(tokens), "mode": "budgeted", "impact": impact, "base": int(base),
            "source": source, "override": matched}


# ---------------------------------------------------------------- decisions

def route_engine(estimated_agents: int, impact: str, mode: str, config: dict | None = None) -> str:
    """'inline' or 'workflow'. Workflow for unleashed, CRITICAL, or large fan-outs."""
    c = _cfg(config)
    if mode == "unlimited" or (impact or "").upper() == "CRITICAL":
        return "workflow"
    if estimated_agents > c.get("workflow_threshold", DEFAULTS["workflow_threshold"]):
        return "workflow"
    return "inline"


def must_deepen(dimension: str, impact: str, remaining: float, config: dict | None = None) -> bool:
    """High-blast-radius dimensions (security/auth/data-loss/migrations) ALWAYS deepen on
    HIGH/CRITICAL impact when affordable — independent of Pass-1's self-reported confidence,
    which is advisory only. This is the calibration floor against a falsely-confident Pass-1."""
    c = _cfg(config)
    force = {d.lower() for d in c.get("force_deepen_dimensions", DEFAULTS["force_deepen_dimensions"])}
    if (impact or "").upper() in ("HIGH", "CRITICAL") and (dimension or "").lower() in force:
        return remaining >= c.get("deepen_cost", DEFAULTS["deepen_cost"])
    return False


def should_deepen(severity: str, confidence: float, remaining: float, config: dict | None = None,
                  dimension: str | None = None, impact: str | None = None) -> bool:
    """Escalate a review dimension to a dedicated specialist.

    `remaining` MUST be the **gates-slice** remaining (see allocate()), never the whole
    budget — gates may never consume the reserved implementation floor.

    Returns True when EITHER: the dimension is a force-deepen one on a HIGH/CRITICAL request
    (must_deepen), OR it is risky/uncertain (severity ≥ HIGH or confidence < threshold) AND
    affordable. The cost of an affordable deepen on a finding includes a later verify pass.
    """
    c = _cfg(config)
    if must_deepen(dimension or "", impact or "", remaining, config):
        return True
    sev = SEVERITY_RANK.get((severity or "").upper(), 0)
    risky = sev >= 2 or confidence < c.get("deepen_threshold", DEFAULTS["deepen_threshold"])
    cost = c.get("deepen_cost", DEFAULTS["deepen_cost"]) + (c.get("verify_cost", DEFAULTS["verify_cost"]) if sev >= 2 else 0)
    return bool(risky and remaining >= cost)


def allocate(budget: float, config: dict | None = None) -> dict[str, float]:
    """Split a budget: understand (~10%, capped), reserved implementation floor (~40%),
    gates get the surplus. `should_deepen` spends ONLY against the gates slice. Unlimited → inf."""
    if budget == UNLIMITED:
        return {"understand": UNLIMITED, "implementation_floor": UNLIMITED, "gates": UNLIMITED}
    try:
        budget = max(0.0, float(budget))
    except (TypeError, ValueError):
        budget = 0.0
    understand = min(0.10 * budget, 60_000)
    impl_floor = 0.40 * budget
    gates = max(0.0, budget - understand - impl_floor)
    return {"understand": understand, "implementation_floor": impl_floor, "gates": gates}


def model_for(task_kind: str, config: dict | None = None) -> str:
    """'mechanical' (lint/regression/Pass-1/dedup) → cheap; else → judgment tier."""
    c = _cfg(config)
    models = c.get("models", DEFAULTS["models"])
    return models.get("mechanical" if task_kind == "mechanical" else "judgment", "opus")


# ---------------------------------------------------------------- ledger + report

class Ledger:
    """Accumulates spend against a budget.

    INLINE path: `add()` the `subagent_tokens` from each `Agent` tool result's `usage`
    block — that is the CHILD's TOTAL consumption (incl. its own file reads), so the
    inline ledger is a reasonable measure, but it does NOT include Tier 0's own
    orchestration tokens between dispatches, so `spent` is a **lower bound** and the
    inline hard cap is **best-effort**. For authoritative enforcement use the Workflow
    engine (real `budget` primitive) — already required for large/CRITICAL/unleashed.
    """

    def __init__(self, budget: float) -> None:
        self.budget = budget
        self.spent = 0.0
        self.by_stage: dict[str, float] = {}

    def add(self, tokens: float, stage: str = "other") -> None:
        self.spent += tokens
        self.by_stage[stage] = self.by_stage.get(stage, 0.0) + tokens

    def remaining(self) -> float:
        if self.budget == UNLIMITED:
            return UNLIMITED
        return max(0.0, self.budget - self.spent)

    def exhausted(self) -> bool:
        return self.budget != UNLIMITED and self.spent >= self.budget


def _fmt(n: float) -> str:
    if n == UNLIMITED:
        return "INF"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}m"
    if n >= 1_000:
        return f"{round(n / 1_000)}k"
    return str(int(n))


def spend_report(impact: str, mode: str, budget: float, ledger: Ledger, agents: dict[str, int],
                 deepened: list[str] | None = None, skipped: list[str] | None = None,
                 override: str | None = None) -> str:
    """Render the per-response spend report. Always echoes the detected override (if any)
    so an accidental rescale is visible to the user."""
    agent_str = " · ".join(f"{v} {k}" for k, v in agents.items() if v)
    prefix = "spent≈" if mode != "unlimited" else "spent~"
    head = f"⟦orchestration⟧ impact={impact} · mode={mode} · budget={_fmt(budget)} · {prefix}{_fmt(ledger.spent)}"
    if override:
        head += f' · override="{override}"'
    lines = [head, f"agents: {agent_str or 'none'}" + (f" (deepened: {', '.join(deepened)})" if deepened else "")]
    if skipped:
        lines.append(f"skipped (budget): {', '.join(skipped)}")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    impact = sys.argv[1] if len(sys.argv) > 1 else "HIGH"
    req = sys.argv[2] if len(sys.argv) > 2 else None
    res = resolve_budget(impact, req)
    alloc = allocate(res["tokens"])
    res["tokens"] = "INF" if res["tokens"] == UNLIMITED else res["tokens"]
    res["allocation"] = {k: ("INF" if v == UNLIMITED else int(v)) for k, v in alloc.items()}
    print(json.dumps(res, indent=2, default=str))
