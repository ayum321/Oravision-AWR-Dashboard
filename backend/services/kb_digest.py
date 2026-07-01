"""
KB Digest — Expert Incident Cross-Reference
===========================================
A lightweight, deterministic knowledge base of REAL past incidents and the
fixes that resolved them — captured from the team's engineers (e.g. via the
Outlook digest puller). When the AWR dashboard flags a bottleneck (a regressed
SQL_ID, a hot wait event/class, or a bottleneck class), this module looks up
`backend/data/kb_digest.md` and returns the matching past incident(s) so the
analyst sees how the same symptom was actually fixed before.

Design
------
- No LLM, no embeddings — pure keyword/identifier matching. Reproducible and
  auditable.
- Failure-proof: a missing or malformed file never raises; it returns an empty
  result so a comparison can never be broken by the KB.
- Hot-reload: the file is re-parsed automatically when its mtime changes, so
  the Outlook puller can append incidents without a server restart.

kb_digest.md format (one block per incident)
--------------------------------------------
    ## Latch: shared pool contention during month-end batch
    - db: PRNEI77C
    - date: 2025-03
    - engineer: Rangadu
    - bottleneck: Concurrency
    - wait: latch: shared pool, library cache: mutex X
    - sql_id: 7xkq9z2pksvwa, a1b2c3d4e5f6g
    - segment: SCPOMGR.LANEEXCEPTION_IDX1
    - symptom: DB time up 5x, hard-parse storm in the batch window
    - root_cause: Literal SQL flooding the shared pool (no bind variables)
    - fix: cursor_sharing=FORCE on the batch service; bound the offending SQL; pinned packages
    - outcome: DB time -62%, latch waits cleared
    - tags: hard-parse, shared-pool, batch

Comma-separated fields (db, wait, sql_id, segment, tags) accept multiple values.
Any field may be omitted. Lines may use "- key: value", "key: value", or
"**key:** value".
"""
from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_PATH = _DATA_DIR / "kb_digest.md"
# Allow an override so the Outlook puller can write anywhere it likes.
_PATH = Path(os.getenv("KB_DIGEST_PATH", str(_DEFAULT_PATH)))

_LIST_FIELDS = {"db", "wait", "sql_id", "segment", "tags"}
_KNOWN_FIELDS = _LIST_FIELDS | {
    "date", "engineer", "bottleneck", "symptom", "root_cause", "fix", "outcome",
}

# ── parse cache (mtime-keyed, thread-safe) ───────────────────────────────────
_lock = threading.Lock()
_cache: dict[str, Any] = {"mtime": None, "path": None, "incidents": []}

_FIELD_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?([A-Za-z_ ]+?)(?:\*\*)?\s*:\s*(.*)$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")
# Oracle SQL_IDs are 13 chars of base-32 (a-z 0-9). Used for free-text extraction.
_SQLID_RE = re.compile(r"\b([0-9a-z]{13})\b")


def _split_list(value: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,;]", value) if p.strip()]


def _parse(text: str) -> list[dict]:
    """Parse the markdown digest into a list of incident dicts. Tolerant of
    blank lines, prose between fields, and missing fields."""
    incidents: list[dict] = []
    cur: dict | None = None
    body_lines: list[str] = []
    in_fence = False

    def _flush() -> None:
        nonlocal cur, body_lines
        if cur is not None:
            extra = "\n".join(body_lines).strip()
            if extra and not cur.get("notes"):
                cur["notes"] = extra
            incidents.append(cur)
        cur, body_lines = None, []

    for line in text.splitlines():
        # Ignore everything inside ``` fenced code blocks (used for the
        # documentation template at the top of the digest file).
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m_head = _HEADING_RE.match(line)
        if m_head:
            _flush()
            cur = {"title": m_head.group(1).strip()}
            continue
        if cur is None:
            continue
        m_field = _FIELD_RE.match(line)
        if m_field:
            key = m_field.group(1).strip().lower().replace(" ", "_")
            val = m_field.group(2).strip()
            if key in _KNOWN_FIELDS:
                cur[key] = _split_list(val) if key in _LIST_FIELDS else val
                continue
        if line.strip():
            body_lines.append(line.strip())
    _flush()

    # Keep only blocks that carry at least one matchable signal.
    return [
        inc for inc in incidents
        if inc.get("sql_id") or inc.get("wait") or inc.get("bottleneck")
        or inc.get("segment") or inc.get("tags")
    ]


