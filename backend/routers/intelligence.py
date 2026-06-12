"""
Intelligence API Router
=======================
GET  /api/intelligence/status/{upload_id}  — is analysis ready?
GET  /api/intelligence/{upload_id}         — get full FindingReport
POST /api/intelligence/trigger/{upload_id} — trigger analysis manually (if auto-trigger missed)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.awr_intelligence import (
    run_intelligence, run_intelligence_compare,
    cache_get, cache_status,
)
from services.data_source import get_uploaded_data, has_uploaded_data

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


# ─── Status ───────────────────────────────────────────────────────────────────
@router.get("/status/{upload_id}")
async def get_status(upload_id: str):
    """Poll this to know when analysis is ready."""
    status = cache_status(upload_id)
    return {
        "upload_id": upload_id,
        "status": status,          # "ready" | "missing"
        "data_available": has_uploaded_data(upload_id),
    }


# ─── Get report ───────────────────────────────────────────────────────────────
@router.get("/{upload_id}")
async def get_report(upload_id: str):
    """Return the cached FindingReport for this upload."""
    report = cache_get(upload_id)
    if report is None:
        raise HTTPException(404, detail={
            "error": "Analysis not ready yet",
            "upload_id": upload_id,
            "hint": "Poll /api/intelligence/status/{upload_id} then retry",
        })
    return report


# ─── Manual trigger ───────────────────────────────────────────────────────────
class TriggerRequest(BaseModel):
    model: Optional[str] = None


@router.post("/trigger/{upload_id}")
async def trigger_analysis(upload_id: str, req: TriggerRequest, background_tasks: BackgroundTasks):
    """Re-run (or start) intelligence analysis for a given upload."""
    data = get_uploaded_data(upload_id)
    if data is None:
        raise HTTPException(404, f"No uploaded data for '{upload_id}'. Upload a file first.")
    model = req.model

    loop = asyncio.get_event_loop()

    async def _run():
        await loop.run_in_executor(_executor, lambda: run_intelligence(upload_id, data, model))
        log.info("Intelligence analysis complete for %s", upload_id)

    background_tasks.add_task(_run)
    return {"status": "triggered", "upload_id": upload_id}


@router.post("/trigger-compare/{good_id}/{bad_id}")
async def trigger_compare(good_id: str, bad_id: str, req: TriggerRequest, background_tasks: BackgroundTasks):
    """Re-run intelligence analysis for a comparison upload."""
    good_data = get_uploaded_data(good_id)
    bad_data = get_uploaded_data(bad_id)
    if good_data is None:
        raise HTTPException(404, f"No uploaded data for '{good_id}'.")
    if bad_data is None:
        raise HTTPException(404, f"No uploaded data for '{bad_id}'.")
    model     = req.model
    comp_id   = f"{good_id}_vs_{bad_id}"

    loop = asyncio.get_event_loop()

    async def _run():
        await loop.run_in_executor(
            _executor,
            lambda: run_intelligence_compare(good_id, bad_id, good_data, bad_data, model)
        )
        log.info("Comparison intelligence analysis complete for %s", comp_id)

    background_tasks.add_task(_run)
    return {"status": "triggered", "upload_id": comp_id}
