"""
PDF Knowledge Base Service
===========================
Ingests Oracle PDF documentation into the shared rag_kb.db SQLite store,
enabling keyword-based cross-check of RCA recommendations against official sources.

Public API
----------
    ingest_pdf(pdf_path: str) -> int
        Parse and chunk the PDF, store in pdf_knowledge table.
        Returns the number of chunks stored.

    query_kb(keywords: list[str], top_k: int = 5) -> list[dict]
        Return up to top_k most relevant chunks matching the keywords.

    cross_check_rca(wait_events: list[str], sql_type: str, issue_type: str) -> list[dict]
        Convenience wrapper: derive keywords from AWR signals and return guidance.

    kb_status() -> dict
        Chunk counts and source files currently stored.

Requirements
------------
    pdfplumber>=0.10    (pip install pdfplumber)
    No other non-stdlib deps.

Fallback
--------
    If pdfplumber is not installed, ingest_pdf() raises ImportError with
    install instructions, but all other functions still work against any
    chunks that were previously stored.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Storage ──────────────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DATA_DIR / "rag_kb.db"

# Oracle domain keywords used for relevance scoring (no stemming needed)
_ORACLE_TERMS = {
    "buffer cache", "buffer hit", "shared pool", "library cache", "hard parse",
    "soft parse", "bind variable", "cursor sharing", "full table scan", "index range scan",
    "nested loops", "hash join", "sort merge", "execution plan", "plan hash",
    "cardinality", "histogram", "statistics", "dbms_stats", "gather stats",
    "optimizer", "cost based", "rule based", "query transformation", "subquery",
    "materialized view", "inline view", "with clause", "rowid", "rownum",
    "pga", "sga", "uga", "redo log", "undo", "rollback", "flashback",
    "wait event", "wait class", "db time", "db cpu", "aas", "active sessions",
    "log file sync", "db file sequential read", "db file scattered read",
    "direct path read", "direct path write", "free buffer wait", "buffer busy",
    "latch", "enqueue", "lock", "deadlock", "row lock", "table lock",
    "partition pruning", "parallel query", "parallel execution", "degree",
    "sql tuning advisor", "sqlt", "sql profile", "sql plan baseline", "spm",
    "sql monitoring", "ash", "awr", "addm", "statspack",
    "dbms_xplan", "display_cursor", "display_awr", "sql trace", "tkprof",
    "10046", "10053", "event 10",
    "high water mark", "hwm", "segment", "extent", "block", "initrans", "pctfree",
    "assm", "freelist", "tablespace", "locally managed",
    "init.ora", "spfile", "pfile", "parameter", "sga_target", "pga_aggregate_target",
    "db_cache_size", "shared_pool_size", "log_buffer", "cursor_sharing",
    "optimizer_mode", "optimizer_features_enable",
}

# Heading patterns in PDF text (detect section/chapter boundaries)
_HEADING_RE = re.compile(
    r"^(?:"
    r"chapter\s+\d|"                  # Chapter N
    r"\d+\s+[A-Z][A-Za-z ]{5,60}$|" # "12 SQL Tuning Overview"
    r"[A-Z][A-Z\s\-/]{8,60}$|"      # "SQL TUNING OVERVIEW"
    r"(?:Overview|Introduction|Summary|Concepts?|Guidelines?|Examples?|"
    r"Best Practices?|Diagnosis|Methodology|Reference)\b"
    r")",
    re.IGNORECASE,
)

_MAX_CHUNK_CHARS = 1_200   # keep chunks short enough to be readable
_MIN_CHUNK_CHARS = 80      # discard very small fragments (headers only, etc.)


# ── Schema bootstrap ─────────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_DB_PATH))
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _init_schema() -> None:
    with closing(_conn()) as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS pdf_knowledge (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file  TEXT NOT NULL,
                page_num     INTEGER,
                section      TEXT,
                chunk_text   TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                char_count   INTEGER,
                created_at   INTEGER NOT NULL
            )
            """
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_pdf_source ON pdf_knowledge(source_file)"
        )
        # FTS5 virtual table for fast full-text search (SQLite has this built-in)
        c.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS pdf_fts USING fts5(
                chunk_text,
                content=pdf_knowledge,
                content_rowid=id
            )
            """
        )
        c.commit()


_init_schema()


# ── PDF parsing & chunking ────────────────────────────────────────────────────
def _extract_pages(pdf_path: str) -> list[dict]:
    """Return [{page_num, text}, ...] from PDF using pdfplumber."""
    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is required for PDF ingestion.\n"
            "Install it with:  pip install pdfplumber\n"
            "Then re-run the ingestion script."
        ) from exc

    pages: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            # strip header/footer lines (short lines at very top or bottom of page)
            lines = text.splitlines()
            if len(lines) > 4:
                lines = lines[1:-1]  # crude header/footer strip
            pages.append({"page_num": i, "text": "\n".join(lines)})
    return pages


def _split_into_chunks(pages: list[dict]) -> list[dict]:
    """
    Split pages into logical chunks, attempting to break at section headings.
    Returns [{page_num, section, chunk_text}, ...]
    """
    chunks: list[dict] = []
    current_section = "Introduction"
    current_page = 1
    current_buf: list[str] = []

    def flush(section: str, page: int, buf: list[str]) -> None:
        text = " ".join(" ".join(b.split()) for b in buf).strip()
        if len(text) >= _MIN_CHUNK_CHARS:
            # sub-split oversized chunks by sentence
            if len(text) > _MAX_CHUNK_CHARS:
                sentences = re.split(r"(?<=[.!?])\s+", text)
                sub_buf: list[str] = []
                for sent in sentences:
                    if sum(len(s) for s in sub_buf) + len(sent) > _MAX_CHUNK_CHARS and sub_buf:
                        sub_text = " ".join(sub_buf)
                        if len(sub_text) >= _MIN_CHUNK_CHARS:
                            chunks.append({"page_num": page, "section": section, "chunk_text": sub_text})
                        sub_buf = [sent]
                    else:
                        sub_buf.append(sent)
                if sub_buf:
                    sub_text = " ".join(sub_buf)
                    if len(sub_text) >= _MIN_CHUNK_CHARS:
                        chunks.append({"page_num": page, "section": section, "chunk_text": sub_text})
            else:
                chunks.append({"page_num": page, "section": section, "chunk_text": text})

    for page_data in pages:
        page_num = page_data["page_num"]
        for line in page_data["text"].splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _HEADING_RE.match(stripped) and len(stripped) < 80:
                # heading boundary → flush current chunk, start new section
                flush(current_section, current_page, current_buf)
                current_section = stripped
                current_page = page_num
                current_buf = []
            else:
                current_buf.append(stripped)
                # flush if accumulated enough
                if sum(len(b) for b in current_buf) >= _MAX_CHUNK_CHARS:
                    flush(current_section, current_page, current_buf)
                    current_page = page_num
                    current_buf = []

    flush(current_section, current_page, current_buf)
    return chunks


def _extract_keywords(text: str) -> list[str]:
    """Return Oracle-domain keywords that appear in the text (case-insensitive)."""
    lower = text.lower()
    found: list[str] = []
    for term in _ORACLE_TERMS:
        if term in lower:
            found.append(term)
    # also extract wait event names (quoted or bracketed patterns)
    for m in re.finditer(r"\"([a-z][a-z0-9 :_\-]{3,50})\"", lower):
        candidate = m.group(1).strip()
        if any(w in candidate for w in ("wait", "read", "write", "sync", "latch", "enq", "lock")):
            if candidate not in found:
                found.append(candidate)
    return found


# ── Ingestion ─────────────────────────────────────────────────────────────────
def ingest_pdf(pdf_path: str, replace_existing: bool = True) -> int:
    """
    Parse *pdf_path*, chunk the text, and store in the pdf_knowledge table.

    Parameters
    ----------
    pdf_path : str
        Absolute path to the PDF file.
    replace_existing : bool
        If True (default), delete any previously stored chunks for this file
        before inserting fresh ones.

    Returns
    -------
    int
        Number of chunks stored.
    """
    _init_schema()
    path = Path(pdf_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    source_key = path.name  # store only the filename as the key

    log.info("Extracting pages from %s …", path)
    pages = _extract_pages(str(path))
    log.info("  → %d pages extracted", len(pages))

    chunks = _split_into_chunks(pages)
    log.info("  → %d chunks after split", len(chunks))

    now = int(time.time())
    with closing(_conn()) as con:
        if replace_existing:
            # remove old FTS entries first
            old_ids = [
                row[0]
                for row in con.execute(
                    "SELECT id FROM pdf_knowledge WHERE source_file=?", (source_key,)
                ).fetchall()
            ]
            if old_ids:
                placeholders = ",".join("?" * len(old_ids))
                con.execute(
                    f"DELETE FROM pdf_fts WHERE rowid IN ({placeholders})", old_ids
                )
                con.execute(
                    "DELETE FROM pdf_knowledge WHERE source_file=?", (source_key,)
                )
                log.info("  → removed %d stale chunks for %s", len(old_ids), source_key)

        stored = 0
        for chunk in chunks:
            kws = _extract_keywords(chunk["chunk_text"])
            row_id = con.execute(
                """
                INSERT INTO pdf_knowledge
                    (source_file, page_num, section, chunk_text, keywords_json, char_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_key,
                    chunk["page_num"],
                    chunk["section"],
                    chunk["chunk_text"],
                    json.dumps(kws),
                    len(chunk["chunk_text"]),
                    now,
                ),
            ).lastrowid
            # sync FTS
            con.execute(
                "INSERT INTO pdf_fts(rowid, chunk_text) VALUES (?, ?)",
                (row_id, chunk["chunk_text"]),
            )
            stored += 1

        con.commit()

    log.info("  → stored %d chunks for %s", stored, source_key)
    return stored