def _load() -> list[dict]:
    """Return parsed incidents, re-reading the file only when its mtime changes."""
    path = _PATH
    try:
        if not path.exists():
            with _lock:
                _cache.update(mtime=None, path=str(path), incidents=[])
            return []
        mtime = path.stat().st_mtime
        with _lock:
            if _cache["mtime"] == mtime and _cache["path"] == str(path):
                return _cache["incidents"]
        text = path.read_text(encoding="utf-8", errors="replace")
        incidents = _parse(text)
        with _lock:
            _cache.update(mtime=mtime, path=str(path), incidents=incidents)
        return incidents
    except Exception:
        log.exception("kb_digest: failed to load/parse %s", path)
        return []


# ── signal extraction from a comparison report ───────────────────────────────
def _report_signals(report: dict) -> dict:
    sql_ids: set[str] = set()
    offenders: set[str] = set()
    segments: set[str] = set()
    for r in (report.get("sql_regressions") or []):
        sid = str(r.get("sql_id", "")).strip().lower()
        if sid:
            sql_ids.add(sid)
            if str(r.get("tag", "")) in ("new_offender", "regression", "load_increase"):
                offenders.add(sid)
        for t in (r.get("tables_referenced") or []):
            tt = str(t).strip().lower()
            if tt:
                segments.add(tt)

    waits: set[str] = set()
    wait_classes: set[str] = set()
    for w in ((report.get("top_wait_events") or {}).get("comparisons") or []):
        en = str(w.get("event_name", "")).strip().lower()
        if en:
            waits.add(en)
        wc = str(w.get("wait_class", "")).strip().lower()
        if wc and wc != "other":
            wait_classes.add(wc)

    summary = report.get("summary") or {}
    bottleneck = str(summary.get("bad_bottleneck", "")).strip().lower()
    return {
        "sql_ids": sql_ids,
        "offenders": offenders,
        "segments": segments,
        "waits": waits,
        "wait_classes": wait_classes,
        "bottleneck": bottleneck,
    }


def _wait_hit(inc_token: str, report_waits: set[str], report_classes: set[str]) -> bool:
    """An incident wait token matches if it appears within any flagged event name
    (or vice-versa), or equals a flagged wait class."""
    t = inc_token.strip().lower()
    if not t:
        return False
    if t in report_classes:
        return True
    for ev in report_waits:
        if t in ev or ev in t:
            return True
    return False


