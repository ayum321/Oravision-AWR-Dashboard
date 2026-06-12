"""
RAG Narrative Router
====================

POST /api/rag/narrative    Generate AI-enhanced narrative for a comparison
GET  /api/rag/archetypes   List the knowledge-base archetypes
POST /api/rag/learn        Persist current narrative as a new archetype
GET  /api/rag/health       Show RAG provider/config status
POST /api/rag/ingest_pdf   Ingest an Oracle PDF into the knowledge base
GET  /api/rag/kb_status    Show PDF knowledge base chunk counts
POST /api/rag/query_kb     Keyword search against stored PDF knowledge
POST /api/rag/cross_check  Targeted RCA cross-check against PDF knowledge
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import rag_narrative
from services import pdf_kb

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rag", tags=["rag"])


class NarrativeRequest(BaseModel):
    report: dict[str, Any] = Field(default_factory=dict)
    ctx_signals: dict[str, Any] = Field(default_factory=dict)
    deterministic_narrative: str = ""
    k: int = 3


class LearnRequest(BaseModel):
    report: dict[str, Any] = Field(default_factory=dict)
    ctx_signals: dict[str, Any] = Field(default_factory=dict)
    narrative_html: str
    archetype_key: str | None = Field(None, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")


@router.get("/health")
async def health() -> dict[str, Any]:
    provider = rag_narrative._llm_provider()
    return {
        "status": "ok",
        "provider": provider,
        "model": (
            rag_narrative._OPENAI_MODEL if provider == "openai"
            else rag_narrative._ANTHROPIC_MODEL if provider == "anthropic"
            else None
        ),
        "vector_db": rag_narrative._DB_PATH.name,
        "signature_dimensions": rag_narrative.SIGNATURE_DIMS,
    }


@router.get("/archetypes")
async def archetypes() -> dict[str, Any]:
    return {"archetypes": rag_narrative.list_archetypes()}


@router.post("/narrative")
async def narrative(req: NarrativeRequest) -> dict[str, Any]:
    if not req.report and not req.ctx_signals:
        raise HTTPException(status_code=400, detail="report or ctx_signals required")
    try:
        return rag_narrative.generate_ai_narrative(
            req.report, req.ctx_signals, req.deterministic_narrative, k=max(1, min(req.k, 10))
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("RAG narrative generation failed")
        raise HTTPException(status_code=500, detail="RAG narrative generation failed.") from exc


@router.post("/learn")
async def learn(req: LearnRequest) -> dict[str, Any]:
    if not req.narrative_html or not req.narrative_html.strip():
        raise HTTPException(status_code=400, detail="narrative_html required")
    try:
        key = rag_narrative.learn_from_report(
            req.report, req.ctx_signals, req.narrative_html, archetype_key=req.archetype_key
        )
        return {"status": "stored", "archetype_key": key}
    except Exception as exc:  # noqa: BLE001
        log.exception("RAG learn failed")
        raise HTTPException(status_code=500, detail="RAG learning failed.") from exc


# ─── PDF Knowledge Base endpoints ────────────────────────────────────────────

class IngestPdfRequest(BaseModel):
    pdf_path: str = Field(..., description="Filename of the PDF in the approved uploads directory.")
    replace_existing: bool = Field(True, description="Replace previously stored chunks for this file.")


# Approved directory for PDF ingestion — configurable via env var
_PDF_UPLOAD_DIR = Path(os.getenv("PDF_UPLOAD_DIR", Path(__file__).parent.parent / "uploads" / "pdfs")).resolve()


def _resolve_pdf_upload_path(pdf_path: str) -> Path:
    """Accept a PDF filename only and keep resolution inside the approved directory."""
    requested = Path(pdf_path)
    if requested.is_absolute() or requested.name != pdf_path:
        raise HTTPException(status_code=400, detail="Provide a PDF filename only.")
    safe_path = (_PDF_UPLOAD_DIR / requested.name).resolve()
    if safe_path.parent != _PDF_UPLOAD_DIR:
        raise HTTPException(status_code=400, detail="Path traversal not allowed.")
    return safe_path


class QueryKbRequest(BaseModel):
    keywords: list[str] = Field(..., description="Oracle-domain terms to search for.")
    top_k: int = Field(5, ge=1, le=20)
    source_filter: str | None = Field(None, description="Limit to a specific source filename.")


class CrossCheckRequest(BaseModel):
    wait_events: list[str] = Field(default_factory=list)
    sql_type: str = ""
    issue_type: str = ""
    top_k: int = Field(4, ge=1, le=10)


@router.post("/ingest_pdf")
async def ingest_pdf(req: IngestPdfRequest) -> dict[str, Any]:
    """
    Ingest an Oracle documentation PDF into the knowledge base.
    Only files inside the approved uploads directory are accepted.
    """
    safe_path = _resolve_pdf_upload_path(req.pdf_path)
    if not safe_path.suffix.lower() == ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    if not safe_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found in approved uploads directory: {safe_path.name}.",
        )
    try:
        n = pdf_kb.ingest_pdf(str(safe_path), replace_existing=req.replace_existing)
        status = pdf_kb.kb_status()
        return {"status": "ok", "chunks_stored": n, "kb_status": status}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="PDF file could not be read.") from exc
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF ingestion dependency is unavailable. Install pdfplumber on the server.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("PDF ingestion failed")
        raise HTTPException(status_code=500, detail="PDF ingestion failed.") from exc


@router.get("/kb_status")
async def kb_status() -> dict[str, Any]:
    """Show what PDF knowledge is currently stored."""
    return pdf_kb.kb_status()


@router.post("/query_kb")
async def query_kb(req: QueryKbRequest) -> dict[str, Any]:
    """
    Keyword search against stored PDF knowledge chunks.
    Returns the most relevant chunks with their source, page, section and text.
    """
    if not req.keywords:
        raise HTTPException(status_code=400, detail="keywords list is required")
    results = pdf_kb.query_kb(req.keywords, top_k=req.top_k, source_filter=req.source_filter)
    return {"results": results, "count": len(results)}


@router.post("/cross_check")
async def cross_check(req: CrossCheckRequest) -> dict[str, Any]:
    """
    Derive keywords from AWR signals (wait events, SQL type, issue type) and
    retrieve the most relevant PDF guidance for that RCA scenario.
    """
    results = pdf_kb.cross_check_rca(
        wait_events=req.wait_events,
        sql_type=req.sql_type,
        issue_type=req.issue_type,
        top_k=req.top_k,
    )
    return {
        "results": results,
        "count": len(results),
        "prompt_text": pdf_kb.format_chunks_for_prompt(results),
    }