# ── Retrieval ─────────────────────────────────────────────────────────────────
def _keyword_score(chunk_keywords: list[str], query_kws: list[str]) -> float:
    """
    Score relevance between stored chunk keywords and query keywords.
    Uses Jaccard on exact matches + partial credit for word-level substring matches.
    """
    if not query_kws or not chunk_keywords:
        return 0.0
    ck = set(chunk_keywords)
    qk = set(query_kws)

    # exact Jaccard
    intersection = len(ck & qk)
    union = len(ck | qk)
    exact_score = intersection / union if union else 0.0

    # partial: query word contained in any stored keyword phrase
    partial_hits = 0
    for q in qk:
        for c in ck:
            if q in c or c in q:
                partial_hits += 1
                break
    partial_score = partial_hits / len(qk) if qk else 0.0

    return round(max(exact_score, partial_score * 0.6), 3)


def query_kb(keywords: list[str], top_k: int = 5, source_filter: str | None = None) -> list[dict]:
    """
    Return up to *top_k* chunks most relevant to *keywords*.

    Uses SQLite FTS5 for primary match, then re-ranks by keyword overlap.
    Falls back to keyword overlap scan if FTS returns nothing.

    Parameters
    ----------
    keywords : list[str]
        Oracle-domain terms extracted from the AWR signal (wait event names,
        SQL types, issue labels, etc.).  Case-insensitive.
    top_k : int
        Maximum number of chunks to return.
    source_filter : str | None
        Limit to a specific source file (basename).

    Returns
    -------
    list[dict]
        Each element: {id, source_file, page_num, section, chunk_text, keywords, score}
    """
    _init_schema()
    if not keywords:
        return []

    norm_kws = [k.lower().strip() for k in keywords if k.strip()]

    results: list[dict] = []

    with closing(_conn()) as con:
        # ── FTS search ────────────────────────────────────────────────────────
        # Build FTS query: match any of the multi-word keywords with NEAR or OR
        fts_terms: list[str] = []
        for kw in norm_kws[:8]:  # FTS5 query gets long, cap at 8 terms
            # Escape FTS special chars, wrap multi-word in quotes
            escaped = kw.replace('"', '""')
            if " " in escaped:
                fts_terms.append(f'"{escaped}"')
            else:
                fts_terms.append(escaped)

        fts_query = " OR ".join(fts_terms)
        try:
            source_clause = "AND pk.source_file = ?" if source_filter else ""
            fts_params: list[Any] = [fts_query]
            if source_filter:
                fts_params.append(source_filter)

            rows = con.execute(
                f"""
                SELECT pk.id, pk.source_file, pk.page_num, pk.section,
                       pk.chunk_text, pk.keywords_json
                FROM pdf_fts
                JOIN pdf_knowledge pk ON pdf_fts.rowid = pk.id
                WHERE pdf_fts MATCH ?
                  {source_clause}
                ORDER BY rank
                LIMIT {top_k * 4}
                """,
                fts_params,
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

        # ── Fallback: full keyword scan if FTS returns nothing ────────────────
        if not rows:
            conditions = " OR ".join(
                "chunk_text LIKE ?" for _ in norm_kws[:6]
            )
            like_params: list[Any] = [f"%{k}%" for k in norm_kws[:6]]
            if source_filter:
                conditions = f"({conditions}) AND source_file = ?"
                like_params.append(source_filter)
            if conditions:
                rows = con.execute(
                    f"""
                    SELECT id, source_file, page_num, section, chunk_text, keywords_json
                    FROM pdf_knowledge
                    WHERE {conditions}
                    LIMIT {top_k * 4}
                    """,
                    like_params,
                ).fetchall()

    for row in rows:
        row_id, src, pg, sec, text, kws_json = row
        try:
            stored_kws: list[str] = json.loads(kws_json) if kws_json else []
        except (json.JSONDecodeError, TypeError):
            stored_kws = []
        score = _keyword_score(stored_kws, norm_kws)
        results.append(
            {
                "id": row_id,
                "source_file": src,
                "page_num": pg,
                "section": sec or "",
                "chunk_text": text,
                "keywords": stored_kws,
                "score": round(score, 3),
            }
        )

    # re-rank by score, deduplicate by id
    seen: set[int] = set()
    unique: list[dict] = []
    for item in sorted(results, key=lambda x: x["score"], reverse=True):
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)

    return unique[:top_k]


