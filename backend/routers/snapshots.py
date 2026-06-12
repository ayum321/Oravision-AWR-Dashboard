"""Snapshot management endpoints."""
from fastapi import APIRouter, Query
from services.mock_data import get_mock_snapshots
from services.data_source import resolve_period_or_404, list_uploaded_data

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])

@router.get("/")
async def list_snapshots(demo: bool = Query(False)):
    """List available AWR snapshots (uploaded or demo)."""
    uploaded = list_uploaded_data()
    if uploaded:
        # Return summary of real uploaded snapshots
        snapshots = []
        for label, data in uploaded:
            snapshots.append({
                "label": label,
                "db_name": data.get("db_name", ""),
                "instance": data.get("instance", ""),
                "begin_snap": data.get("begin_snap", 0),
                "end_snap": data.get("end_snap", 0),
                "begin_time": data.get("begin_time", ""),
                "end_time": data.get("end_time", ""),
                "source": "uploaded",
            })
        return {"snapshots": snapshots, "source": "uploaded"}
    if demo:
        return {"snapshots": get_mock_snapshots(), "source": "demo"}
    return {"snapshots": [], "source": "none", "message": "No AWR reports uploaded. Upload reports or use ?demo=true for sample data."}

@router.get("/data/{period}")
async def get_snapshot_data(period: str, demo: bool = Query(False)):
    """Get AWR data for a period."""
    data, source = resolve_period_or_404(period, demo=demo)
    return {"data": data, "source": source}
