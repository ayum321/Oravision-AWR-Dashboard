"""Wait Event Analysis endpoints."""
from fastapi import APIRouter, Query
from services.data_source import resolve_period_or_404, resolve_comparison_or_404

router = APIRouter(prefix="/api/waits", tags=["wait_events"])

@router.get("/{period}")
async def get_wait_events(period: str, demo: bool = Query(False)):
    """Get wait events for a period."""
    data, source = resolve_period_or_404(period, demo=demo)
    return {
        "wait_events":  data.get("wait_events", []),
        "wait_classes": data.get("_wait_classes", []),
        "time_model":   data.get("time_model", []),
        "ash_summary":  data.get("ash_summary", []),
        "period": period,
        "source": source,
    }

@router.get("/compare/{good_period}/{bad_period}")
async def compare_wait_events(good_period: str = "good", bad_period: str = "bad", demo: bool = Query(False)):
    """Compare wait events between two periods."""
    good_data, bad_data, sources = resolve_comparison_or_404(good_period, bad_period, demo=demo)

    # Single-pass build: dict keyed by event_name for O(1) lookup
    good_waits: dict = {w["event_name"]: w for w in good_data.get("wait_events", [])}
    bad_waits:  dict = {w["event_name"]: w for w in bad_data.get("wait_events", [])}

    # Union of all event names in one expression
    all_events = good_waits.keys() | bad_waits.keys()

    comparison = []
    for event in all_events:
        gw = good_waits.get(event, {})
        bw = bad_waits.get(event, {})
        good_time = gw.get("time_waited_secs", 0)
        bad_time  = bw.get("time_waited_secs", 0)
        comparison.append({
            "event_name":   event,
            "good_time_secs": good_time,
            "bad_time_secs":  bad_time,
            "good_pct":     gw.get("pct_db_time", 0),
            "bad_pct":      bw.get("pct_db_time", 0),
            "good_avg_ms":  gw.get("avg_wait_ms", 0),
            "bad_avg_ms":   bw.get("avg_wait_ms", 0),
            "wait_class":   bw.get("wait_class", gw.get("wait_class", "Other")),
            # Correctly track both directions
            "is_new":          event not in good_waits,
            "is_disappeared":  event not in bad_waits,
        })

    comparison.sort(key=lambda x: x["bad_time_secs"], reverse=True)
    return {"comparison": comparison, "sources": {"good": sources[0], "bad": sources[1]}}
