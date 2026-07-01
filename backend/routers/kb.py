"""
KB Digest Router — expert incident cross-reference.

GET  /api/kb/status      Digest health: file present, incidents indexed, engineers.
POST /api/kb/crossref    Cross-reference a comparison report against past incidents.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services import kb_digest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kb", tags=["kb"])


class CrossrefRequest(BaseModel):
    report: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=4, ge=1, le=20)


@router.get("/status")
async def kb_status() -> dict[str, Any]:
    return kb_digest.status()


@router.post("/crossref")
async def kb_crossref(req: CrossrefRequest) -> dict[str, Any]:
    return kb_digest.crossref(req.report, top_k=req.top_k)