def _score(inc: dict, sig: dict) -> tuple[int, list[str], float]:
    """Score one incident against the report signals.
    Returns (score, reasons, confidence) where confidence is a 0..1 similarity:
    an exact SQL_ID match means we have literally seen this statement before (1.0);
    otherwise it is the weighted fraction of the incident's other signal
    categories (wait / bottleneck / segment) that matched."""
    score = 0
    reasons: list[str] = []
    matched: set[str] = set()
    available: set[str] = set()
    if inc.get("sql_id"):
        available.add("sql_id")
    if inc.get("wait"):
        available.add("wait")
    if str(inc.get("bottleneck", "")).strip():
        available.add("bottleneck")
    if inc.get("segment"):
        available.add("segment")

    for sid in (inc.get("sql_id") or []):
        s = str(sid).strip().lower()
        if not s:
            continue
        if s in sig["sql_ids"]:
            pts = 55 if s in sig["offenders"] else 40
            score += pts
            reasons.append(f"SQL_ID {sid}")
            matched.add("sql_id")

    for wtok in (inc.get("wait") or []):
        if _wait_hit(wtok, sig["waits"], sig["wait_classes"]):
            score += 20
            reasons.append(f"wait: {wtok}")
            matched.add("wait")

    inc_bottleneck = str(inc.get("bottleneck", "")).strip().lower()
    if inc_bottleneck and sig["bottleneck"] and (
        inc_bottleneck == sig["bottleneck"]
        or inc_bottleneck in sig["bottleneck"]
        or sig["bottleneck"] in inc_bottleneck
    ):
        score += 15
        reasons.append(f"bottleneck: {inc.get('bottleneck')}")
        matched.add("bottleneck")

    for seg in (inc.get("segment") or []):
        s = str(seg).strip().lower()
        if not s:
            continue
        # match on full owner.object or just the object name
        obj = s.split(".")[-1]
        if s in sig["segments"] or any(obj and obj in rs for rs in sig["segments"]):
            score += 12
            reasons.append(f"segment: {seg}")
            matched.add("segment")

    # ── normalized similarity (0..1) ─────────────────────────────────────────
    if "sql_id" in matched:
        confidence = 1.0  # same statement seen before — an identity match
    else:
        cat_w = {"wait": 0.45, "bottleneck": 0.30, "segment": 0.25}
        denom = sum(cat_w[c] for c in available if c in cat_w)
        numer = sum(cat_w[c] for c in matched if c in cat_w)
        confidence = (numer / denom) if denom else 0.0

    return score, reasons, round(confidence, 3)


def crossref(report: dict, top_k: int = 4, min_score: int = 12) -> dict:
    """Cross-reference a comparison report against the expert incident digest.

    Returns a failure-proof dict:
        {
          "available": bool,            # digest file present & has incidents
          "incidents_indexed": int,
          "match_count": int,
          "matches": [ {title, engineer, date, db, bottleneck, symptom,
                        root_cause, fix, outcome, tags, score, matched_on[]} ],
          "path": str,
        }
    """
    try:
        incidents = _load()
        if not incidents:
            return {
                "available": False, "incidents_indexed": 0,
                "match_count": 0, "matches": [], "path": str(_PATH),
            }
        sig = _report_signals(report or {})
        scored: list[tuple[int, list[str], float, dict]] = []
        for inc in incidents:
            sc, reasons, conf = _score(inc, sig)
            if sc >= min_score:
                scored.append((sc, reasons, conf, inc))
        scored.sort(key=lambda x: (x[0], x[2]), reverse=True)

        matches = []
        for sc, reasons, conf, inc in scored[:max(1, top_k)]:
            matches.append({
                "title": inc.get("title", ""),
                "engineer": inc.get("engineer", ""),
                "date": inc.get("date", ""),
                "db": inc.get("db") or [],
                "bottleneck": inc.get("bottleneck", ""),
                "symptom": inc.get("symptom", ""),
                "root_cause": inc.get("root_cause", ""),
                "fix": inc.get("fix", ""),
                "outcome": inc.get("outcome", ""),
                "tags": inc.get("tags") or [],
                "score": sc,
                "confidence": conf,
                "matched_on": reasons,
            })
        return {
            "available": True,
            "incidents_indexed": len(incidents),
            "match_count": len(matches),
            "matches": matches,
            "path": str(_PATH),
        }
    except Exception:
        log.exception("kb_digest.crossref failed (non-fatal)")
        return {
            "available": False, "incidents_indexed": 0,
            "match_count": 0, "matches": [], "path": str(_PATH),
        }


def status() -> dict:
    """Health/diagnostics for the KB digest."""
    try:
        incidents = _load()
        engineers = sorted({
            str(i.get("engineer", "")).strip() for i in incidents if i.get("engineer")
        })
        return {
            "available": _PATH.exists(),
            "path": str(_PATH),
            "incidents_indexed": len(incidents),
            "engineers": engineers,
            "sql_ids_indexed": sum(len(i.get("sql_id") or []) for i in incidents),
        }
    except Exception:
        log.exception("kb_digest.status failed")
        return {"available": False, "path": str(_PATH), "incidents_indexed": 0,
                "engineers": [], "sql_ids_indexed": 0}
