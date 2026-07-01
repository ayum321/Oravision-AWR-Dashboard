"""
AI RCA Deep Analysis Router
============================
POST /api/ai-rca/analyze  — Stream AI-enhanced Oracle RCA analysis via NVIDIA API

The endpoint accepts a rich context payload (serialised from window.AWRContext in the
frontend), builds a structured Oracle Performance Engineering prompt, and streams
Gemma-4 thinking + response tokens back as newline-delimited JSON.

API key is read from the NVIDIA_API_KEY environment variable — never hardcoded.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Oracle PE Knowledge Base — distilled from Oracle Database Performance Tuning Guide 19c
try:
    from services.oracle_pe_kb import get_compact_knowledge_for_prompt, get_full_knowledge_base
except ImportError:
    try:
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
        from services.oracle_pe_kb import get_compact_knowledge_for_prompt, get_full_knowledge_base
    except ImportError:
        def get_compact_knowledge_for_prompt() -> str:
            return ""
        def get_full_knowledge_base() -> str:
            return ""

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-rca", tags=["ai-rca"])

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL       = "google/gemma-4-31b-it"     # both modes — thinking disabled in quick, enabled in deep
MODEL_QUICK = MODEL                         # same model, smaller output + no thinking


def _flt(v: Any, default: float = 0.0) -> float:
    """Safely convert any value to float, returning default on failure."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v: Any, default: int = 0) -> int:
    """Safely convert any value to int, returning default on failure."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ─── Controlled vocabulary ───────────────────────────────────────────────────

CONTROLLED_ROOT_CAUSES: frozenset = frozenset({
    "dbwr_throughput", "log_sync", "cpu_saturation", "sql_dominance",
    "io_latency", "latch_contention", "undo_pressure",
    "buffer_pool_contention", "parse_overhead", "network_latency", "checkpoint_pressure",
})

_BOTTLENECK_SYNONYMS: dict = {
    "free buffer":  "dbwr_throughput",
    "dbwr":         "dbwr_throughput",
    "buffer cache": "buffer_pool_contention",
    "log file sync":"log_sync",
    "redo":         "log_sync",
    "lgwr":         "log_sync",
    "cpu":          "cpu_saturation",
    "sql":          "sql_dominance",
    "io":           "io_latency",
    "disk":         "io_latency",
    "latch":        "latch_contention",
    "undo":         "undo_pressure",
    "checkpoint":   "checkpoint_pressure",
    "parse":        "parse_overhead",
    "network":      "network_latency",
}


# ─── Prompt Builder ──────────────────────────────────────────────────────────

def _fmt(v: Any, decimals: int = 1) -> str:
    try:
        return f"{float(v):,.{decimals}f}"
    except Exception:
        return str(v)


def _extract_normalized_facts(ctx: dict) -> dict:
    """
    Stage-1: Extract only normalized, meaningful metrics from AWR context.
    Returns compact JSON with deltas — no raw text, no noise.
    The LLM is forbidden from adding facts not present here.
    """
    meta         = ctx.get("meta") or {}
    aas_raw      = ctx.get("aas") or {}
    aas_bad      = _flt(aas_raw.get("bad") if isinstance(aas_raw, dict) else aas_raw)
    aas_good     = _flt(aas_raw.get("good") if isinstance(aas_raw, dict) else 0)
    cpus         = _int(meta.get("cpus") or 0)
    verdict      = ctx.get("verdict") or {}
    wait_events  = ctx.get("waitEvents") or {}
    ev_bad       = (wait_events.get("bad") if isinstance(wait_events, dict) else wait_events) or []
    ev_bad       = ev_bad if isinstance(ev_bad, list) else []
    ev_good      = (wait_events.get("good") if isinstance(wait_events, dict) else []) or []
    ev_good      = ev_good if isinstance(ev_good, list) else []
    top_sql_raw  = ctx.get("topSQL") or {}
    sql_bad      = (top_sql_raw.get("bad") if isinstance(top_sql_raw, dict) else top_sql_raw) or []
    sql_bad      = sql_bad if isinstance(sql_bad, list) else []
    load_profile = ctx.get("loadProfile") or {}
    lp_bad       = (load_profile.get("bad") if isinstance(load_profile, dict) else load_profile) or {}
    lp_good      = (load_profile.get("good") if isinstance(load_profile, dict) else {}) or {}
    time_model   = ctx.get("timeModel") or {}
    tm_bad       = (time_model.get("bad") if isinstance(time_model, dict) else time_model) or {}
    tm_good      = (time_model.get("good") if isinstance(time_model, dict) else {}) or {}
    bottleneck   = ctx.get("bottleneck") or {}
    addm         = ctx.get("addmFindings") or []
    addm         = addm if isinstance(addm, list) else []
    instance_eff = ctx.get("instanceEfficiency") or {}
    ie_bad       = (instance_eff.get("bad")  if isinstance(instance_eff, dict) else instance_eff) or {}
    ie_good      = (instance_eff.get("good") if isinstance(instance_eff, dict) else {}) or {}
    bt_bad       = bottleneck.get("bad") or {}
    bt_good      = bottleneck.get("good") or {}
    bt_type      = (bt_bad.get("type") or "") if isinstance(bt_bad, dict) else ""

    # Wait event deltas
    good_wait_map = {
        e.get("event_name", ""): _flt(e.get("pct_db_time") or e.get("pct"))
        for e in ev_good if isinstance(e, dict)
    }
    wait_facts = []
    for e in ev_bad[:8]:
        if not isinstance(e, dict):
            continue
        nm       = e.get("event_name") or ""
        pct      = _flt(e.get("pct_db_time") or e.get("pct"))
        ms       = _flt(e.get("avg_wait_ms") or e.get("avg_ms"))
        base_pct = good_wait_map.get(nm, 0.0)
        wait_facts.append({
            "event":            nm,
            "pct_db_time":      round(pct, 1),
            "avg_wait_ms":      round(ms, 2),
            "baseline_pct":     round(base_pct, 1),
            "delta_pp":         round(pct - base_pct, 1),
            "wait_class":       e.get("wait_class") or "",
            "is_new_in_problem": base_pct == 0 and pct > 0,
        })

    # Load profile — only significant deltas (>=25% change)
    # Skip the 25%-change filter when good=0 (single-AWR mode) to avoid 100% noise
    _is_single = not any(_flt(lp_good.get(k, 0)) > 0 for k in ["physical_reads", "logical_reads", "redo_size"])
    lp_facts: dict = {}
    for key in ["physical_reads", "logical_reads", "hard_parses", "soft_parses",
                "executes", "redo_size", "user_commits", "block_changes",
                "physical_writes", "transactions", "user_rollbacks"]:
        bv = _flt(lp_bad.get(key))  if isinstance(lp_bad, dict) else 0.0
        gv = _flt(lp_good.get(key)) if isinstance(lp_good, dict) else 0.0
        if bv > 0:
            if _is_single:
                # In single mode just report the absolute value — no delta comparison possible
                lp_facts[key] = {"baseline": None, "problem": round(bv, 1), "pct_change": None}
            else:
                pct_chg = round((bv - gv) / gv * 100, 0) if gv > 0 else 100.0
                if abs(pct_chg) >= 25:
                    lp_facts[key] = {"baseline": round(gv, 1), "problem": round(bv, 1), "pct_change": pct_chg}

    # Time model — only significant deltas (>=3 pp)
    tm_facts: dict = {}
    if isinstance(tm_bad, dict):
        for k, bv in tm_bad.items():
            if isinstance(bv, (int, float)):
                gv    = _flt(tm_good.get(k)) if isinstance(tm_good, dict) else 0.0
                delta = bv - gv
                if abs(delta) >= 3:
                    tm_facts[k] = {"baseline_pct": round(gv, 1), "problem_pct": round(bv, 1), "delta_pp": round(delta, 1)}

    # Top SQL
    sql_facts = []
    for s in sql_bad[:5]:
        if not isinstance(s, dict):
            continue
        flags = []
        if s.get("is_new")         or s.get("isNew"):       flags.append("NEW_IN_PROBLEM")
        if s.get("is_plan_change") or s.get("isPlanChg"):   flags.append("PLAN_CHANGE")
        if s.get("is_regressed")   or s.get("isRegressed"): flags.append("REGRESSED")
        sql_facts.append({
            "pct_db_time":          round(_flt(s.get("pct_db_time") or s.get("pctDb")), 1),
            "executions":           _int(s.get("executions") or s.get("execs")),
            "elapsed_s_per_exec":   round(_flt(s.get("elapsed_time_s") or s.get("elapsed_s")), 2),
            "buffer_gets_per_exec": round(_flt(s.get("buffer_gets_per_exec") or s.get("gets")), 0),
            "disk_reads_per_exec":  round(_flt(s.get("disk_reads_per_exec")  or s.get("disk")), 0),
            "flags": flags,
        })

    # Instance efficiency
    ie_facts: dict = {}
    for k in ["buffer_hit", "library_hit", "soft_parse_pct", "execute_to_parse",
              "parse_cpu_pct", "parse_cpu_to_elapsed_pct", "shared_pool_memory_usage_pct"]:
        bv = ie_bad.get(k)  if isinstance(ie_bad,  dict) else None
        gv = ie_good.get(k) if isinstance(ie_good, dict) else None
        if bv is not None and _flt(bv) > 0:
            delta = _flt(bv) - _flt(gv) if gv is not None else 0.0
            # Always include parse_cpu and shared_pool even if delta is small — they have special rules
            if k in ("parse_cpu_pct", "parse_cpu_to_elapsed_pct", "shared_pool_memory_usage_pct") or abs(delta) >= 2 or _flt(bv) < 90:
                ie_facts[k] = {"baseline": round(_flt(gv), 1) if gv is not None else None,
                                "problem": round(_flt(bv), 1), "delta": round(delta, 1)}

    # ADDM
    addm_facts = []
    for a in addm[:5]:
        if not isinstance(a, dict):
            continue
        impact = _flt(a.get("impact") or a.get("impact_pct") or 0)
        fname  = a.get("type") or a.get("finding") or a.get("finding_name") or ""
        rec    = a.get("recommendation") or ""
        addm_facts.append({"impact_pct": round(impact, 1), "finding": fname,
                            "recommendation": rec[:100] if rec else ""})

    # Deterministic verdict (ground truth for the LLM)
    det = {
        "root_cause":       verdict.get("rootCause") or verdict.get("root_cause") or bt_type or "",
        "severity":         verdict.get("severity") or "",
        "confidence":       round(_flt(verdict.get("confidence") or verdict.get("confidence_score") or 0), 0),
        "mechanism":        verdict.get("mechanism") or "",
        "action":           verdict.get("action") or "",
        "bottleneck_type":  bt_type,
        "bottleneck_baseline": (bt_good.get("type") or "") if isinstance(bt_good, dict) else "",
        "aas_baseline":     round(aas_good, 1),
        "aas_problem":      round(aas_bad, 1),
        "aas_delta_pct":    round((aas_bad - aas_good) / aas_good * 100, 0) if aas_good > 0 else None,
        "cpu_count":        cpus,
        "cpu_saturation_ratio": round(aas_bad / cpus, 2) if cpus > 0 else None,
    }

    return {
        "snapshot":              {"db_version": meta.get("db_version") or meta.get("version") or "",
                                  "elapsed_h": round(_flt(meta.get("elapsed_time") or 0), 2),
                                  "cpus": cpus,
                                  "aas_baseline": round(aas_good, 1),
                                  "aas_problem":  round(aas_bad,  1)},
        "deterministic_verdict": det,
        "wait_event_deltas":     wait_facts,
        "load_profile_deltas":   lp_facts,
        "time_model_deltas":     tm_facts,
        "top_sql":               sql_facts,
        "instance_efficiency":   ie_facts,
        "addm_findings":         addm_facts,
        # Enriched signals from classifyAndAnnotate (front-end derived)
        "sql_classifications":   ctx.get("sqlClassifications") or {},
        "workload_spikes":        ctx.get("workloadSpikes") or {},
        "conn_wait_pct":          ctx.get("connWaitPct") or {},
        "is_single_awr":         _is_single,
    }


def _run_contradiction_check(result: dict, facts: dict) -> dict:
    """
    Post-generation rule-based validator. Applied after JSON parse, before streaming result.

    Rules enforced:
    1. primary_bottleneck must be in controlled vocabulary.
    2. confidence is bounded by evidence count (cannot exceed 95).
    3. LLM cannot CONFLICT with a high-confidence deterministic verdict on thin evidence.
    4. Cleans evidence array structure.
    5. Normalises verdict_alignment → also writes deterministic_alignment for backward compat.
    """
    det      = facts.get("deterministic_verdict", {})
    det_root = str(det.get("root_cause", "")).lower()
    det_conf = _flt(det.get("confidence", 0))

    # 1. Validate / map primary_bottleneck to controlled vocabulary
    pb = str(result.get("primary_bottleneck", "")).lower()
    if pb not in CONTROLLED_ROOT_CAUSES:
        mapped = next((v for k, v in _BOTTLENECK_SYNONYMS.items() if k in pb), "")
        result["primary_bottleneck"] = (
            mapped or
            (det_root if det_root in CONTROLLED_ROOT_CAUSES else "io_latency")
        )
    # Keep root_cause in sync
    if not result.get("root_cause") or result["root_cause"] not in CONTROLLED_ROOT_CAUSES:
        result["root_cause"] = result["primary_bottleneck"]

    # 2. Bound confidence by evidence count (base 40 + 8 per evidence item, max 95)
    evidence = result.get("evidence", [])
    evidence = evidence if isinstance(evidence, list) else []
    max_conf = min(95, 40 + len(evidence) * 8)
    result["confidence"] = min(_int(result.get("confidence", 50)), max_conf)

    # 3. Alignment check: if deterministic has high confidence, LLM must not CONFLICT on thin evidence
    alignment = str(result.get("verdict_alignment") or result.get("deterministic_alignment") or "ALIGNED")
    if alignment not in ("ALIGNED", "MINOR_VARIANCE", "CONFLICT"):
        alignment = "ALIGNED"
    if det_conf >= 70 and alignment == "CONFLICT" and len(evidence) < 3:
        alignment = "MINOR_VARIANCE"
        result["alignment_note"] = (
            f"Deterministic engine confidence {int(det_conf)}% — divergence treated as minor variance. "
            + (result.get("alignment_note") or "")
        )[:120]
    result["verdict_alignment"]       = alignment
    result["deterministic_alignment"] = alignment  # backward compat

    # 4. Clean evidence array
    clean_ev = []
    for ev in evidence[:8]:
        if isinstance(ev, dict) and ev.get("metric"):
            clean_ev.append({
                "metric":       str(ev.get("metric",      ""))[:60],
                "value":        str(ev.get("value",       ""))[:40],
                "delta":        str(ev.get("delta",       ""))[:30] if ev.get("delta") else "",
                "significance": str(ev.get("significance",""))[:40],
            })
    result["evidence"] = clean_ev

    # 5. Ensure do_not_recommend is a clean list of strings
    dnr = result.get("do_not_recommend", [])
    result["do_not_recommend"] = [str(x)[:80] for x in (dnr if isinstance(dnr, list) else [])][:5]

    return result


def _build_oracle_prompt(ctx: dict) -> str:
    """
    Build a structured Oracle Performance Engineering prompt from the full
    AWRContext payload collected by the frontend.
    """
    meta          = ctx.get("meta") or {}
    db_name       = meta.get("db_name") or meta.get("db") or "Unknown"
    host          = meta.get("host") or "Unknown"
    instance      = meta.get("instance") or "N/A"
    snap_begin    = meta.get("snap_begin") or meta.get("snapBegin") or "?"
    snap_end      = meta.get("snap_end") or meta.get("snapEnd") or "?"
    elapsed_hrs   = _flt(meta.get("elapsed_time") or meta.get("elapsedTime"))
    cpus          = _int(meta.get("cpus"))
    db_version    = meta.get("db_version") or meta.get("version") or ""
    sga_gb        = _flt(meta.get("sga_size_gb") or meta.get("sgaGb"))
    pga_gb        = _flt(meta.get("pga_target_gb") or meta.get("pgaGb"))

    aas_raw       = ctx.get("aas")
    if isinstance(aas_raw, dict):
        aas_bad  = _flt(aas_raw.get("bad"))
        aas_good = _flt(aas_raw.get("good"))
    elif isinstance(aas_raw, (int, float, str)):
        aas_bad  = _flt(aas_raw)
        aas_good = 0.0
    else:
        aas_bad  = 0.0
        aas_good = 0.0

    time_model    = ctx.get("timeModel") or {}
    load_profile  = ctx.get("loadProfile") or {}
    wait_events   = ctx.get("waitEvents") or {}
    top_sql_raw   = ctx.get("topSQL") or ctx.get("sqlStats") or {}
    verdict       = ctx.get("verdict") or {}
    findings_raw  = ctx.get("findings") or []
    session_intel = ctx.get("sessionIntel") or ctx.get("sessionIntelligence") or {}
    addm          = ctx.get("addmFindings") or []
    instance_eff  = ctx.get("instanceEfficiency") or {}
    bottleneck    = ctx.get("bottleneck") or {}
    analysis      = ctx.get("analysis") or {}

    # Ensure lists are actually lists
    if not isinstance(findings_raw, list): findings_raw = []
    if not isinstance(addm, list): addm = []

    # Wait events may be split good/bad
    ev_bad  = wait_events.get("bad") if isinstance(wait_events, dict) else (wait_events if isinstance(wait_events, list) else [])
    ev_bad  = ev_bad if isinstance(ev_bad, list) else []
    ev_good = (wait_events.get("good") or []) if isinstance(wait_events, dict) else []
    ev_good = ev_good if isinstance(ev_good, list) else []

    # Top SQL may be split good/bad  
    sql_bad  = top_sql_raw.get("bad") or top_sql_raw.get("problem") or (top_sql_raw if isinstance(top_sql_raw, list) else [])
    sql_good = top_sql_raw.get("good") or top_sql_raw.get("baseline") or []

    # Load profile may be split
    lp_bad  = load_profile.get("bad") or load_profile.get("problem") or (load_profile if not isinstance(load_profile, dict) or "bad" not in load_profile else {})
    lp_good = load_profile.get("good") or load_profile.get("baseline") or {}

    # Time model may be split
    tm_bad  = time_model.get("bad") or time_model.get("problem") or (time_model if not isinstance(time_model, dict) or "bad" not in time_model else {})
    tm_good = time_model.get("good") or time_model.get("baseline") or {}

    lines: list[str] = []
    A = lines.append

    A("You are a senior Oracle Database Performance Engineer with 20+ years of expertise in AWR analysis, SQL tuning, wait event analysis, and Oracle internals.")
    A("You have access to the full AWR comparison data from an OraVision RCA engine. Your task is a deep, iterative analysis.")
    A("")
    # Inject Oracle PE knowledge base
    kb = get_full_knowledge_base()
    if kb:
        A(kb)
        A("")
    A("## DATABASE CONTEXT")
    A(f"Database: {db_name}  |  Host: {host}  |  Instance: {instance}")
    if db_version:
        A(f"Oracle Version: {db_version}")
    A(f"Snapshot Range: {snap_begin} → {snap_end}  |  Duration: {_fmt(elapsed_hrs)}h  |  CPUs: {cpus}")
    if sga_gb:
        A(f"SGA: {_fmt(sga_gb)}GB  |  PGA Target: {_fmt(pga_gb)}GB")
    A(f"Average Active Sessions — Baseline: {_fmt(aas_good)}  |  Problem: {_fmt(aas_bad)}")
    if cpus > 0:
        A(f"CPU Saturation: {'⚠ YES' if aas_bad > cpus else 'NO'} ({_fmt(aas_bad)}/{cpus} = {_fmt(aas_bad/cpus*100,0)}%)")
    A("")

    # Time model
    if tm_bad:
        A("## TIME MODEL (Problem Period)")
        items = list(tm_bad.items())[:12] if isinstance(tm_bad, dict) else []
        for k, v in items:
            if isinstance(v, (int, float)):
                A(f"  {k}: {_fmt(v)}%")
        if tm_good and isinstance(tm_good, dict):
            A("  [Baseline comparison]")
            for k, v in list(tm_good.items())[:6]:
                bv = tm_bad.get(k, 0) if isinstance(tm_bad, dict) else 0
                if isinstance(v, (int, float)) and isinstance(bv, (int, float)) and abs(bv - v) > 2:
                    A(f"  {k}: {_fmt(v)}% → {_fmt(bv)}% (delta: {_fmt(bv-v,1)}pp)")
        A("")

    # Load profile
    if lp_bad:
        A("## LOAD PROFILE (per second, Problem vs Baseline)")
        _lp_keys = [
            ("logical_reads", "Logical Reads"),
            ("physical_reads", "Physical Reads"),
            ("physical_writes", "Physical Writes"),
            ("hard_parses", "Hard Parses"),
            ("soft_parses", "Soft Parses"),
            ("executes", "Executions"),
            ("transactions", "Transactions"),
            ("redo_size", "Redo Size (bytes)"),
            ("user_commits", "User Commits"),
            ("user_rollbacks", "User Rollbacks"),
            ("block_changes", "Block Changes"),
            ("db_time", "DB Time (s)"),
        ]
        for key, label in _lp_keys:
            bv = lp_bad.get(key) if isinstance(lp_bad, dict) else None
            gv = lp_good.get(key) if isinstance(lp_good, dict) else None
            if bv is not None and _flt(bv) > 0:
                delta_str = ""
                if gv is not None and _flt(gv) > 0:
                    delta = (_flt(bv) - _flt(gv)) / _flt(gv) * 100
                    delta_str = f" (baseline: {_fmt(gv,0)}, delta: {_fmt(delta,0)}%)"
                A(f"  {label}: {_fmt(bv,0)}/s{delta_str}")
        A("")

    # Wait events
    if ev_bad:
        A("## TOP WAIT EVENTS — Problem Period")
        for i, e in enumerate(ev_bad[:12], 1):
            name    = e.get("event_name") or e.get("name") or ""
            pct     = _flt(e.get("pct_db_time") or e.get("pct"))
            avg_ms  = _flt(e.get("avg_wait_ms") or e.get("avg_ms"))
            waits   = _int(e.get("waits") or e.get("total_waits"))
            wcls    = e.get("wait_class") or ""
            A(f"  {i:2d}. [{wcls:18s}] {name}: {_fmt(pct)}% DB time | avg {_fmt(avg_ms)}ms | {waits:,} waits")
        if ev_good:
            A("  Baseline top events for comparison:")
            ev_good_map = {e.get("event_name",""): e for e in ev_good}
            for e in ev_bad[:5]:
                nm   = e.get("event_name","")
                b_pct = _flt(e.get("pct_db_time"))
                g_e  = ev_good_map.get(nm)
                g_pct = _flt(g_e.get("pct_db_time")) if g_e else 0.0
                if abs(b_pct - g_pct) > 1:
                    A(f"    {nm}: {_fmt(g_pct)}% → {_fmt(b_pct)}% (+{_fmt(b_pct-g_pct,1)}pp)")
        A("")

    # Oracle documentation cross-check — grounds the analysis in official
    # Oracle docs (Database Reference, SQL Tuning Guide) actually ingested
    # into the PDF knowledge base, keyed off the real dominant wait events
    # and the engine's own verdict so the LLM cites real sources instead of
    # inventing generic advice.
    try:
        from services import pdf_kb
        _wait_names = [
            (e.get("event_name") or e.get("name") or "") for e in ev_bad[:5]
        ]
        _issue_type = str(
            verdict.get("primary_bottleneck") or verdict.get("primaryBottleneck")
            or verdict.get("root_cause") or ""
        )
        _sql_type = ""
        if sql_bad:
            _first_sql_txt = (sql_bad[0].get("sql_text") or "").strip().upper()
            for _kw in ("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"):
                if _first_sql_txt.startswith(_kw):
                    _sql_type = _kw
                    break
        _pdf_chunks = pdf_kb.cross_check_rca(
            wait_events=_wait_names, sql_type=_sql_type, issue_type=_issue_type, top_k=4
        )
        _pdf_block = pdf_kb.format_chunks_for_prompt(_pdf_chunks, max_chars=1800)
        if _pdf_block:
            A(_pdf_block)
            A("Cross-reference the engine verdict and your analysis against the above official Oracle documentation. Cite the source file and page number when you rely on it. If the documentation contradicts the verdict, say so explicitly.")
            A("")
    except Exception:
        pass  # KB not available or query failed — proceed without it, never block analysis

    # Top SQL
    if sql_bad:
        A("## TOP SQL — Problem Period (by DB Time)")
        sql_good_map = {s.get("sql_id",""):s for s in sql_good} if sql_good else {}
        for i, s in enumerate(sql_bad[:10], 1):
            sid      = s.get("sql_id") or s.get("id") or ""
            pct      = _flt(s.get("pct_db_time") or s.get("pct_db"))
            elapsed  = _flt(s.get("elapsed_time_s") or s.get("elapsed_s") or s.get("elapsed"))
            execs    = _int(s.get("executions") or s.get("execs")) or 1
            cpu_pct  = _flt(s.get("cpu_pct"))
            gets     = _flt(s.get("buffer_gets_per_exec") or s.get("gets"))
            disk     = _flt(s.get("disk_reads_per_exec") or s.get("disk"))
            plan_chg = bool(s.get("planChg") or s.get("plan_change"))
            is_new   = bool(s.get("isNew") or s.get("is_new"))
            txt      = (s.get("sql_text") or "")[:120]
            flags    = (" [PLAN CHANGED]" if plan_chg else "") + (" [NEW SQL]" if is_new else "")
            A(f"  {i:2d}. [{sid}]{flags}")
            A(f"      {_fmt(pct)}% DB time | {_fmt(elapsed)}s elapsed | {execs:,} execs | {_fmt(elapsed/execs,3)}s/exec | {_fmt(cpu_pct)}% CPU | {_fmt(gets,0)} gets/exec | {_fmt(disk,0)} reads/exec")
            # Baseline comparison
            g = sql_good_map.get(sid)
            if g:
                g_pct   = _flt(g.get("pct_db_time"))
                g_exec  = _int(g.get("executions") or g.get("execs")) or 1
                g_gets  = _flt(g.get("buffer_gets_per_exec") or g.get("gets"))
                g_elapsed = _flt(g.get("elapsed_time_s") or g.get("elapsed_s"))
                A(f"      Baseline: {_fmt(g_pct)}% DB time | {_fmt(g_elapsed)}s elapsed | {g_exec:,} execs | {_fmt(g_gets,0)} gets/exec")
            if txt:
                A(f"      SQL: {txt}...")
        A("")

    # Engine verdict
    if verdict:
        pv = verdict.get("primary_bottleneck") or verdict.get("primaryBottleneck") or ""
        sev = verdict.get("severity") or ""
        conf = verdict.get("confidence_score") or verdict.get("confidenceScore") or verdict.get("confidence") or ""
        rc = verdict.get("root_cause") or verdict.get("rootCause") or ""
        mech = verdict.get("mechanism") or ""
        pf = verdict.get("primary_finding") or verdict.get("primaryFinding") or ""
        act = verdict.get("action") or ""
        A("## ORAVISION ENGINE VERDICT (validate and challenge this)")
        A(f"  Primary Bottleneck: {pv}")
        A(f"  Severity: {sev}  |  Confidence: {conf}")
        if pf:
            A(f"  Primary Finding: {pf}")
        if rc:
            A(f"  Root Cause: {rc}")
        if mech:
            A(f"  Mechanism: {mech}")
        if act:
            A(f"  Recommended Action: {act}")
        # Evidence chain
        chain = verdict.get("chain") or []
        if chain:
            A("  Evidence Chain:")
            for step in chain[:6]:
                if isinstance(step, dict):
                    A(f"    → {step.get('signal','')}: {step.get('label','')} {step.get('value','')} {step.get('unit','')}")
                else:
                    A(f"    → {step}")
        A("")

    # Findings
    if findings_raw:
        critical = [f for f in findings_raw if (f.get("severity") or "").lower() in ("critical", "warning")]
        if critical:
            A("## ENGINE FINDINGS")
            for f in critical[:8]:
                A(f"  [{(f.get('severity') or '').upper():8s}] {f.get('title','')} — {f.get('detail','')}")
            A("")

    # Bottleneck classification
    if bottleneck:
        A("## BOTTLENECK CLASSIFICATION")
        A(f"  Baseline: {bottleneck.get('goodLabel') or bottleneck.get('good',{}).get('type','')}")
        A(f"  Problem:  {bottleneck.get('badLabel') or bottleneck.get('bad',{}).get('type','')}")
        A(f"  Shifted:  {bottleneck.get('shifted', False)}")
        A("")

    # Instance efficiency
    ie_bad  = instance_eff.get("bad") or instance_eff
    ie_good = instance_eff.get("good") or {}
    if ie_bad and isinstance(ie_bad, dict) and ie_bad.get("buffer_hit"):
        A("## INSTANCE EFFICIENCY")
        for k in ["buffer_hit", "library_hit", "soft_parse_pct", "execute_to_parse", "parse_cpu_to_total"]:
            bv = ie_bad.get(k) if isinstance(ie_bad, dict) else None
            gv = ie_good.get(k) if isinstance(ie_good, dict) else None
            if bv is not None:
                comp = f" (baseline: {_fmt(_flt(gv))}%)" if gv is not None else ""
                A(f"  {k}: {_fmt(_flt(bv))}%{comp}")
        A("")

    # Session intelligence
    if session_intel:
        A("## SESSION INTELLIGENCE")
        for k, v in list(session_intel.items())[:10]:
            if v is not None and k not in ("raw", "_raw"):
                A(f"  {k}: {v}")
        A("")

    # ADDM
    if addm:
        A("## ADDM FINDINGS")
        for a in addm[:6]:
            impact = _flt(a.get("impact")) if isinstance(a, dict) else 0.0
            ftype  = a.get("type") or a.get("finding") or ""
            rec    = a.get("recommendation") or ""
            A(f"  [{_fmt(impact)}% impact] {ftype}")
            if rec:
                A(f"    Recommendation: {rec}")
        A("")

    # Top culprit from analysis
    top_culprit_id = analysis.get("topCulprit") or verdict.get("topCulprit",{})
    if isinstance(top_culprit_id, dict):
        top_culprit_id = top_culprit_id.get("sqlId") or ""
    if top_culprit_id:
        A(f"## TOP CULPRIT SQL: {top_culprit_id}")
        A(f"  Zone: {analysis.get('topCulpritZone','')}  |  Badge: {analysis.get('topCulpritBadge','')}  |  Mechanism: {analysis.get('mechanism','')}")
        A("")

    A("---")
    A("")
    A("## OUTPUT REQUIREMENTS")
    A("")
    A("You are an Oracle Performance Engineer. Analyse the data above and return ONLY valid JSON.")
    A("No markdown fences, no preamble text, no explanation outside the JSON structure.")
    A("Think carefully using your reasoning, but your FINAL OUTPUT must be ONLY the JSON object below.")
    A("")
    A("PRIVACY RULES — strictly enforced:")
    A("  - Replace any database name with: 'target database'")
    A("  - Replace any SQL ID / hash with: 'top SQL'")
    A("  - Omit host names entirely")
    A("  - Replace schema/table names with: 'target table' or 'monitored segment'")
    A("  - Use only generic Oracle terminology")
    A("")
    A("Return EXACTLY this JSON schema (no extra keys, no comments):")
    A('{')
    A('  "executive_summary": {')
    A('    "verdict": "<string, max 12 words, what happened and how severe>",')
    A('    "severity": "<CRITICAL|DEGRADED|WARNING|INFO>",')
    A('    "impact_score": <integer 0-100>,')
    A('    "confidence": <integer 0-100>,')
    A('    "primary_bottleneck": "<string, max 6 words>"')
    A('  },')
    A('  "findings": [')
    A('    {')
    A('      "metric": "<string, max 5 words>",')
    A('      "baseline": "<string, e.g. 1.2 AAS or 0.4ms>",')
    A('      "problem": "<string, e.g. 9.8 AAS or 12ms>",')
    A('      "delta_pct": <number, positive means worse>,')
    A('      "impact": "<HIGH|MEDIUM|LOW>",')
    A('      "severity": "<CRITICAL|WARNING|INFO>",')
    A('      "note": "<string, max 8 words, generic Oracle term only>"')
    A('    }')
    A('  ],')
    A('  "root_cause_chain": [')
    A('    {')
    A('      "step": <integer 1-4>,')
    A('      "type": "<TRIGGER|DRIVER|CASCADE|OUTCOME>",')
    A('      "label": "<string, max 6 words>",')
    A('      "detail": "<string, max 12 words>"')
    A('    }')
    A('  ],')
    A('  "priority_actions": [')
    A('    {')
    A('      "rank": <integer 1-5>,')
    A('      "action": "<string, max 10 words, generic Oracle command or parameter>",')
    A('      "expected_gain": "<string, max 8 words>",')
    A('      "effort": "<LOW|MEDIUM|HIGH>",')
    A('      "time_to_fix": "<immediate|hours|days>"')
    A('    }')
    A('  ],')
    A('  "gaps": "<string, max 15 words, what extra data would improve confidence>"')
    A('}')
    A("")
    A("HARD CONSTRAINTS:")
    A("  - findings: max 5 items")
    A("  - root_cause_chain: max 4 steps")
    A("  - priority_actions: max 5 items")
    A("  - impact_score: derive from (problem_AAS / cpu_count * 100), cap at 100")
    A("  - delta_pct: use positive number for degradation")
    A("  - severity CRITICAL if delta_pct > 100, WARNING if 20-100, INFO if < 20")
    A("  - every finding must be grounded in the metrics above — no invented data")
    A("  - root_cause_chain must name real Oracle internals (latch, segment, undo, etc.)")
    A("")
    A("Output ONLY the JSON. Start your response with '{' and end with '}'.")

    return "\n".join(lines)


def _build_quick_validate_prompt(ctx: dict, facts: dict | None = None) -> str:
    """
    Two-stage Oracle AWR analysis prompt.

    Stage 1 (done by caller): _extract_normalized_facts() pulls only compact,
    deterministic metrics from AWR context — no raw text dumps.

    Stage 2 (this function): LLM receives structured facts JSON + Oracle KB,
    and must narrate, validate, and rank actions from those facts ONLY.

    Architecture: deterministic engine decides severity/root label first;
    LLM explains and prioritises actions second. LLM must not invent metrics.
    """
    if facts is None:
        facts = _extract_normalized_facts(ctx)

    det       = facts.get("deterministic_verdict", {})
    det_conf  = _flt(det.get("confidence", 0))
    compact_kb = get_compact_knowledge_for_prompt()

    lines: list[str] = []
    A = lines.append

    # ── Role + Rules ──────────────────────────────────────────────────────────
    A("You are an Oracle AWR interpretation assistant.")
    A("You must ONLY reason from the metrics supplied in INPUT FACTS below.")
    A("Do not invent metric values. Do not recommend changes not supported by evidence.")
    A("If a metric is missing from the input facts, state 'insufficient evidence'.")
    if det_conf >= 70:
        A(f"The deterministic engine has already classified the root cause with {int(det_conf)}% confidence.")
        A("Explain that verdict. Do NOT replace it unless you have 3 or more conflicting hard-metric data points.")
    A("")

    # ── Oracle KB ─────────────────────────────────────────────────────────────
    if compact_kb:
        A("## ORACLE PERFORMANCE ENGINEERING REFERENCE")
        A(compact_kb)
        A("")

    A("---")
    A("")

    # ── Stage-1 Facts (compact normalized JSON) ───────────────────────────────
    A("## INPUT FACTS  (Stage-1 deterministic extraction — do NOT add facts beyond these)")
    A(json.dumps(facts, indent=2))
    A("")
    A("---")
    A("")

    # ── Decision policy ───────────────────────────────────────────────────────
    A("## DECISION POLICY")
    A("1. Pick exactly ONE primary_bottleneck from this controlled vocabulary:")
    A("   dbwr_throughput | log_sync | cpu_saturation | sql_dominance | io_latency |")
    A("   latch_contention | undo_pressure | buffer_pool_contention | parse_overhead | checkpoint_pressure")
    A("2. Every claim MUST cite an exact metric from the input facts above,")
    A("   e.g. 'free buffer waits = 58.9% DB time, +41pp vs baseline'.")
    A("3. List all supporting evidence as separate objects with metric + value + delta + significance.")
    A("4. Separate recommended_actions from do_not_recommend.")
    A("   Key traps: do NOT recommend increasing buffer_cache when DBWR is the bottleneck.")
    A("   Do NOT recommend disabling redo logging when log_sync is the bottleneck.")
    A("5. Compute confidence: base 40 + 8 per evidence item you list. Cap at 95.")
    A("6. WAIT EVENT CASCADE PRINCIPLE: Work on ONE event at a time. Actions must target the single")
    A("   top event by % DB time. Secondary events are often symptoms — name this in do_not_recommend.")
    A("7. PARSE CPU TO ELAPSED % INVERSION: if present in instance_efficiency, this metric is")
    A("   LOWER-IS-BETTER. Only flag as problematic if value < 10%. Near 100% = healthy.")
    A("8. SHARED POOL MEMORY USAGE %: healthy range = 60-85%. Flag <60% as oversized,")
    A("   >85% as pressure, >95% as critical (ORA-04031 risk).")
    A("9. COMMIT-IN-LOOP FINGERPRINT: if log file switch is top event AND redo_size is high")
    A("   AND physical_writes > physical_reads AND transactions/s is high")
    A("   → primary cause is commit-in-loop. Recommend moving COMMIT outside the loop first.")
    A("")
    A("---")
    A("")

    # ── Output schema ─────────────────────────────────────────────────────────
    A("## OUTPUT")
    A("Return ONLY valid JSON. No markdown fences. No preamble. Start with '{' end with '}'.")
    A("Every string field: plain text ONLY — no HTML tags, no markdown, no backticks.")
    A("")
    A("REQUIRED JSON SCHEMA:")
    schema = {
        "key_finding":      "<≤15 words — the single most important actionable fact. MUST cite a real metric value>",
        "primary_bottleneck": "<one token from controlled vocabulary above>",
        "what": "<2-3 sentences. MUST name exact wait event or SQL + its % DB time from the input facts>",
        "why":  "<2-3 sentences. Explain the Oracle internal chain: e.g. LGWR flush path, buffer eviction, etc.>",
        "risk": "<1-2 sentences. Operational consequence if unaddressed>",
        "actions": ["<ordered list of 3-5 specific DBA actions. Each must name exact Oracle param, view, or command>"],
        "do_not_recommend": ["<1-3 wrong actions a DBA might reach for — explain why they won't help>"],
        "evidence": [
            {"metric": "<exact name from input facts>", "value": "<exact value>",
             "delta": "<change vs baseline or 'single AWR'>", "significance": "primary|secondary|context"}
        ],
        "corrections": [
            {"area": "<≤5 words>", "dashboard_claim": "<what the dashboard said>",
             "actual_finding": "<what the data actually shows>", "severity": "CRITICAL|HIGH|MEDIUM"}
        ],
        "verdict_alignment": "<CONFIRMED|REFINED|OVERRIDDEN — does AI agree with the deterministic verdict?>",
        "alignment_note":    "<required if not CONFIRMED, else empty string>",
        "confidence":        "<integer 40-95>",
    }
    A(json.dumps(schema, indent=2))
    A("")
    A("CRITICAL RULES:")
    A("- key_finding, what, why MUST quote actual numbers from INPUT FACTS — never say 'significant increase' without a number")
    A("- actions: plain strings in a list — NOT objects. 3-5 items. Be specific (e.g. 'ALTER TABLE x MOVE TABLESPACE y')")
    A("- corrections: empty [] if the dashboard verdict is correct. Only flag provable mistakes.")
    A("- evidence: include every data point that supports your primary_bottleneck (min 2, max 6)")
    A("- Output ONLY the JSON. No explanation before or after.")

    return "\n".join(lines)


def _UNUSED_build_quick_validate_prompt_legacy(ctx: dict) -> str:
    """Legacy implementation — kept for reference only. Use _build_quick_validate_prompt."""
    meta         = ctx.get("meta") or {}
    aas_raw      = ctx.get("aas") or {}
    aas_bad      = _flt(aas_raw.get("bad") if isinstance(aas_raw, dict) else aas_raw)
    aas_good     = _flt(aas_raw.get("good") if isinstance(aas_raw, dict) else 0)
    cpus         = _int(meta.get("cpus") or 0)
    elapsed_h    = _flt(meta.get("elapsed_time") or 0)
    snap_begin   = meta.get("snap_begin") or meta.get("snapBegin") or ""
    snap_end     = meta.get("snap_end")   or meta.get("snapEnd")   or ""
    db_version   = meta.get("db_version") or meta.get("version") or ""

    verdict      = ctx.get("verdict") or {}
    findings_raw = ctx.get("findings") or []
    findings     = findings_raw if isinstance(findings_raw, list) else []
    wait_events  = ctx.get("waitEvents") or {}
    ev_bad       = (wait_events.get("bad") if isinstance(wait_events, dict) else wait_events) or []
    ev_bad       = ev_bad if isinstance(ev_bad, list) else []
    ev_good      = (wait_events.get("good") if isinstance(wait_events, dict) else []) or []
    ev_good      = ev_good if isinstance(ev_good, list) else []
    top_sql_raw  = ctx.get("topSQL") or {}
    sql_bad      = (top_sql_raw.get("bad") if isinstance(top_sql_raw, dict) else top_sql_raw) or []
    sql_bad      = sql_bad if isinstance(sql_bad, list) else []
    sql_good     = (top_sql_raw.get("good") if isinstance(top_sql_raw, dict) else []) or []
    sql_good     = sql_good if isinstance(sql_good, list) else []
    load_profile = ctx.get("loadProfile") or {}
    lp_bad       = (load_profile.get("bad") if isinstance(load_profile, dict) else load_profile) or {}
    lp_good      = (load_profile.get("good") if isinstance(load_profile, dict) else {}) or {}
    time_model   = ctx.get("timeModel") or {}
    tm_bad       = (time_model.get("bad") if isinstance(time_model, dict) else time_model) or {}
    tm_good      = (time_model.get("good") if isinstance(time_model, dict) else {}) or {}
    bottleneck   = ctx.get("bottleneck") or {}
    addm         = ctx.get("addmFindings") or []
    addm         = addm if isinstance(addm, list) else []
    instance_eff = ctx.get("instanceEfficiency") or {}
    analysis     = ctx.get("analysis") or {}
    session_intel = ctx.get("sessionIntel") or {}

    lines: list[str] = []
    A = lines.append

    A("You are an expert Oracle Performance Engineer. Analyse both baseline and problem AWR data below,")
    A("validate the automated dashboard findings, and produce an authoritative performance verdict.")
    A("You have deep knowledge of Oracle internals, AWR methodology, and all Oracle wait events.")
    A("")
    # Inject compact Oracle PE knowledge base
    compact_kb = get_compact_knowledge_for_prompt()
    if compact_kb:
        A(compact_kb)
        A("")
    A("---")
    A("")
    A("Using the Oracle PE knowledge above as your reference, now analyse the AWR data below:")
    A("")

    # ── Snapshot context ──────────────────────────────────────────────────────
    A("## SNAPSHOT CONTEXT")
    A(f"  Snap window : {snap_begin} → {snap_end}  ({_fmt(elapsed_h)}h elapsed)")
    if db_version:
        A(f"  Oracle version: {db_version}")
    A(f"  CPUs         : {cpus}")
    A(f"  AAS baseline : {_fmt(aas_good)}   |   AAS problem : {_fmt(aas_bad)}")
    if cpus > 0 and aas_bad > 0:
        ratio = aas_bad / cpus
        A(f"  CPU saturation: {'⚠ YES' if ratio > 1 else 'OK'} — {_fmt(ratio, 2)}× CPU count ({_fmt(aas_bad/cpus*100,0)}%)")
    A("")

    # ── Dashboard automated verdict ───────────────────────────────────────────
    # Use actual AWRContext field names (rootCause, severity, confidence, mechanism, action)
    sev       = verdict.get("severity") or ""
    confidence_raw = verdict.get("confidence") or verdict.get("confidence_score") or ""
    root_cause = verdict.get("rootCause") or verdict.get("root_cause") or ""
    mechanism  = verdict.get("mechanism") or ""
    action     = verdict.get("action") or ""
    top_culprit = verdict.get("topCulprit") or {}
    if isinstance(top_culprit, dict):
        top_culprit_id  = top_culprit.get("sqlId") or top_culprit.get("sql_id") or ""
        top_culprit_pct = _flt(top_culprit.get("pctDb") or top_culprit.get("pct_db_time"))
    else:
        top_culprit_id  = str(top_culprit) if top_culprit else ""
        top_culprit_pct = 0.0
    # Bottleneck classification
    bt_bad  = bottleneck.get("bad") or {}
    bt_good = bottleneck.get("good") or {}
    bt_type = bt_bad.get("type") or "" if isinstance(bt_bad, dict) else ""
    bt_shifted = bottleneck.get("shifted", False)

    A("## DASHBOARD AUTOMATED VERDICT (validate this)")
    A(f"  Severity          : {sev}")
    A(f"  Confidence        : {confidence_raw}")
    if root_cause:
        A(f"  Root cause        : {root_cause}")
    if mechanism:
        A(f"  Oracle mechanism  : {mechanism}")
    if action:
        A(f"  Recommended action: {action}")
    if bt_type:
        A(f"  Bottleneck type   : {bt_good.get('type','?') if isinstance(bt_good,dict) else '?'} (baseline) → {bt_type} (problem)  [shifted={bt_shifted}]")
    if top_culprit_id:
        A(f"  Top culprit SQL   : present ({_fmt(top_culprit_pct)}% DB time)")
    A("")

    # ── Dashboard findings ────────────────────────────────────────────────────
    if findings:
        A("## DASHBOARD ENGINE FINDINGS (validate each)")
        crit = [f for f in findings if (f.get("severity") or "").upper() in ("CRITICAL","WARNING","HIGH")]
        for f in (crit or findings)[:8]:
            sev_f  = (f.get("severity") or "").upper()
            title  = f.get("title") or ""
            detail = f.get("detail") or ""
            A(f"  [{sev_f}] {title}")
            if detail:
                A(f"         → {detail}")
        A("")

    # ── Wait events (baseline vs problem) ────────────────────────────────────
    A("## WAIT EVENTS — BASELINE (top 6)")
    for e in ev_good[:6]:
        nm  = e.get("event_name") or e.get("name") or ""
        pct = _flt(e.get("pct_db_time") or e.get("pct"))
        ms  = _flt(e.get("avg_wait_ms") or e.get("avg_ms"))
        A(f"  {_fmt(pct,1)}% DB time  avg {_fmt(ms,1)}ms   {nm}")
    A("")

    A("## WAIT EVENTS — PROBLEM (top 8)")
    for e in ev_bad[:8]:
        nm  = e.get("event_name") or e.get("name") or ""
        pct = _flt(e.get("pct_db_time") or e.get("pct"))
        ms  = _flt(e.get("avg_wait_ms") or e.get("avg_ms"))
        wcls = e.get("wait_class") or ""
        A(f"  {_fmt(pct,1)}% DB time  avg {_fmt(ms,1)}ms   {nm}  [{wcls}]")
    A("")

    # ── Time model ────────────────────────────────────────────────────────────
    if tm_bad and isinstance(tm_bad, dict):
        A("## TIME MODEL — PROBLEM vs BASELINE")
        for k, bv in list(tm_bad.items())[:8]:
            if isinstance(bv, (int, float)):
                gv = _flt(tm_good.get(k)) if isinstance(tm_good, dict) else 0
                delta = bv - gv
                if abs(delta) > 1:
                    sign = "+" if delta >= 0 else ""
                    A(f"  {k}: {_fmt(gv,1)}% → {_fmt(bv,1)}%  (Δ {sign}{_fmt(delta,1)}pp)")
        A("")

    # ── Load profile ──────────────────────────────────────────────────────────
    A("## LOAD PROFILE DELTA (baseline → problem)")
    for key, label in [
        ("physical_reads","Physical reads/s"), ("logical_reads","Logical reads/s"),
        ("hard_parses","Hard parses/s"),       ("soft_parses","Soft parses/s"),
        ("executes","Executes/s"),             ("redo_size","Redo bytes/s"),
        ("user_commits","Commits/s"),          ("block_changes","Block changes/s"),
    ]:
        bv = _flt(lp_bad.get(key)) if isinstance(lp_bad, dict) else 0
        gv = _flt(lp_good.get(key)) if isinstance(lp_good, dict) else 0
        if bv > 0 or gv > 0:
            delta = ((bv - gv) / gv * 100) if gv > 0 else 0
            marker = " ⚠" if abs(delta) > 50 else ""
            sign = "+" if delta >= 0 else ""
            A(f"  {label}: {_fmt(gv,0)} → {_fmt(bv,0)}  ({sign}{_fmt(delta,0)}%){marker}")
    A("")

    # ── Instance efficiency ───────────────────────────────────────────────────
    ie_bad  = (instance_eff.get("bad")  if isinstance(instance_eff, dict) and "bad"  in instance_eff else instance_eff) or {}
    ie_good = (instance_eff.get("good") if isinstance(instance_eff, dict) and "good" in instance_eff else {}) or {}
    if ie_bad and isinstance(ie_bad, dict):
        A("## INSTANCE EFFICIENCY (baseline → problem)")
        for k in ["buffer_hit", "library_hit", "soft_parse_pct", "execute_to_parse", "parse_cpu_to_total"]:
            bv = ie_bad.get(k)
            gv = ie_good.get(k)
            if bv is not None:
                delta = _flt(bv) - _flt(gv) if gv is not None else 0
                marker = " ⚠" if abs(delta) > 5 else ""
                A(f"  {k}: {_fmt(_flt(gv),1)}% → {_fmt(_flt(bv),1)}%{marker}")
        A("")

    # ── Top SQL ───────────────────────────────────────────────────────────────
    if sql_bad:
        A("## TOP SQL — PROBLEM (anonymised)")
        for i, s in enumerate(sql_bad[:6], 1):
            pct_db  = _flt(s.get("pct_db_time") or s.get("pctDb"))
            elapsed = _flt(s.get("elapsed_time_s") or s.get("elapsed_s"))
            execs   = _int(s.get("executions") or s.get("execs"))
            gets    = _flt(s.get("buffer_gets_per_exec") or s.get("gets"))
            flags   = []
            if s.get("is_new")  or s.get("isNew"):     flags.append("NEW-IN-PROBLEM")
            if s.get("is_plan_change") or s.get("isPlanChg"):  flags.append("PLAN-CHANGE")
            if s.get("is_regressed")   or s.get("isRegressed"): flags.append("REGRESSED")
            flag_str = " [" + ", ".join(flags) + "]" if flags else ""
            A(f"  #{i}: {_fmt(pct_db,1)}% DBtime | {_fmt(elapsed,1)}s elapsed | {execs:,} execs | {_fmt(gets,0)} gets/exec{flag_str}")
        A("")

    # ── ADDM ──────────────────────────────────────────────────────────────────
    if addm:
        A("## ADDM FINDINGS (Oracle auto-diagnosis)")
        for a in addm[:6]:
            impact = _flt(a.get("impact") or a.get("impact_pct") or 0)
            fname  = a.get("type") or a.get("finding") or a.get("finding_name") or ""
            rec    = a.get("recommendation") or ""
            A(f"  {_fmt(impact,1)}% impact — {fname}")
            if rec:
                A(f"    Oracle recommendation: {rec}")
        A("")

    A("=" * 60)
    A("")
    A("TASK: You are producing the authoritative Intelligence Review for this AWR comparison.")
    A("      Validate the automated dashboard findings against the raw AWR metrics.")
    A("      Then produce a structured conclusion: WHAT happened, WHY it happened (Oracle internals),")
    A("      RISK level if left unfixed, and precise ACTIONS the DBA must take.")
    A("      Look for: wrong severity, missed bottleneck, wrong Oracle mechanism, missed root cause,")
    A("      wrong SQL attribution, or any finding contradicted by the metrics.")
    A("")
    A("PRIVACY RULES — strictly enforced:")
    A("  - Never use any database name, SQL ID, host name, schema name, or table name.")
    A("  - Refer to SQL as 'top SQL statement', 'dominant workload SQL', 'problem SQL'.")
    A("  - Use generic Oracle terminology only.")
    A("")
    A("Return ONLY valid JSON. No markdown fences. No HTML tags. No preamble. Start with '{' end with '}'.")
    A("")
    A("STRICT JSON SCHEMA (all string values must be plain text — NO HTML, NO markdown, NO backticks):")
    A('{')
    A('  "what": "<string: 2-3 sentences. What happened during this AWR window. Name the primary wait event, % DB time, and AAS delta. Plain text only.>",')
    A('  "why": "<string: 2-3 sentences. The Oracle internal mechanism that caused it — name the exact Oracle construct (latch, segment, DBWR, log writer, buffer pool, etc.). Explain the causal chain. Plain text only.>",')
    A('  "risk": "<string: 1-2 sentences. Business/operational risk if this is not addressed. Include estimated AAS headroom before saturation.>",')
    A('  "actions": [')
    A('    {')
    A('      "rank": <integer 1-5>,')
    A('      "do": "<string ≤15 words — specific Oracle parameter, view query, or DBA command. Generic Oracle terms only.>",')
    A('      "do_not": "<string ≤12 words — a common but wrong action to avoid, or empty string>",')
    A('      "expected_gain": "<string ≤10 words — measurable outcome>",')
    A('      "effort": "<immediate|hours|days>",')
    A('      "evidence_source": "<string ≤8 words — which AWR section supports this action>"')
    A('    }')
    A('  ],')
    A('  "signals_used": ["<signal name>"],')
    A('  "signals_missing": ["<signal name if not available>"],')
    A('  "conclusion": "<string: 3-4 sentences combining WHAT+WHY+RISK in plain English for the DBA. Embed actual metric values. Plain text only.>",')
    A('  "verdict_validation": "<CONFIRMED | PARTIALLY_CORRECT | INCORRECT | INCONCLUSIVE>",')
    A('  "deterministic_alignment": "<ALIGNED | MINOR_VARIANCE | CONFLICT>",')
    A('  "alignment_note": "<string ≤20 words — only if MINOR_VARIANCE or CONFLICT: what specifically differs between deterministic and LLM verdict>",')
    A('  "dashboard_status": "<ACCURATE | HAS_CORRECTIONS | INCONCLUSIVE>",')
    A('  "key_finding": "<string ≤12 words: the single most important thing the DBA needs to know>",')
    A('  "validated_claims": [')
    A('    {')
    A('      "claim": "<string ≤10 words — something the dashboard stated correctly>",')
    A('      "evidence": "<string ≤12 words — which AWR metric confirms it>"')
    A('    }')
    A('  ],')
    A('  "corrections": [')
    A('    {')
    A('      "area": "<string ≤5 words — e.g. Wait Classification, SQL Attribution, Severity Assessment>",')
    A('      "dashboard_claim": "<string ≤12 words — what the dashboard concluded about this area>",')
    A('      "actual_finding": "<string ≤15 words — what the AWR data actually shows>",')
    A('      "why_it_matters": "<string ≤12 words — why this correction changes the action plan>",')
    A('      "severity": "<CRITICAL|HIGH|MEDIUM>"')
    A('    }')
    A('  ],')
    A('  "confidence": <integer 0-100>')
    A('}')
    A("")
    A("RULES:")
    A("  - what / why / risk / conclusion: plain text ONLY — absolutely no HTML tags or markdown")
    A("  - actions: max 5 items ranked by urgency; rank 1 = most urgent")
    A("  - do_not: use empty string '' when no anti-pattern applies")
    A("  - signals_used: list the AWR sections you used, e.g. [\"Wait Events\", \"Load Profile\", \"Top SQL\", \"Time Model\", \"Instance Efficiency\", \"ADDM\"]")
    A("  - signals_missing: list important data not available, e.g. [\"IO latency stats\", \"segment-level stats\"]")
    A("  - validated_claims: 2-4 things the dashboard got RIGHT")
    A("  - corrections: ONLY items where dashboard is WRONG or MISLEADING — empty array [] if none")
    A("  - verdict_validation CONFIRMED if all key findings are correct, PARTIALLY_CORRECT if some are wrong")
    A("  - deterministic_alignment: ALIGNED if LLM agrees with the engine verdict, CONFLICT if materially different")
    A("  - alignment_note: required for MINOR_VARIANCE or CONFLICT; empty string for ALIGNED")
    A("  - dashboard_status ACCURATE if no corrections, HAS_CORRECTIONS if corrections[] is non-empty")
    A("  - key_finding must be actionable for the DBA, not a restatement of severity")
    A("  - evidence_source must map to one of: Wait Events, Load Profile, Top SQL, Time Model, Instance Efficiency, ADDM, Session Intel")
    A("")
    A("Output ONLY the JSON object.")

    return "\n".join(lines)


# ─── NVIDIA Streaming ────────────────────────────────────────────────────────

async def _stream_nvidia(prompt: str, api_key: str, quick: bool = False) -> AsyncIterator[str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
    }
    # Quick mode uses a small always-warm model for low latency.
    # Deep mode uses gemma-4-31b-it with thinking enabled.
    model = MODEL_QUICK if quick else MODEL
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096 if quick else 16384,
        "temperature": 0.2 if quick else 0.3,
        "top_p": 0.9,
        "stream": True,
    }
    # enable_thinking only for deep mode on gemma-4 (other models don't support it)
    if not quick:
        payload["chat_template_kwargs"] = {"enable_thinking": True}

    content_buf: list[str] = []

    # Both modes use generous timeouts. gemma-4-31b can take 60-90s on first call (cold model).
    timeout = httpx.Timeout(240.0, connect=30.0) if quick else httpx.Timeout(360.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", NVIDIA_API_URL, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                log.warning("NVIDIA API error %s: %s", resp.status_code, body.decode(errors="replace")[:500])
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"NVIDIA API request failed with status {resp.status_code}.",
                )
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj   = json.loads(data)
                        delta = obj.get("choices", [{}])[0].get("delta", {})
                        thinking = delta.get("reasoning_content") or delta.get("thinking") or ""
                        content  = delta.get("content") or ""
                        if thinking:
                            if not quick:   # suppress thinking in quick mode
                                yield json.dumps({"type": "thinking", "text": thinking}) + "\n"
                        if content:
                            content_buf.append(content)  # buffer — emit as parsed JSON at end
                    except Exception:
                        pass

    # Parse the buffered JSON response
    full_content = "".join(content_buf).strip()
    # Strip markdown fences (```json ... ```) if the model wrapped its output
    json_text = re.sub(r'^```[a-zA-Z]*\s*', '', full_content)
    json_text = re.sub(r'\s*```\s*$', '', json_text).strip()
    # If model added preamble before '{', extract from first '{'
    brace_idx = json_text.find('{')
    if brace_idx > 0:
        json_text = json_text[brace_idx:]
    try:
        parsed = json.loads(json_text)
        yield json.dumps({"type": "result", "data": parsed}) + "\n"
    except Exception as exc:
        log.warning("AI JSON parse failed: %s | raw=%s", exc, full_content[:300])
        yield json.dumps({"type": "error", "text": "AI response was not valid JSON."}) + "\n"


# ─── Endpoint ────────────────────────────────────────────────────────────────

class AIAnalysisRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    quick: bool = False   # quick=True → PE Narrative validation (no thinking, smaller output)


@router.post("/analyze")
async def analyze(req: AIAnalysisRequest):
    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="NVIDIA_API_KEY environment variable is not set. Configure it before using AI analysis.",
        )

    if req.quick:
        # Two-stage: extract normalized facts first, then build prompt from those facts only
        facts = _extract_normalized_facts(req.context)
        prompt = _build_quick_validate_prompt(req.context, facts)
        log.info("AI RCA quick-validate (two-stage) — prompt %d chars, %d wait events, %d sql",
                 len(prompt),
                 len(facts.get("wait_event_deltas", [])),
                 len(facts.get("top_sql", [])))
    else:
        facts = None
        prompt = _build_oracle_prompt(req.context)
        log.info("AI RCA deep analysis — prompt %d chars, model %s", len(prompt), MODEL)

    async def generate():
        try:
            async for chunk in _stream_nvidia(prompt, api_key, quick=req.quick):
                # Apply contradiction check on the result chunk for quick-mode analysis
                if req.quick and facts and chunk.strip():
                    try:
                        obj = json.loads(chunk.strip())
                        if obj.get("type") == "result" and isinstance(obj.get("data"), dict):
                            obj["data"] = _run_contradiction_check(obj["data"], facts)
                            yield json.dumps(obj) + "\n"
                            continue
                    except (json.JSONDecodeError, Exception):
                        pass
                yield chunk
        except HTTPException as e:
            yield json.dumps({"type": "error", "text": e.detail}) + "\n"
        except Exception as e:
            log.exception("AI RCA stream error")
            yield json.dumps({"type": "error", "text": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