# ── Cross-check helper ────────────────────────────────────────────────────────
# Maps common AWR wait-event + issue patterns to keyword sets
_RCA_KEYWORD_MAP: dict[str, list[str]] = {
    "io":             ["db file sequential read", "db file scattered read", "full table scan", "index range scan", "physical reads", "buffer cache"],
    "memory":         ["pga", "pga_aggregate_target", "sort", "direct path read temp", "hash join", "buffer cache", "shared pool"],
    "parse":          ["hard parse", "soft parse", "bind variable", "library cache", "cursor sharing", "shared pool"],
    "concurrency":    ["buffer busy", "latch", "enqueue", "lock", "row lock", "initrans", "assm", "freelist"],
    "commit":         ["log file sync", "redo log", "lgwr", "commit", "undo"],
    "plan_regression":["execution plan", "plan hash", "optimizer", "cardinality", "histogram", "statistics", "dbms_stats"],
    "stats":          ["dbms_stats", "statistics", "histogram", "cardinality", "stale statistics", "gather stats"],
    "sql_tuning":     ["execution plan", "access path", "index range scan", "nested loops", "hash join", "optimizer", "sql tuning advisor"],
    "new_sql":        ["execution plan", "statistics", "bind variable", "optimizer", "full table scan"],
    "space_mgmt":     ["high water mark", "hwm", "segment", "assm", "freelist", "initrans", "enqueue"],
}

