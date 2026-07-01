"""
Validates the KB Digest expert-incident cross-reference engine:
parse → signal extraction → scored matching on SQL_ID / wait / bottleneck / segment.

Run:  python tests/test_kb_digest.py
"""
from __future__ import annotations
import os, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pathlib import Path
from services import kb_digest as kb

# Isolated digest file with two real-shaped incidents (one inside a code fence
# to prove fenced templates are NOT indexed).
_DIGEST = """# KB Digest

```markdown
## TEMPLATE — should be ignored
- sql_id: zzzzzzzzzzzzz
- bottleneck: CPU
```

# Incidents

## Latch: shared pool contention during month-end batch
- db: PRNEI77C
- date: 2025-03
- engineer: Rangadu
- bottleneck: Concurrency
- wait: latch: shared pool, library cache: mutex X
- sql_id: 7xkq9z2pksvwa, a1b2c3d4e5f6g
- segment: SCPOMGR.LANEEXCEPTION_IDX1
- symptom: DB time up 5x, hard-parse storm
- root_cause: Literal SQL flooding the shared pool
- fix: cursor_sharing=FORCE on the batch service; bound the offending SQL
- outcome: DB time -62%
- tags: hard-parse, shared-pool

## Commit storm — log file sync spike
- engineer: Zafar
- bottleneck: Commit
- wait: log file sync
- sql_id: b2c3d4e5f6g7h
- root_cause: Per-row commit in the ETL loop
- fix: Batched commits to every 5000 rows
- outcome: log file sync waits cleared
"""

PASS = 0
FAIL = 0
def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  PASS  {name}")
    else:
        FAIL += 1; print(f"  FAIL  {name}")

# Point the engine at the temp file
tmp = Path(tempfile.gettempdir()) / "kb_digest_test.md"
tmp.write_text(_DIGEST, encoding="utf-8")
kb._PATH = tmp
kb._cache.update(mtime=None, path=None, incidents=[])

# 1. Parsing — fenced template ignored, 2 real incidents indexed
st = kb.status()
check("indexes exactly 2 real incidents (fenced template ignored)", st["incidents_indexed"] == 2)
check("engineers extracted", set(st["engineers"]) == {"Rangadu", "Zafar"})

# 2. SQL_ID exact match wins
report_sql = {
    "sql_regressions": [{"sql_id": "7xkq9z2pksvwa", "tag": "new_offender", "tables_referenced": []}],
    "top_wait_events": {"comparisons": []},
    "summary": {"bad_bottleneck": "Concurrency"},
}
r = kb.crossref(report_sql)
check("SQL_ID match returns the latch incident first", r["matches"] and r["matches"][0]["engineer"] == "Rangadu")
check("matched_on names the SQL_ID", r["matches"] and any("7xkq9z2pksvwa" in m for m in r["matches"][0]["matched_on"]))
check("fix text surfaced", r["matches"] and "cursor_sharing" in r["matches"][0]["fix"])

# 3. Wait-event match (no SQL_ID) — log file sync → Zafar's commit incident
report_wait = {
    "sql_regressions": [],
    "top_wait_events": {"comparisons": [{"event_name": "log file sync", "wait_class": "Commit"}]},
    "summary": {"bad_bottleneck": "Commit"},
}
r2 = kb.crossref(report_wait)
check("wait-event match finds commit incident", r2["matches"] and r2["matches"][0]["engineer"] == "Zafar")
check("wait match reason recorded", r2["matches"] and any("log file sync" in m for m in r2["matches"][0]["matched_on"]))

# 4. Segment match (object name only)
report_seg = {
    "sql_regressions": [{"sql_id": "nomatch0000000", "tag": "stable",
                         "tables_referenced": ["SCPOMGR.LANEEXCEPTION_IDX1"]}],
    "top_wait_events": {"comparisons": []},
    "summary": {"bad_bottleneck": "Mixed"},
}
r3 = kb.crossref(report_seg)
check("segment match finds latch incident", r3["matches"] and r3["matches"][0]["engineer"] == "Rangadu")

# 5. No signal → no matches, but never errors
r4 = kb.crossref({"sql_regressions": [], "top_wait_events": {"comparisons": []},
                  "summary": {"bad_bottleneck": ""}})
check("no false positives when nothing matches", r4["available"] and r4["match_count"] == 0)

# 6. Failure-proof: garbage input
r5 = kb.crossref(None)
check("None report handled safely", isinstance(r5, dict) and r5["match_count"] == 0)

# 7. Missing file → available False, no crash
kb._PATH = Path(tempfile.gettempdir()) / "does_not_exist_kb.md"
kb._cache.update(mtime=None, path=None, incidents=[])
r6 = kb.crossref(report_sql)
check("missing digest file → available False, safe", r6["available"] is False and r6["match_count"] == 0)

print(f"\nKB DIGEST: {PASS}/{PASS+FAIL} checks passed")
sys.exit(1 if FAIL else 0)
