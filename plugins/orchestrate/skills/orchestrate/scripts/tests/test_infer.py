"""Tests for infer.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.infer import infer_recommendations


def test_recommends_socket_realtime_when_socketio_detected() -> None:
    profile = {
        "shape": "single_app",
        "projects": [{"name": "api", "framework": "nestjs", "qa_scripts": {}}],
        "infrastructure": {"real_time": "socket.io"},
        "domain_markers": {},
    }
    recs = infer_recommendations(profile)
    assert "socket-realtime" in recs["recommended_platform_packs"]


def test_recommends_queue_system_when_bull_detected() -> None:
    profile = {
        "shape": "single_app",
        "projects": [{"name": "api", "framework": "nestjs", "qa_scripts": {}}],
        "infrastructure": {"queues": ["bull"]},
        "domain_markers": {},
    }
    recs = infer_recommendations(profile)
    assert "queue-system" in recs["recommended_platform_packs"]


def test_recommends_multi_tenant_when_marker_set() -> None:
    profile = {
        "shape": "single_app",
        "projects": [{"name": "api", "framework": "nestjs", "qa_scripts": {}}],
        "infrastructure": {},
        "domain_markers": {"multi_tenant": True},
    }
    recs = infer_recommendations(profile)
    assert "multi-tenant" in recs["recommended_platform_packs"]


def test_recommends_jwt_auth_when_jwt_detected() -> None:
    profile = {
        "shape": "single_app",
        "projects": [{"name": "api", "framework": "nestjs", "qa_scripts": {}}],
        "infrastructure": {"auth_jwt": "@nestjs/jwt"},
        "domain_markers": {},
    }
    recs = infer_recommendations(profile)
    assert "jwt-auth" in recs["recommended_platform_packs"]


def test_recommends_observability_when_sentry_detected() -> None:
    profile = {
        "shape": "single_app",
        "projects": [{"name": "api", "framework": "nestjs", "qa_scripts": {}}],
        "infrastructure": {"observability": ["sentry"]},
        "domain_markers": {},
    }
    recs = infer_recommendations(profile)
    assert "observability-sentry" in recs["recommended_platform_packs"]


def test_adaptive_tier2_only_for_high_complexity() -> None:
    profile = {
        "shape": "monorepo",
        "projects": [
            {"name": "api", "complexity": "high", "qa_scripts": {}},
            {"name": "support", "complexity": "medium", "qa_scripts": {}},
            {"name": "website", "complexity": "low", "qa_scripts": {}},
        ],
        "infrastructure": {},
        "domain_markers": {},
    }
    recs = infer_recommendations(profile)
    assert recs["adaptive_tier2_leads"] == ["api"]


def test_qa_wiring_extracted_from_first_project_with_scripts() -> None:
    profile = {
        "shape": "monorepo",
        "projects": [
            {"name": "p1", "qa_scripts": {}},
            {"name": "p2", "qa_scripts": {"lint": "eslint .", "test": "jest"}, "path": "/p2"},
        ],
        "infrastructure": {},
        "domain_markers": {},
    }
    recs = infer_recommendations(profile)
    assert recs["qa_wiring"]["type"] == "npm_scripts"
    assert recs["qa_wiring"]["commands"]["lint"] == "eslint ."


def test_impact_bumps_for_multi_tenant() -> None:
    profile = {
        "shape": "single_app",
        "projects": [{"name": "api", "qa_scripts": {}}],
        "infrastructure": {},
        "domain_markers": {"multi_tenant": True},
    }
    recs = infer_recommendations(profile)
    assert any("tenant" in b.get("condition", "").lower() for b in recs["impact_bumps"])


def test_no_recommendations_when_nothing_detected() -> None:
    profile = {
        "shape": "single_app",
        "projects": [{"name": "myapp", "qa_scripts": {}}],
        "infrastructure": {},
        "domain_markers": {},
    }
    recs = infer_recommendations(profile)
    assert recs["recommended_platform_packs"] == []
