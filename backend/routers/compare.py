"""AWR comparison endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from services.advanced_analytics import compute_advanced_analytics
from services.comparator import compare_periods, _cpu_count
from services.data_source import resolve_comparison_or_404, resolve_period_or_404
from services.dot_connector import analyze_comparison
from services.health_scorer import calculate_health_score
from services.rca_engine import run_comparison_rca
from services.recommendations import generate_recommendations
from services import diagnostic_memory
from services import kb_digest
from services import scenario_detector

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareRequest(BaseModel):
    good_period: Optional[str] = "good"
    bad_period: Optional[str] = "bad"
    good_snap_begin: Optional[int] = None
    good_snap_end: Optional[int] = None
    bad_snap_begin: Optional[int] = None
    bad_snap_end: Optional[int] = None
    demo: bool = False


def _build_compare_response(
    good_data: dict,
    bad_data: dict,
    good_source: str = "",
    bad_source: str = "",
) -> dict:
    """Build a full comparison response with health, recommendations, insights, and RCA."""
    report = compare_periods(good_data, bad_data)
    report_dict = report.model_dump()
    health_good = calculate_health_score(good_data)
    health_bad = calculate_health_score(bad_data)
    recs = generate_recommendations(good_data, bad_data)
    insights = analyze_comparison(good_data, bad_data, report_dict)
    comparison_rca = run_comparison_rca(good_data, bad_data, "Good (Baseline)", "Bad (Problem)")

    advanced = compute_advanced_analytics(
        good_data,
        bad_data,
        [sr.model_dump() for sr in report.sql_regressions],
        report_dict.get("top_wait_events", {}).get("comparisons", []),
        report_dict.get("instance_efficiency", {}).get("comparisons", []),
    )

    advanced["batch_groups"] = report_dict.get("batch_groups", advanced.get("batch_groups", []))
    advanced["logon_storm_explanation"] = report_dict.get("logon_storm_explanation", "")

    # Silent backend intelligence: match against learned + golden case library,
    # then record this case so the engine grows smarter with every comparison.
    try:
        memory = diagnostic_memory.match(report_dict)
        diagnostic_memory.record_case(
            report_dict,
            db_name=str(good_data.get("db_name", "")),
            novel=bool(memory.get("is_novel")),
        )
    except Exception:
        memory = {"matched": 0, "library_size": 0, "drift_warning": "", "is_novel": False}

    # Cross-reference the flagged bottleneck against the expert incident digest.
    try:
        kb_matches = kb_digest.crossref(report_dict)
    except Exception:
        kb_matches = {"available": False, "incidents_indexed": 0, "match_count": 0, "matches": []}

    # Performance-architect pattern recognition: name the structural scenario
    # (cascading delete, stats collision, plan flip, volume growth) and connect
    # it to the matching expert incident's verbatim fix.
    try:
        # Raw host CPU count (from the bad/incident period) threads into the
        # generic resource-ceiling-vs-demand probes (e.g. PARALLEL oversubscription)
        # that need it — report_dict alone carries no raw num_cpus field.
        bad_cpu_count = _cpu_count(bad_data)
        scenarios = scenario_detector.link_kb(
            scenario_detector.detect(report_dict, cpu_count=bad_cpu_count), kb_matches
        )
    except Exception:
        scenarios = []

    return {
        "sources": {"good": good_source, "bad": bad_source},
        "report": report_dict,
        "health_good": health_good,
        "health_bad": health_bad,
        "recommendations": [r.model_dump() for r in recs],
        "insights": insights,
        "comparison_rca": comparison_rca,
        "advanced": advanced,
        "intelligence_memory": memory,
        "kb_crossref": kb_matches,
        "scenario_findings": scenarios,
    }


@router.post("/")
async def compare_awr(request: CompareRequest):
    """Compare two AWR periods."""
    good_data, bad_data, sources = resolve_comparison_or_404(
        request.good_period or "good",
        request.bad_period or "bad",
        demo=request.demo,
    )
    return _build_compare_response(good_data, bad_data, sources[0], sources[1])


@router.get("/mock")
async def compare_mock():
    """Explicit demo route: always uses demo data."""
    good_data, bad_data, sources = resolve_comparison_or_404("good", "bad", demo=True)
    return _build_compare_response(good_data, bad_data, sources[0], sources[1])


@router.get("/health/{period}")
async def get_health_score(period: str, demo: bool = Query(False)):
    """Get health score for a single period."""
    data, source = resolve_period_or_404(period, demo=demo)
    score = calculate_health_score(data)
    return {"health": score, "source": source}
