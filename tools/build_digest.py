"""
build_digest.py  —  Step 4 of the Outlook -> KB pipeline.

Reads  knowledge_base.jsonl  and writes  backend/data/kb_digest.md  —  the
expert-incident knowledge base the AWR dashboard cross-references and the
KB-vs-Tool scorecard replays.

For each e-mail it extracts, deterministically (no LLM):
    bottleneck class, Oracle wait events, SQL_IDs, segments, db, date,
    symptom / root_cause / fix / outcome, and tags.
Incidents are grouped by engineer and emitted in the "## " block format the
services/kb_digest.py parser understands. The documentation/header above the
"# Incidents" marker is preserved; the incidents below it are regenerated from
the (already de-duplicated) jsonl, so re-running never doubles up.

Run from the workspace root:
    python tools/build_digest.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSONL = ROOT / "knowledge_base.jsonl"
DIGEST = ROOT / "backend" / "data" / "kb_digest.md"

# ── Oracle wait vocabulary: (detect substring, canonical name, bottleneck class)
_WAITS: list[tuple[str, str, str]] = [
    ("log file sync", "log file sync", "Commit"),
    ("log file parallel write", "log file parallel write", "Commit"),
    ("db file sequential read", "db file sequential read", "I/O"),
    ("db file scattered read", "db file scattered read", "I/O"),
    ("db file parallel read", "db file parallel read", "I/O"),
    ("direct path read temp", "direct path read temp", "I/O"),
    ("direct path read", "direct path read", "I/O"),
    ("direct path write temp", "direct path write temp", "I/O"),
    ("direct path write", "direct path write", "I/O"),
    ("read by other session", "read by other session", "I/O"),
    ("buffer busy waits", "buffer busy waits", "Concurrency"),
    ("latch: shared pool", "latch: shared pool", "Concurrency"),
    ("latch: cache buffers chains", "latch: cache buffers chains", "Concurrency"),
    ("latch: row cache objects", "latch: row cache objects", "Concurrency"),
    ("library cache lock", "library cache lock", "Concurrency"),
    ("library cache: mutex x", "library cache: mutex X", "Concurrency"),
    ("library cache pin", "library cache pin", "Concurrency"),
    ("cursor: pin s wait on x", "cursor: pin S wait on X", "Concurrency"),
    ("cursor: mutex", "cursor: mutex S", "Concurrency"),
    ("enq: tx - row lock contention", "enq: TX - row lock contention", "Concurrency"),
    ("enq: tx - index contention", "enq: TX - index contention", "Concurrency"),
    ("enq: tm - contention", "enq: TM - contention", "Concurrency"),
    ("enq: hw - contention", "enq: HW - contention", "Concurrency"),
    ("gc buffer busy acquire", "gc buffer busy acquire", "Cluster"),
    ("gc buffer busy release", "gc buffer busy release", "Cluster"),
    ("gc cr block busy", "gc cr block busy", "Cluster"),
    ("gc current block busy", "gc current block busy", "Cluster"),
    ("gc cr request", "gc cr request", "Cluster"),
    ("gc current request", "gc current request", "Cluster"),
    ("sql*net more data to client", "SQL*Net more data to client", "Network"),
    ("sql*net message from dblink", "SQL*Net message from dblink", "Network"),
    ("sql*net more data from dblink", "SQL*Net more data from dblink", "Network"),
]

# Bottleneck keyword fallback when no concrete wait event is named.
_BOTTLENECK_KW: list[tuple[str, str]] = [
    (r"\bcpu\s*time\b|\bhigh\s*cpu\b|\bcpu[-\s]*bound\b|\bcpu\s*satur", "CPU"),
    (r"\blog file sync\b|\blog file parallel write\b|\bredo\b|\bcommit\s+wait\b", "Commit"),
    (r"\bglobal cache\b|\brac\b|\bgc \b|\bcluster\b|\binterconnect\b", "Cluster"),
    (r"\bsql\*net\b|\bnetwork\b", "Network"),
    (r"\bsequential read\b|\bscattered read\b|\bphysical read\b|\bi/?o\b|\bdisk\b", "I/O"),
    (r"\blatch\b|\brow lock\b|\bblocking\b|\bdeadlock\b|\bbuffer busy\b"
     r"|\bsegment contention\b|\blibrary cache\b|\benq:\b|\bmutex\b|\bcontention\b", "Concurrency"),
]

_SQLID_RE = re.compile(r"\b([0-9a-z]{13})\b")
# Authoritative: a token explicitly labelled "SQL ID" / "SQL_ID" is the real id.
_SQLID_LABELLED_RE = re.compile(r"sql[\s_]*id\b[\s:#=.-]*([0-9a-z]{13})\b", re.IGNORECASE)
# A db/instance host name looks like letters-then-digits (e.g. prbc651503011);
# Oracle SQL_IDs interleave and never use the letters e, i, l, o (base-32 alphabet).
_HOSTNAME_SHAPE = re.compile(r"^[a-z]{2,}[0-9]{4,}[a-z0-9]*$")
_SEGMENT_RE = re.compile(r"\b([A-Z][A-Z0-9_$]{2,}\.[A-Z][A-Z0-9_$#]{2,})\b")
# Column-name suffixes: an OWNER.OBJECT match whose object ends like a column is
# almost always a TABLE.COLUMN predicate reference, not a SCHEMA.TABLE segment.
_COLUMN_SUFFIX = re.compile(
    r"(?:_ID|_IDS|_DATE|_DT|_TS|_TIME|_STATE|_STATUS|_NAME|_CODE|_CD|_FLAG"
    r"|_IND|_NUM|_NO|_KEY|_TYPE|_DESC|_AMT|_QTY)$")
_DB_RE = re.compile(r"\b([A-Z]{3,}[0-9]{2,}[A-Z0-9]*)\b")
_DB_HOST_RE = re.compile(r"\b([a-z]{2,}[0-9]{4,}[a-z0-9]*)\b")

_SECTIONS = {
    "symptom": r"problem|symptom|issue|impact|observed|behaviou?r",
    "root_cause": r"root\s*cause|\brca\b|diagnosis|reason|because",
    "fix": r"fix|solution|resolution|action\s*taken|remediation|resolved\s*by|workaround|changed?|implemented",
    "outcome": r"outcome|result|after\s*(?:the\s*)?(?:fix|change)|improvement|reduced",
}

_TAG_KW = ["batch", "hard-parse", "parse", "plan", "stats", "index", "partition",
           "bind", "cursor", "purge", "archive", "tablespace", "undo", "temp",
           "month-end", "etl", "interconnect"]

# Free-prose harvesters. When an email has no "fix:" / "root_cause:" headers
# (most real threads), pull the engineer's own sentences VERBATIM so the
# dashboard shows how they actually solved it, in their words — never invented.
_REMEDY_PAT = (
    r"\bpin(?:ning|ned)?\b.*\bplan\b|\benable\s+(?:pdml|parallel)|\bparallel\s+dml\b"
    r"|\bcreate\s+(?:an?\s+)?index\b|\bintroduc\w*\s+parallel|\bparallel\s+hint"
    r"|\btruncate\s+instead\s+of\s+delete\b|\bexclud\w*\b.*\bstat"
    r"|\brebuild\b|\bgather\w*\s+stat|\badd\s+the\s+\w*\s*hint|\bcursor_sharing\b"
    r"|\bbind\s+variable|\bplan\s+hash\s+value\b|\bclean\s*up\b|\bwork\s+with\s+dba"
    r"|\bavoid\s+running\b|\bdo\s+not\s+run\b|\bstagger\b|\bserial(?:ize|ise)\b"
    r"|\bdisable\b|\bupdate\b.*\bset\s+value\b|\bset\s+value\s*="
    r"|\block_table_stats|\bunlock\b.*\bstat|\bdelete_table_stats|\bcomment\s+that\s+gathering"
    r"|\bdelete\s+the\s+statistics\b|\bincrease\b.*\btimeout"
)
_OUTCOME_PAT = (
    r"\breduced?\b|\bimproved?\b|\bfaster\b|\bbetter\b|\bcame\s+down\b"
    r"|\bcompleted?\s+in\b|\bnow\s+(?:runs?|completes?|takes?)\b"
    r"|\bunder\s+\d+\s*(?:min|minute|hour|hr)\b"
    r"|\bfrom\s+.*\bto\s+(?:under\s+)?\d+\s*(?:min|minute|hour|hr)"
)
_SYMPTOM_PAT = (
    r"\btook\s+(?:approximately\s+)?\d|\btaking\s+(?:almost\s+|significant|a\s+long)"
    r"|\bexecution\s+plan\s+deviation|\bplan\s+deviation|\bgrowing\s+continuously"
    r"|\bhigh(?:er)?\s+volume|\bslow\b|\blong(?:er)?\s+(?:time|run)"
    r"|\b\d+\.?\d*\s*(?:hours?|hrs?|mins?|minutes?)\b"
)
_ROOTCAUSE_PAT = (
    r"\bdue\s+to\b|\bbecause\b|\bchange\s+in\s+the\s+execution\s+plan\b"
    r"|\bincreased\s+data\s+volume\b|\bvolume\s+of\s+data\s+processed\b"
    r"|\bplan\s+change\b|\bappears?\s+to\s+(?:have|be)\b"
)
_HEADER_LINE_RE = re.compile(r"(?i)^(from|sent|to|cc|subject)\b")
# Greeting / sign-off words: skip only when the line is just that (short), so an
# inline "Hi @Name, <real recommendation...>" sentence is still harvested.
_GREETING_RE = re.compile(r"(?i)^(thanks|regards|hi|hello|best|cheers)\b")
# Separator-only lines (====, ----, ____) carry no content.
_SEP_RE = re.compile(r"^[=\-_\u2013\u2014~*\u2022.\s]{2,}$")
# Owners that are PL/SQL packages / builtins, never real data segments.
_PKG_OWNERS = {"SYS", "SYSTEM", "CTXSYS", "DBMS", "UTL", "DBMS_STATS",
               "DBMS_LOCK", "DBMS_OUTPUT", "DBMS_SCHEDULER", "DBMS_JOB"}

_DISALLOWED_SQLID = {"information", "performance"}  # too short to ever match anyway


def _clean_title(subject: str) -> str:
    s = re.sub(r"^\s*(re|fw|fwd)\s*:\s*", "", subject, flags=re.IGNORECASE).strip()
    s = re.sub(r"^\s*(re|fw|fwd)\s*:\s*", "", s, flags=re.IGNORECASE).strip()
    return s or "Incident"


def _find_waits(body_l: str) -> tuple[list[str], dict[str, int]]:
    found: list[str] = []
    class_tally: dict[str, int] = {}
    for needle, canon, cls in _WAITS:
        if needle in body_l and canon not in found:
            found.append(canon)
            class_tally[cls] = class_tally.get(cls, 0) + 1
    return found, class_tally


def _infer_bottleneck(class_tally: dict[str, int], body_l: str) -> str:
    if class_tally:
        return max(class_tally.items(), key=lambda x: (x[1], x[0]))[0]
    for pat, cls in _BOTTLENECK_KW:
        if re.search(pat, body_l):
            return cls
    return ""


def _find_sql_ids(body: str, db: str = "") -> list[str]:
    out: list[str] = []
    # 1) Authoritative pass: tokens explicitly labelled "SQL ID" in the text.
    for m in _SQLID_LABELLED_RE.findall(body):
        if m not in out:
            out.append(m)
    if out:
        return out[:5]
    # 2) Fallback: generic 13-char tokens, excluding db/host-shaped names and
    #    anything outside Oracle's SQL_ID base-32 alphabet (no e, i, l, o).
    db_l = db.lower()
    for m in _SQLID_RE.findall(body):
        if not (any(c.isdigit() for c in m) and any(c.isalpha() for c in m)):
            continue
        if m == db_l or _HOSTNAME_SHAPE.match(m):
            continue
        if any(ch in m for ch in "eilo"):
            continue
        if m not in out:
            out.append(m)
    return out[:5]


def _strip_noise(text: str) -> str:
    """Remove embedded-image CID refs, mailto/URLs and MIME junk that otherwise
    get mis-read as db names, SQL_IDs or segments."""
    text = re.sub(r"\[cid:[^\]]*\]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"image\d+\.png@[0-9A-Fa-f.]+", " ", text)
    text = re.sub(r"\bmailto:\S+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://\S+", " ", text)
    return text


def _find_segments(body: str) -> list[str]:
    out: list[str] = []
    for m in _SEGMENT_RE.findall(body):
        owner, obj = m.split(".", 1)
        if owner in _PKG_OWNERS or owner.startswith(("DBMS_", "UTL_")):
            continue
        if _COLUMN_SUFFIX.search(obj):
            continue  # TABLE.COLUMN predicate ref, not a real segment
        if m not in out:
            out.append(m)
    return out[:5]


def _find_db(body: str, subject: str) -> str:
    for src in (subject, body):
        for rx in (_DB_RE, _DB_HOST_RE):
            m = rx.search(src)
            if m:
                return m.group(1)
    return ""


def _extract_section(lines: list[str], pattern: str) -> str:
    head_re = re.compile(rf"^\s*(?:[-*•>]\s*)?(?:{pattern})\b\s*[:\-–]\s*(.*)$", re.IGNORECASE)
    any_head = re.compile(
        r"^\s*(?:[-*•>]\s*)?(?:"
        + "|".join(_SECTIONS.values())
        + r")\b\s*[:\-–]", re.IGNORECASE)
    for i, ln in enumerate(lines):
        m = head_re.match(ln)
        if not m:
            continue
        parts = [m.group(1).strip()]
        for nxt in lines[i + 1:]:
            if not nxt.strip() or any_head.match(nxt) or nxt.lstrip().startswith("#"):
                break
            if _SEP_RE.match(nxt.strip()):
                continue
            parts.append(nxt.strip())
            if sum(len(p) for p in parts) > 320:
                break
        text = " ".join(p for p in parts if p).strip(" -\u2013\u2022\t=_~*.")
        if text:
            return re.sub(r"\s+", " ", text)[:320]
    return ""


def _tags(body_l: str, waits: list[str]) -> list[str]:
    tags = [kw for kw in _TAG_KW if kw in body_l]
    return tags[:6]


def _clean_sentence(s: str) -> str:
    s = re.sub(r"<[^>]*>", " ", s)
    s = re.sub(r"\[cid:[^\]]*\]", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bmailto:\S+", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"https?://\S+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" \t-*\u2022>")


def _sentences(body: str) -> list[str]:
    out: list[str] = []
    for ln in body.splitlines():
        ln = ln.strip(" \t-*\u2022>")
        if not ln or _HEADER_LINE_RE.match(ln) or _SEP_RE.match(ln):
            continue
        if _GREETING_RE.match(ln) and len(ln) < 40:
            continue
        for frag in re.split(r"(?<=[.?!])\s+", ln):
            frag = _clean_sentence(frag)
            if 12 <= len(frag) <= 400:
                out.append(frag)
    return out


def _harvest(sentences: list[str], pattern: str, limit: int, maxlen: int,
             exclude: set[str] | None = None, negative: str | None = None
             ) -> tuple[str, set[str]]:
    rx = re.compile(pattern, re.IGNORECASE)
    neg = re.compile(negative, re.IGNORECASE) if negative else None
    exclude = exclude or set()
    picks: list[str] = []
    for s in sentences:
        if s in exclude or s in picks:
            continue
        if neg and neg.search(s):
            continue
        if rx.search(s):
            picks.append(s)
        if len(picks) >= limit:
            break
    text = re.sub(r"\s+", " ", " ".join(picks)).strip()[:maxlen]
    return text, set(picks)


def _date(received: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})", received or "")
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def _extract(rec: dict) -> dict | None:
    body = _strip_noise(rec.get("body", "") or "")
    body_l = body.lower()
    lines = body.splitlines()

    waits, tally = _find_waits(body_l)
    bottleneck = _infer_bottleneck(tally, body_l)
    db = _find_db(body, rec.get("subject", ""))
    sql_ids = _find_sql_ids(body, db)
    segments = _find_segments(body)
    tags = _tags(body_l, waits)

    # Keep only incidents that carry at least one matchable signal.
    if not (waits or bottleneck or sql_ids or segments or tags):
        return None

    # Prefer explicit "fix:" / "root_cause:" headers; otherwise harvest the
    # engineer's own sentences verbatim so the narrative stays in their words.
    # Slot each field to distinct sentences: outcome → fix → root_cause →
    # symptom, so a result sentence never gets mislabelled as the symptom.
    sents = _sentences(body)
    outcome = _extract_section(lines, _SECTIONS["outcome"])
    outcome_used: set[str] = set()
    if not outcome:
        outcome, outcome_used = _harvest(sents, _OUTCOME_PAT, 2, 320)

    fix = _extract_section(lines, _SECTIONS["fix"])
    fix_used: set[str] = set()
    if not fix:
        fix, fix_used = _harvest(sents, _REMEDY_PAT, 4, 520, exclude=outcome_used)

    root_cause = _extract_section(lines, _SECTIONS["root_cause"])
    root_used: set[str] = set()
    if not root_cause:
        root_cause, root_used = _harvest(sents, _ROOTCAUSE_PAT, 2, 320,
                                         exclude=outcome_used | fix_used)

    symptom = _extract_section(lines, _SECTIONS["symptom"])
    if not symptom:
        symptom, _ = _harvest(sents, _SYMPTOM_PAT, 2, 320,
                              exclude=outcome_used | fix_used | root_used,
                              negative=_OUTCOME_PAT)

    return {
        "title": _clean_title(rec.get("subject", "")),
        "engineer": rec.get("engineer", ""),
        "date": _date(rec.get("received", "")),
        "db": db,
        "bottleneck": bottleneck,
        "wait": waits,
        "sql_id": sql_ids,
        "segment": segments,
        "symptom": symptom,
        "root_cause": root_cause,
        "fix": fix,
        "outcome": outcome,
        "tags": tags,
    }


def _emit_block(inc: dict) -> str:
    out = [f"## {inc['title']}"]

    def line(key: str, val) -> None:
        if not val:
            return
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val if str(v).strip())
            if not val:
                return
        out.append(f"- {key}: {val}")

    line("db", inc["db"])
    line("date", inc["date"])
    line("engineer", inc["engineer"])
    line("bottleneck", inc["bottleneck"])
    line("wait", inc["wait"])
    line("sql_id", inc["sql_id"])
    line("segment", inc["segment"])
    line("symptom", inc["symptom"])
    line("root_cause", inc["root_cause"])
    line("fix", inc["fix"])
    line("outcome", inc["outcome"])
    line("tags", inc["tags"])
    return "\n".join(out)


def _read_jsonl() -> list[dict]:
    if not JSONL.exists():
        return []
    recs = []
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return recs


def _preserved_header() -> str:
    """Everything up to (but not including) the '# Incidents' line is kept."""
    default = (
        "# KB Digest — Expert Incident Knowledge Base\n\n"
        "Generated from the team's Outlook e-mails by tools/build_digest.py.\n"
    )
    if not DIGEST.exists():
        return default
    text = DIGEST.read_text(encoding="utf-8")
    m = re.search(r"^#\s+Incidents\s*$", text, re.MULTILINE)
    return text[: m.start()].rstrip() + "\n" if m else text.rstrip() + "\n"


def main() -> int:
    recs = _read_jsonl()
    incidents: list[dict] = []
    skipped = 0
    for r in recs:
        inc = _extract(r)
        if inc is None:
            skipped += 1
        else:
            incidents.append(inc)

    # Group by engineer, then by date for stable, readable output.
    incidents.sort(key=lambda i: (i["engineer"], i["date"], i["title"]))

    blocks = "\n\n".join(_emit_block(i) for i in incidents)
    header = _preserved_header()
    body = (
        f"{header}\n# Incidents\n\n"
        "<!--\n"
        "  Generated from knowledge_base.jsonl by tools/build_digest.py.\n"
        "  Grouped by engineer. Re-run after exporting more e-mails; it dedups.\n"
        f"  Contributors: Rangadu · Zafar · Sukhamoy · Virendra · Ayush\n"
        "-->\n\n"
        + (blocks + "\n" if blocks else "")
    )

    DIGEST.parent.mkdir(parents=True, exist_ok=True)
    DIGEST.write_text(body, encoding="utf-8")

    by_eng: dict[str, int] = {}
    for i in incidents:
        by_eng[i["engineer"]] = by_eng.get(i["engineer"], 0) + 1

    print(f"kb_digest.md: {len(incidents)} incident(s) written, {skipped} skipped (no signal)")
    if by_eng:
        print("By engineer: " + ", ".join(f"{k}={v}" for k, v in sorted(by_eng.items())))
    else:
        print("No incidents yet. Run the Outlook export + python tools/build_kb.py first.")
    print("Dashboard hot-reloads kb_digest.md. Check alignment: python tests/kb_vs_tool_scorecard.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