_WAIT_TO_CATEGORY: list[tuple[str, str]] = [
    ("db file sequential read",  "io"),
    ("db file scattered read",   "io"),
    ("direct path read",         "io"),
    ("direct path read temp",    "memory"),
    ("direct path write temp",   "memory"),
    ("log file sync",            "commit"),
    ("buffer busy",              "concurrency"),
    ("latch",                    "concurrency"),
    ("enq:",                     "concurrency"),
    ("library cache",            "parse"),
    ("shared pool",              "parse"),
    ("hard parse",               "parse"),
]


def cross_check_rca(
    wait_events: list[str],
    sql_type: str = "",
    issue_type: str = "",
    top_k: int = 4,
) -> list[dict]:
    """
    Derive Oracle-domain keywords from AWR signals and retrieve relevant PDF chunks.

    Parameters
    ----------
    wait_events : list[str]
        Dominant wait event names from the AWR comparison (e.g. ["db file sequential read"]).
    sql_type : str
        SQL classification: "SELECT", "INSERT", "UPDATE", "DELETE", etc.
    issue_type : str
        Issue label from the RCA engine: "PLAN_REGRESSION", "NEW_WORKLOAD",
        "HIGH_IO", "PARSE_STORM", etc.

    Returns
    -------
    list[dict]  — same shape as query_kb()
    """
    keyword_set: list[str] = []

    # add wait event names directly as keywords
    keyword_set.extend(e.lower() for e in wait_events if e)

    # map wait events to category keywords
    for event in wait_events:
        ev_lower = event.lower()
        for pattern, category in _WAIT_TO_CATEGORY:
            if pattern in ev_lower:
                keyword_set.extend(_RCA_KEYWORD_MAP.get(category, []))
                break

    # map issue type
    issue_lower = issue_type.lower()
    for cat_key in _RCA_KEYWORD_MAP:
        if cat_key in issue_lower:
            keyword_set.extend(_RCA_KEYWORD_MAP[cat_key])

    # always include sql_type keywords
    if sql_type:
        keyword_set.append(sql_type.lower())
    if "select" in (sql_type or "").lower():
        keyword_set.extend(_RCA_KEYWORD_MAP["sql_tuning"])
    elif "insert" in (sql_type or "").lower():
        keyword_set.extend(["high water mark", "assm", "freelist", "initrans", "redo log", "undo"])

    # deduplicate while preserving order
    seen: set[str] = set()
    unique_kws: list[str] = []
    for kw in keyword_set:
        if kw not in seen:
            seen.add(kw)
            unique_kws.append(kw)

    return query_kb(unique_kws, top_k=top_k)


