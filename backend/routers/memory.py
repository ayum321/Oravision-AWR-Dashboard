"""
Diagnostic Memory API — control surface for the backend learning engine.

These endpoints let the system (or a PE) inspect what the dashboard has learned,
confirm ground-truth outcomes (feedback loop), see what is NEW/unrecognised, and
backfill the library from AWRs already uploaded in this session.

Every handler is failure-proof: the learning engine must never break a request.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services import diagnostic_memory
from services.comparator import compare_periods
from services.data_source import get_uploaded_data, list_uploaded_data

router = APIRouter(prefix="/api/memory", tags=["memory"])


class ConfirmRequest(BaseModel):
    case_id: str = Field(..., min_length=1, max_length=128)
    confirmed_root_cause: str = Field(..., min_length=1, max_length=200)


class BackfillRequest(BaseModel):
    good_label: str = Field(..., min_length=1, max_length=64)
    bad_label: str = Field(..., min_length=1, max_length=64)


@router.get("/stats")
async def memory_stats():
    """What the dashboard knows: coverage by bottleneck class, confirmed vs novel."""
    try:
        return diagnostic_memory.stats()
    except Exception as exc:
        return {"library_size": 0, "error": str(exc)}


@router.get("/cases")
async def memory_cases(limit: int = 100):
    """List learned + golden cases (most recent first) for audit/inspection."""
    try:
        limit = max(1, min(int(limit), 500))
        return {"cases": diagnostic_memory.all_cases(limit=limit)}
    except Exception as exc:
        return {"cases": [], "error": str(exc)}


@router.post("/confirm")
async def memory_confirm(req: ConfirmRequest):
    """Feedback loop — tag a stored case with its DB-validated root cause."""
    try:
        ok = diagnostic_memory.confirm_case(req.case_id, req.confirmed_root_cause.strip())
        return {"ok": ok, "case_id": req.case_id,
                "message": "Confirmed and added to ground truth." if ok else "Case id not found."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/backfill")
async def memory_backfill(req: BackfillRequest):
    """Learn from a pair of AWRs already uploaded this session."""
    try:
        good = get_uploaded_data(req.good_label)
        bad = get_uploaded_data(req.bad_label)
        if not good or not bad:
            return {"ok": False, "message": "One or both labels not found in current uploads.",
                    "available": [lbl for lbl, _ in list_uploaded_data()]}
        report = compare_periods(good, bad).model_dump()
        memory = diagnostic_memory.match(report)
        rec = diagnostic_memory.record_case(
            report, db_name=str(good.get("db_name", "")), novel=bool(memory.get("is_novel"))
        )
        return {"ok": True, "recorded_id": rec.get("id"),
                "is_novel": memory.get("is_novel"), "matched": memory.get("matched"),
                "library_size": diagnostic_memory.stats().get("library_size")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
