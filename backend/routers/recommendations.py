"""Recommendations endpoints."""
from fastapi import APIRouter, Query
from services.recommendations import generate_recommendations, generate_single_report_recommendations
from services.data_source import resolve_period_or_404, resolve_comparison_or_404

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

@router.get("/{period}")
async def get_recommendations(period: str, demo: bool = Query(False)):
    """Get recommendations for a single period."""
    data, source = resolve_period_or_404(period, demo=demo)
    recs = generate_single_report_recommendations(data)
    return {"recommendations": [r.model_dump() for r in recs], "period": period, "source": source}

@router.get("/compare/good-vs-bad")
async def get_comparison_recommendations(demo: bool = Query(False)):
    """Get recommendations based on good vs bad comparison."""
    good, bad, sources = resolve_comparison_or_404("good", "bad", demo=demo)
    recs = generate_recommendations(good, bad)
    return {"recommendations": [r.model_dump() for r in recs], "sources": {"good": sources[0], "bad": sources[1]}}
