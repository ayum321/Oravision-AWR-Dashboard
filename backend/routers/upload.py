"""AWR HTML file upload, parsing, and analysis endpoints."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
import asyncio
import concurrent.futures
import logging

from services.html_parser import parse_awr_html, normalize_parsed_data
from services.health_scorer import calculate_health_score
from services.comparator import compare_periods
from services.recommendations import generate_single_report_recommendations, generate_recommendations
from services.dot_connector import analyze_awr_data, analyze_comparison
from services.rca_engine import run_rca, run_comparison_rca
from services.awr_intelligence import run_intelligence, run_intelligence_compare, _CACHE as _intelligence_cache
from services.data_source import get_uploaded_data, list_uploaded_data, normalize_upload_label, store_uploaded_data
from services.advanced_analytics import compute_single_analytics

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/upload", tags=["upload"])
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _parse_and_store(html_content: str, label: str) -> dict:
    """Parse HTML content and store the result. Returns the parsed data dict."""
    raw = parse_awr_html(html_content)
    if not raw.get("db_name") or not raw.get("begin_snap"):  # FIX: OR not AND — either missing = invalid
        raise HTTPException(400, "Could not parse AWR data. Ensure it is a valid Oracle AWR HTML report.")

    awr_model = normalize_parsed_data(raw)
    data_dict = awr_model.model_dump()

    # Preserve extra parsed fields not in the Pydantic model
    data_dict["addm_findings"] = raw.get("addm_findings", [])
    data_dict["_foreground_wait_events"] = raw.get("_foreground_wait_events", [])
    data_dict["_wait_classes"] = raw.get("_wait_classes", [])
    data_dict["_latch_activity"] = raw.get("_latch_activity", [])
    data_dict["_instance_activity"] = raw.get("_instance_activity", [])
    data_dict["_tablespace_io"] = raw.get("_tablespace_io", [])
    data_dict["_ash_activity"] = raw.get("_ash_activity", [])
    data_dict["_wait_histogram"] = raw.get("_wait_histogram", [])
    data_dict["_buffer_cache_advisory"] = raw.get("_buffer_cache_advisory", [])
    data_dict["_shared_pool_advisory"] = raw.get("_shared_pool_advisory", [])
    data_dict["_pga_advisory"] = raw.get("_pga_advisory", [])
    data_dict["_sql_registry"] = raw.get("_sql_registry", {})
    data_dict["_sql_text_map"] = raw.get("_sql_text_map", {})
    # Session/logon metrics (ensure they survive even if model didn't capture them)
    for _lf in ("logons_cumulative_total", "logons_current_begin", "logons_current_end"):
        if raw.get(_lf) is not None and data_dict.get(_lf) is None:
            data_dict[_lf] = raw[_lf]

    store_uploaded_data(label, data_dict)
    return data_dict


_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB — generous for AWR HTML reports


@router.post("/awr")
async def upload_awr_html(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    label: str = Form("uploaded"),
):
    """Upload a single AWR HTML report file and get full analysis."""
    try:
        label = normalize_upload_label(label)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not file.filename.lower().endswith(('.html', '.htm')):
        raise HTTPException(400, "Only HTML files are supported")

    # Stream upload with size limit — reject before buffering the entire file
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)  # 64 KB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                413,
                f"File too large (>{_MAX_UPLOAD_BYTES // (1024*1024)} MB). "
                "AWR HTML reports are typically under 10 MB.",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    # Try strict UTF-8 first; Oracle AWR exports are always UTF-8 or Latin-1
    try:
        html_str = content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            html_str = content.decode('latin-1')
        except Exception:
            raise HTTPException(400, "File encoding not supported. Please upload a UTF-8 or Latin-1 AWR HTML report.")

    data_dict = _parse_and_store(html_str, label)

    # Calculate health score
    health = calculate_health_score(data_dict)

    # Generate recommendations
    recs = generate_single_report_recommendations(data_dict)

    # AI dot-connector analysis
    insights = analyze_awr_data(data_dict)

    # Run RCA engine
    rca_result = run_rca(data_dict)

    # Run the same analytics engines used by compare mode (minus delta layers)
    analytics = compute_single_analytics(data_dict)

    # Fire intelligence pipeline in background
    _lbl, _dd = label, data_dict

    async def _run_intelligence():
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, lambda: run_intelligence(_lbl, _dd))
        log.info("Intelligence analysis complete for %s", _lbl)

    background_tasks.add_task(_run_intelligence)

    return {
        "status": "ok",
        "upload_id": label,
        "db_name": data_dict.get("db_name", ""),
        "instance": data_dict.get("instance", ""),
        "snap_range": f"{data_dict.get('begin_snap', '?')} - {data_dict.get('end_snap', '?')}",
        "begin_time": data_dict.get("begin_time", ""),
        "end_time": data_dict.get("end_time", ""),
        "elapsed_min": data_dict.get("elapsed_min", 0),
        "db_time_min": data_dict.get("db_time_min", 0),
        "health": health,
        "recommendations": [r.model_dump() for r in recs],
        "insights": insights,
        "rca": rca_result,
        "data": data_dict,
        "analytics": analytics,
        "intelligence_status": "running",   # analysis fires in background
    }


@router.post("/compare")
async def upload_and_compare(
    background_tasks: BackgroundTasks,
    good_file: UploadFile = File(...),
    bad_file: UploadFile = File(...),
):
    """Upload two AWR HTML reports (good + bad) and get a full comparison."""
    _MAX_MB = 80
    _MAX_BYTES = _MAX_MB * 1024 * 1024

    for f, name in [(good_file, "good_file"), (bad_file, "bad_file")]:
        if not (f.filename or "").lower().endswith(('.html', '.htm')):
            raise HTTPException(400, f"{name}: Only HTML files are supported (.html / .htm)")

    async def _stream_file(f: UploadFile, name: str) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await f.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_BYTES:
                raise HTTPException(413, f"{name}: File too large (>{_MAX_MB} MB).")
            chunks.append(chunk)
        return b"".join(chunks)

    good_content = await _stream_file(good_file, good_file.filename or "good_file")
    bad_content = await _stream_file(bad_file, bad_file.filename or "bad_file")

    # Lightweight AWR signature check
    for content, name in [(good_content, good_file.filename), (bad_content, bad_file.filename)]:
        sample = content[:4096]
        try:
            sample_str = sample.decode('utf-8', errors='replace')
        except Exception:
            sample_str = sample.decode('latin-1', errors='replace')
        if 'WORKLOAD REPOSITORY' not in sample_str.upper() and 'AWR' not in sample_str.upper():
            raise HTTPException(400, f"{name}: File does not appear to be an Oracle AWR HTML report.")

    try:
        good_html = good_content.decode('utf-8', errors='replace')
    except Exception:
        good_html = good_content.decode('latin-1', errors='replace')

    try:
        bad_html = bad_content.decode('utf-8', errors='replace')
    except Exception:
        bad_html = bad_content.decode('latin-1', errors='replace')

    try:
        good_dict = _parse_and_store(good_html, "uploaded_good")
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Failed to parse good (baseline) AWR file")
        raise HTTPException(422, "Could not parse baseline AWR file. Check server logs for details.") from exc

    try:
        bad_dict = _parse_and_store(bad_html, "uploaded_bad")
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Failed to parse bad (problem) AWR file")
        raise HTTPException(422, "Could not parse problem AWR file. Check server logs for details.") from exc

    # Clear stale intelligence cache for previous uploads (prevents returning old analysis)
    for _key in ["uploaded_good", "uploaded_bad", "uploaded_good_vs_uploaded_bad"]:
        _intelligence_cache.pop(_key, None)

    try:
        # Compare
        report = compare_periods(good_dict, bad_dict)

        # Health scores
        health_good = calculate_health_score(good_dict)
        health_bad = calculate_health_score(bad_dict)

        # Recommendations
        recs = generate_recommendations(good_dict, bad_dict)

        # AI dot-connector analysis
        insights = analyze_comparison(good_dict, bad_dict, report.model_dump())

        # Run comparison RCA engine
        label1 = good_file.filename or "Period 1"
        label2 = bad_file.filename or "Period 2"
        comparison_rca = run_comparison_rca(good_dict, bad_dict, label1, label2)
    except Exception as exc:
        log.exception("Comparison analysis failed")
        raise HTTPException(500, "Comparison analysis failed. Check server logs for details.") from exc

    # Fire comparison intelligence in background (failure here must not affect response)
    _gd, _bd = good_dict, bad_dict

    async def _run_compare_intelligence():
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                _executor,
                lambda: run_intelligence_compare("uploaded_good", "uploaded_bad", _gd, _bd)
            )
            log.info("Comparison intelligence analysis complete")
        except Exception:
            log.exception("Background intelligence analysis failed (non-fatal)")

    background_tasks.add_task(_run_compare_intelligence)

    return {
        "status": "ok",
        "good_upload_id": "uploaded_good",
        "bad_upload_id": "uploaded_bad",
        "report": report.model_dump(),
        "health_good": health_good,
        "health_bad": health_bad,
        "recommendations": [r.model_dump() for r in recs],
        "insights": insights,
        "comparison_rca": comparison_rca,
        "good_data": good_dict,
        "bad_data": bad_dict,
        "intelligence_status": "running",
    }



@router.get("/analyze/{upload_id}")
async def analyze_upload(upload_id: str):
    """Get full analysis for a previously uploaded report."""
    data = get_uploaded_data(upload_id)
    if data is None:
        raise HTTPException(404, "Upload not found. Upload a file first.")
    health = calculate_health_score(data)
    recs = generate_single_report_recommendations(data)
    insights = analyze_awr_data(data)
    rca_result = run_rca(data)

    return {
        "upload_id": upload_id,
        "health": health,
        "recommendations": [r.model_dump() for r in recs],
        "insights": insights,
        "rca": rca_result,
        "data": data,
    }


@router.get("/compare/stored")
async def compare_stored():
    """Compare previously uploaded good vs bad reports."""
    good_dict = get_uploaded_data("uploaded_good")
    bad_dict = get_uploaded_data("uploaded_bad")
    if good_dict is None or bad_dict is None:
        raise HTTPException(404, "Upload both good and bad reports first via POST /api/upload/compare")

    report = compare_periods(good_dict, bad_dict)
    health_good = calculate_health_score(good_dict)
    health_bad = calculate_health_score(bad_dict)
    recs = generate_recommendations(good_dict, bad_dict)
    insights = analyze_comparison(good_dict, bad_dict, report.model_dump())
    comparison_rca = run_comparison_rca(good_dict, bad_dict, "Period 1", "Period 2")

    return {
        "report": report.model_dump(),
        "health_good": health_good,
        "health_bad": health_bad,
        "recommendations": [r.model_dump() for r in recs],
        "insights": insights,
        "comparison_rca": comparison_rca,
    }


@router.get("/list")
async def list_uploads():
    """List all uploaded AWR data."""
    return {"uploads": [
        {
            "upload_id": k,
            "db_name": v.get("db_name", ""),
            "instance": v.get("instance", ""),
            "snap_range": f"{v.get('begin_snap','?')}-{v.get('end_snap','?')}",
            "elapsed_min": v.get("elapsed_min", 0),
            "db_time_min": v.get("db_time_min", 0),
        }
        for k, v in list_uploaded_data()
    ]}
