"""Shared AWR data source helpers.

This module centralizes how the application resolves data for dashboard
endpoints. Uploaded AWR payloads are preferred when available; otherwise
callers must explicitly request demo mode.
"""
from __future__ import annotations

import os
import re
import time
from copy import deepcopy
from typing import Any

# ── Upload storage with TTL ──────────────────────────────────────────────────

_MAX_AGE_SECS = 3600 * 4  # 4 hours TTL per upload
try:
    _MAX_UPLOADS = max(2, int(os.getenv("ORAVISION_MAX_UPLOADS", "24")))
except ValueError:
    _MAX_UPLOADS = 24
_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_uploaded_data: dict[str, dict[str, Any]] = {}
_upload_timestamps: dict[str, float] = {}


def normalize_upload_label(label: str) -> str:
    """Return a bounded storage key suitable for API and in-memory lookup."""
    normalized = (label or "uploaded").strip().lower()
    if not _LABEL_RE.fullmatch(normalized):
        raise ValueError("Upload label must contain 1-64 lowercase letters, numbers, underscores, or hyphens.")
    return normalized


def store_uploaded_data(label: str, data: dict[str, Any]) -> None:
    """Store parsed upload data under a stable label."""
    normalized = normalize_upload_label(label)
    _purge_expired()
    if normalized not in _uploaded_data:
        while len(_uploaded_data) >= _MAX_UPLOADS:
            oldest = min(_upload_timestamps, key=_upload_timestamps.get)
            _uploaded_data.pop(oldest, None)
            _upload_timestamps.pop(oldest, None)
    _uploaded_data[normalized] = data
    _upload_timestamps[normalized] = time.time()


def get_uploaded_data(label: str) -> dict[str, Any] | None:
    """Return uploaded data by label if present (and not expired)."""
    _purge_expired()
    try:
        return _uploaded_data.get(normalize_upload_label(label))
    except ValueError:
        return None


def has_uploaded_data(label: str) -> bool:
    """Check whether a non-expired upload exists for the given label."""
    _purge_expired()
    try:
        return normalize_upload_label(label) in _uploaded_data
    except ValueError:
        return False


def list_uploaded_data() -> list[tuple[str, dict[str, Any]]]:
    """Return uploaded data items for API responses."""
    _purge_expired()
    return list(_uploaded_data.items())


def clear_uploaded_data() -> None:
    """Clear uploaded data. Intended for tests and local reset flows."""
    _uploaded_data.clear()
    _upload_timestamps.clear()


def _purge_expired() -> None:
    """Remove uploads older than _MAX_AGE_SECS."""
    now = time.time()
    expired = [k for k, ts in _upload_timestamps.items() if now - ts > _MAX_AGE_SECS]
    for k in expired:
        _uploaded_data.pop(k, None)
        _upload_timestamps.pop(k, None)


def resolve_period_data(period: str, *, allow_demo: bool = False) -> tuple[dict[str, Any], str]:
    """Resolve a single-period dataset.

    Resolution order:
    1. Exact uploaded label, e.g. ``uploaded`` / ``uploaded_good`` / ``uploaded_bad``
    2. Canonical aliases:
       - ``good`` -> ``uploaded_good`` -> ``uploaded``
       - ``bad``  -> ``uploaded_bad``
    3. If ``allow_demo=True``, fall back to mock data (explicit demo mode only).
    4. Otherwise raise ``KeyError`` — never silently produce fake data.
    """
    _purge_expired()

    normalized = (period or "good").strip().lower()

    if normalized in _uploaded_data:
        return deepcopy(_uploaded_data[normalized]), normalized

    if normalized == "good":
        if "uploaded_good" in _uploaded_data:
            return deepcopy(_uploaded_data["uploaded_good"]), "uploaded_good"
        if "uploaded" in _uploaded_data:
            return deepcopy(_uploaded_data["uploaded"]), "uploaded"

    if normalized == "bad":
        if "uploaded_bad" in _uploaded_data:
            return deepcopy(_uploaded_data["uploaded_bad"]), "uploaded_bad"

    # Explicit demo mode only — never silent fallback
    if allow_demo:
        from services.mock_data import get_mock_awr_data, get_mock_bad_data, get_mock_good_data
        if normalized == "good":
            return deepcopy(get_mock_good_data()), "demo_good"
        if normalized == "bad":
            return deepcopy(get_mock_bad_data()), "demo_bad"
        return deepcopy(get_mock_awr_data(normalized)), f"demo_{normalized}"

    raise KeyError(
        f"No uploaded report found for period '{normalized}'. "
        "Upload an AWR report first, or use ?demo=true for sample data."
    )


def resolve_comparison_data(
    good_period: str = "good",
    bad_period: str = "bad",
    *,
    allow_demo: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, str]]:
    """Resolve a comparison pair without mixing uploaded and mock datasets.

    If a real uploaded comparison exists, use both uploaded periods together.
    Otherwise use the requested pair as an exact uploaded-label lookup when both
    are present. If neither case applies, fall back to demo data only when
    ``allow_demo=True``. Otherwise raise ``KeyError``.
    """
    _purge_expired()

    good_norm = (good_period or "good").strip().lower()
    bad_norm = (bad_period or "bad").strip().lower()

    if good_norm in _uploaded_data and bad_norm in _uploaded_data:
        return (
            deepcopy(_uploaded_data[good_norm]),
            deepcopy(_uploaded_data[bad_norm]),
            (good_norm, bad_norm),
        )

    if (
        good_norm == "good"
        and bad_norm == "bad"
        and "uploaded_good" in _uploaded_data
        and "uploaded_bad" in _uploaded_data
    ):
        return (
            deepcopy(_uploaded_data["uploaded_good"]),
            deepcopy(_uploaded_data["uploaded_bad"]),
            ("uploaded_good", "uploaded_bad"),
        )

    if allow_demo:
        from services.mock_data import get_mock_bad_data, get_mock_good_data
        return deepcopy(get_mock_good_data()), deepcopy(get_mock_bad_data()), ("demo_good", "demo_bad")

    raise KeyError(
        f"No uploaded reports found for comparison (good='{good_norm}', bad='{bad_norm}'). "
        "Upload both AWR reports first, or use ?demo=true for sample data."
    )


# ── HTTP-friendly wrappers (raise 404 instead of KeyError) ───────────────────

def resolve_period_or_404(
    period: str, *, demo: bool = False,
) -> tuple[dict[str, Any], str]:
    """Like ``resolve_period_data`` but raises ``HTTPException(404)`` on miss."""
    from fastapi import HTTPException
    try:
        return resolve_period_data(period, allow_demo=demo)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def resolve_comparison_or_404(
    good: str = "good", bad: str = "bad", *, demo: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, str]]:
    """Like ``resolve_comparison_data`` but raises ``HTTPException(404)`` on miss."""
    from fastapi import HTTPException
    try:
        return resolve_comparison_data(good, bad, allow_demo=demo)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
