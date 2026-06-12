"""SQL Analysis endpoints."""
from fastapi import APIRouter
from services.data_source import resolve_period_data

router = APIRouter(prefix="/api/sql", tags=["sql"])

@router.get("/top/{period}")
async def top_sql(period: str, order_by: str = "elapsed_time"):
    """Get top SQL statements ordered by specified metric."""
    data, source = resolve_period_data(period)
    sql_stats = list(data.get("sql_stats", []))

    # Sort by requested metric
    sort_key_map = {
        "elapsed_time": "elapsed_time_secs",
        "cpu_time": "cpu_time_secs",
        "disk_reads": "disk_reads",
        "buffer_gets": "buffer_gets",
        "executions": "executions",
    }
    key = sort_key_map.get(order_by, "elapsed_time_secs")
    sql_stats.sort(key=lambda x: x.get(key, 0), reverse=True)

    # Ensure rows_processed is present in each SQL stat (for legacy/mock data)
    for s in sql_stats:
        if "rows_processed" not in s:
            s["rows_processed"] = 0
        if "rows_per_exec" not in s:
            s["rows_per_exec"] = 0
    return {"sql_stats": sql_stats[:20], "period": period, "order_by": order_by, "source": source}

@router.get("/detail/{period}/{sql_id}")
async def sql_detail(period: str, sql_id: str):
    """Get detail for a specific SQL statement."""
    data, source = resolve_period_data(period)
    sql_stats = data.get("sql_stats", [])
    found = next((s for s in sql_stats if s.get("sql_id") == sql_id), None)
    if not found:
        return {"error": "SQL not found", "sql_id": sql_id}
    if "rows_processed" not in found:
        found["rows_processed"] = 0
    if "rows_per_exec" not in found:
        found["rows_per_exec"] = 0
    return {"sql": found, "source": source}