# ── Status ────────────────────────────────────────────────────────────────────
def kb_status() -> dict:
    """Return counts and metadata about stored PDF knowledge chunks."""
    _init_schema()
    with closing(_conn()) as con:
        total_row = con.execute("SELECT COUNT(*) FROM pdf_knowledge").fetchone()
        total = total_row[0] if total_row else 0
        sources = con.execute(
            """
            SELECT source_file, COUNT(*) as chunks,
                   MAX(created_at) as last_ingested
            FROM pdf_knowledge
            GROUP BY source_file
            ORDER BY last_ingested DESC
            """
        ).fetchall()
    return {
        "total_chunks": total,
        "sources": [
            {
                "source_file": row[0],
                "chunks": row[1],
                "last_ingested": row[2],
            }
            for row in sources
        ],
    }


def format_chunks_for_prompt(chunks: list[dict], max_chars: int = 2500) -> str:
    """
    Format retrieved PDF chunks for inclusion in an LLM system prompt or
    template narrative. Returns an empty string if no chunks available.
    """
    if not chunks:
        return ""
    lines: list[str] = ["## Oracle SQL Tuning Guide — Relevant Sections\n"]
    used = len(lines[0])
    for i, chunk in enumerate(chunks, start=1):
        header = f"[{i}] {chunk['source_file']} p.{chunk['page_num']} — {chunk['section']}\n"
        body = chunk["chunk_text"][:600] + ("…" if len(chunk["chunk_text"]) > 600 else "")
        entry = header + body + "\n\n"
        if used + len(entry) > max_chars:
            break
        lines.append(entry)
        used += len(entry)
    return "".join(lines).strip()
