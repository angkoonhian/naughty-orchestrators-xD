"""Tests for budget.py — the budget-driven orchestration core (explicit override grammar)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import budget as B


# ---- parse_amount ----

def test_parse_amount_variants():
    assert B.parse_amount("300k") == 300_000
    assert B.parse_amount("1.2m") == 1_200_000
    assert B.parse_amount("200000") == 200_000
    assert B.parse_amount("500K") == 500_000
    assert B.parse_amount(250_000) == 250_000


# ---- parse_override (explicit grammar) ----

def test_override_unlimited_explicit():
    for t in ["unleash it", "go /unleash now", "unleashed please", "use budget unlimited"]:
        assert B.parse_override(t)["kind"] == "unlimited", t

def test_override_budget_absolute_and_delta():
    assert B.parse_override("use budget 300k")["value"] == 300_000
    assert B.parse_override("budget +200k more")["value"] == 200_000
    assert B.parse_override("budget -50k")["value"] == -50_000

def test_override_multipliers_explicit():
    assert B.parse_override("keep it cheap")["name"] == "cheap"
    assert B.parse_override("/cheap")["name"] == "cheap"
    assert B.parse_override("be thorough about it")["name"] == "thorough"
    assert B.parse_override("budget thorough")["name"] == "thorough"

def test_override_false_positives_resolve_to_none():
    # The whole point: ordinary dev prose must NEVER rescale spend.
    for t in [
        "add a max-width CSS property to the navbar",
        "set max retries to 5", "set max-age to 3600", "the maximal flow rate sensor",
        "refactor the unlimited scroll component",
        "the deep link is broken", "this is a deep copy bug",
        "a quick fix for the navbar", "minimal viable change", "lite version",
        "careful with the migration", "rigorous tests please",
        "add a -50 discount field", "shift schedule by -2 hours", "add +10k throughput",
        "no budget left in sprint",   # 'no budget' as prose must NOT mean unlimited
        "just add the endpoint", None,
    ]:
        assert B.parse_override(t) is None, t


# ---- resolve_budget ----

def test_resolve_impact_defaults():
    assert B.resolve_budget("LOW")["tokens"] == 0
    assert B.resolve_budget("MEDIUM")["tokens"] == 150_000
    assert B.resolve_budget("HIGH")["tokens"] == 500_000
    assert B.resolve_budget("CRITICAL")["tokens"] == 1_200_000

def test_resolve_cheap_and_thorough():
    assert B.resolve_budget("HIGH", "keep it cheap")["tokens"] == int(500_000 * 0.4)
    assert B.resolve_budget("MEDIUM", "be thorough")["tokens"] == int(150_000 * 3.0)

def test_resolve_absolute_and_delta():
    assert B.resolve_budget("MEDIUM", "budget 300k")["tokens"] == 300_000
    assert B.resolve_budget("MEDIUM", "budget +100k")["tokens"] == 250_000

def test_resolve_unlimited_via_override_and_config():
    assert B.resolve_budget("LOW", "unleash")["tokens"] == math.inf
    assert B.resolve_budget("MEDIUM", None, {"mode": "unlimited"})["tokens"] == math.inf

def test_config_unlimited_dials_down_only_on_reduce():
    cfg = {"mode": "unlimited"}
    # cheap / absolute / negative-delta REDUCE → drop to budgeted
    assert B.resolve_budget("HIGH", "keep it cheap", cfg)["mode"] == "budgeted"
    assert B.resolve_budget("HIGH", "budget 200k", cfg)["tokens"] == 200_000
    # thorough / +delta are INCREASE intent → stay unlimited (the review's CRITICAL fix)
    assert B.resolve_budget("HIGH", "be thorough", cfg)["mode"] == "unlimited"
    assert B.resolve_budget("HIGH", "budget +200k", cfg)["mode"] == "unlimited"

def test_hard_cap_clamps():
    assert B.resolve_budget("CRITICAL", "budget 9m", {"max_request_budget": 2_000_000})["tokens"] == 2_000_000


# ---- route_engine ----

def test_route_engine():
    assert B.route_engine(2, "MEDIUM", "budgeted") == "inline"
    assert B.route_engine(2, "CRITICAL", "budgeted") == "workflow"
    assert B.route_engine(2, "MEDIUM", "unlimited") == "workflow"
    assert B.route_engine(20, "MEDIUM", "budgeted") == "workflow"


# ---- deepening economics (review CRITICAL: a deepener must fit MEDIUM) ----

def test_a_deepener_fits_at_every_non_low_default():
    for tier in ("MEDIUM", "HIGH", "CRITICAL"):
        gates = B.allocate(B.resolve_budget(tier)["tokens"])["gates"]
        assert gates >= B.DEFAULTS["deepen_cost"], f"{tier}: gates {gates} < deepen_cost"

def test_should_deepen():
    assert B.should_deepen("HIGH", 0.9, remaining=500_000) is True       # high severity
    assert B.should_deepen("MINOR", 0.4, remaining=500_000) is True      # low confidence
    assert B.should_deepen("MINOR", 0.95, remaining=500_000) is False    # clean + confident
    assert B.should_deepen("HIGH", 0.9, remaining=10_000) is False       # can't afford
    assert B.should_deepen("CRITICAL", 0.9, remaining=math.inf) is True

def test_force_deepen_high_blast_radius():
    # security on a HIGH request deepens even when Pass-1 is confidently "clean".
    assert B.must_deepen("security", "HIGH", remaining=50_000) is True
    assert B.must_deepen("security", "MEDIUM", remaining=50_000) is False  # only HIGH/CRITICAL
    assert B.must_deepen("edge-case", "HIGH", remaining=50_000) is False   # not high-blast-radius
    assert B.should_deepen("MINOR", 0.99, remaining=50_000, dimension="security", impact="HIGH") is True


# ---- allocate / model_for / ledger / report ----

def test_allocate_budgeted_and_unlimited():
    a = B.allocate(500_000)
    assert abs((a["understand"] + a["implementation_floor"] + a["gates"]) - 500_000) < 1
    assert a["implementation_floor"] == 200_000
    assert all(v == math.inf for v in B.allocate(math.inf).values())

def test_model_for_tiers():
    assert B.model_for("mechanical") == "haiku"
    assert B.model_for("security") == "opus"

def test_ledger():
    led = B.Ledger(100_000)
    led.add(40_000, "review"); led.add(70_000, "impl")
    assert led.spent == 110_000 and led.remaining() == 0 and led.exhausted() is True
    inf = B.Ledger(math.inf); inf.add(5_000_000)
    assert inf.remaining() == math.inf and inf.exhausted() is False

def test_spend_report_echoes_override():
    led = B.Ledger(500_000); led.add(320_000)
    rep = B.spend_report("HIGH", "budgeted", 500_000, led, agents={"review": 3},
                         deepened=["security"], skipped=["perf"], override="budget 500k")
    assert "impact=HIGH" in rep and "deepened: security" in rep and 'override="budget 500k"' in rep
