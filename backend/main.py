"""
OraVision AWR Pro — Oracle AWR Performance Dashboard API
FastAPI backend with AWR comparison engine, health scoring, and recommendations.
Serves both the API and the HTML frontend via Jinja2 templates.
"""
import sys
import os
import hmac
import logging
import traceback
from pathlib import Path

# Ensure backend directory is in path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env file if present (supports NVIDIA_API_KEY and other secrets)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        # dotenv not installed — parse manually
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from routers import snapshots, compare, sql_analysis, wait_events, upload, recommendations, intelligence, rag, ai_rca, memory, kb
from services.data_source import resolve_period_or_404

log = logging.getLogger(__name__)

app = FastAPI(
    title="OraVision AWR Tool API",
    description="Oracle AWR Performance Dashboard — Compare, Analyze, Optimize",
    version="3.0.0",
)

# CORS for API consumers
# Defaults to localhost only; override with CORS_ORIGINS env var for production
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional API-key guard for hosted environments. Localhost start.bat remains
# frictionless unless ORAVISION_API_KEY is explicitly configured.
class _ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        required_key = os.getenv("ORAVISION_API_KEY", "").strip()
        if required_key and request.url.path.startswith("/api") and request.method != "OPTIONS":
            supplied_key = request.headers.get("x-api-key", "").strip()
            authorization = request.headers.get("authorization", "").strip()
            if authorization.lower().startswith("bearer "):
                supplied_key = authorization[7:].strip()
            if not supplied_key or not hmac.compare_digest(supplied_key, required_key):
                return JSONResponse(
                    status_code=401,
                    content={"error": "unauthorized", "detail": "A valid API key is required."},
                )
        return await call_next(request)


app.add_middleware(_ApiKeyMiddleware)

# ─── Global exception safety net ─────────────────────────────────────────────
# Catches ANY unhandled Python exception in any endpoint and returns a JSON
# 500 response instead of dropping the TCP connection (which causes the browser
# to show "NetworkError when attempting to fetch resource").
class _CatchAllMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except HTTPException:
            # Let FastAPI's own exception handler return the correct 4xx status.
            raise
        except Exception as exc:
            tb = traceback.format_exc()
            log.error("Unhandled exception on %s %s:\n%s", request.method, request.url.path, tb)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "server_error",
                    "detail": "An internal error occurred. Check server logs for details.",
                },
            )

app.add_middleware(_CatchAllMiddleware)


# Static files and templates
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Register API routers
app.include_router(snapshots.router)
app.include_router(compare.router)
app.include_router(sql_analysis.router)
app.include_router(wait_events.router)
app.include_router(upload.router)
app.include_router(recommendations.router)
app.include_router(intelligence.router)
app.include_router(rag.router)
app.include_router(ai_rca.router)
app.include_router(memory.router)
app.include_router(kb.router)


# ─── Favicon (suppress 404 noise) ───────────────────────────────────────────

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Minimal 1×1 transparent ICO (16 bytes header + 1px BMP)
    ico = bytes([
        0,0,1,0,1,0,16,16,0,0,1,0,32,0,104,4,0,0,22,0,0,0,
        40,0,0,0,16,0,0,0,32,0,0,0,1,0,32,0,0,0,0,0,0,4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
    ] + [0]*1024)
    return Response(content=ico, media_type="image/x-icon")


# ─── HTML Frontend ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main dashboard page."""
    response = templates.TemplateResponse(request=request, name="index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


# ─── API Root ────────────────────────────────────────────────────────────────

@app.get("/api")
async def api_root():
    return {
        "app": "OraVision AWR Pro",
        "version": "2.0.0",
        "endpoints": {
            "snapshots": "/api/snapshots/",
            "compare": "/api/compare/mock",
            "sql_analysis": "/api/sql/top/{period}",
            "wait_events": "/api/waits/{period}",
            "upload": "/api/upload/awr",
            "recommendations": "/api/recommendations/{period}",
            "health": "/api/compare/health/{period}",
        }
    }


@app.get("/api/overview/{period}")
async def dashboard_overview(period: str, demo: bool = False):
    """Get complete dashboard overview data for a period."""
    from services.health_scorer import calculate_health_score

    data, source = resolve_period_or_404(period, demo=demo)
    health = calculate_health_score(data)
    efficiency = data.get("efficiency", {})
    if not isinstance(efficiency, dict):
        efficiency = {}
    top_sql = sorted(
        data.get("sql_stats", []),
        key=lambda sql: sql.get("elapsed_time_secs", 0),
        reverse=True,
    )[:10]

    return {
        "source": source,
        "db_info": {
            "db_name": data.get("db_name", ""),
            "instance": data.get("instance", ""),
            "host": data.get("host", ""),
            "release": data.get("release", ""),
            "cpus": data.get("cpus", 0),
            "memory_gb": data.get("memory_gb", 0),
        },
        "snap_range": {
            "begin_snap": data.get("begin_snap", 0),
            "end_snap": data.get("end_snap", 0),
            "begin_time": data.get("begin_time", ""),
            "end_time": data.get("end_time", ""),
            "elapsed_min": data.get("elapsed_min", 0),
            "db_time_min": data.get("db_time_min", 0),
        },
        "health": health,
        "kpis": {
            "db_time_secs": data.get("db_time_min", 0) * 60,
            "aas": round(data.get("db_time_min", 0) / max(data.get("elapsed_min", 1) or 1, 0.01), 2),
            "buffer_cache_hit": efficiency.get("buffer_cache_hit_pct", 0),
            "soft_parse": efficiency.get("soft_parse_pct", 0),
        },
        "load_profile": data.get("load_profile", []),
        "wait_events": data.get("wait_events", [])[:10],
        "top_sql": top_sql,
    }


if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading

    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
