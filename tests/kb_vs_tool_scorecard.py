"""
KB-vs-Tool Agreement Scorecard
==============================
Answers one question: when an engineer (Rangadu, Zafar, Sukhamoy, Virendra,
Ayush ...) diagnosed and fixed a real incident, does OUR AWR tool independently
reach the same bottleneck verdict — or is it totally different?

How it works (no fabricated data):
  1. Loads the REAL incidents from backend/data/kb_digest.md (the ones the
     Outlook puller / engineers added).
  2. For each incident, replays the engineer's *recorded wait signature*
     through the tool's OWN classifier `comparator._classify_bottleneck`
     (the exact function the live dashboard uses — not a re-implementation).
  3. Compares the tool's class against the engineer's recorded `bottleneck`
     and prints AGREE / PARTIAL / DIFFERENT, plus the engineer's actual fix.

If the KB has no real incidents yet, it prints how to add them and runs a
clearly-labelled DEMO on the bundled sample fixture so you can see the format.

Run:  python tests/kb_vs_tool_scorecard.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services import kb_digest
from services import comparator

# Map an engineer's free-text bottleneck label onto the tool's taxonomy.
_NORMALISE = {
    "cpu": "CPU",
    "io": "I/O", "i/o": "I/O", "disk": "I/O", "user i/o": "I/O",
    "concurrency": "Concurrency", "latch": "Concurrency", "lock": "Concurrency",
    "application": "Concurrency", "contention": "Concurrency",
    "commit": "Commit", "redo": "Commit", "log": "Commit",
    "cluster": "Cluster", "rac": "Cluster", "gc": "Cluster",
    "network": "Network", "net": "Network",
    "mixed": "Mixed",
}


def _norm(label: str) -> str:
    t = (label or "").strip().lower()
    if t in _NORMALISE:
        return _NORMALISE[t]
    for key, val in _NORMALISE.items():
        if key in t:
            return val
    return label.strip().title() if label else "Unknown"


def _infer_wait_class(event_name: str) -> str:
    """Infer the Oracle wait class from an event name (canonical doctrine), so a
    KB incident that records only event names replays exactly as the tool would
    see it from a real AWR. Returns '' when the tool's name-based fallback in
    _classify_bottleneck already handles it (cpu / log file sync / gc / sql*net /
    lock / latch)."""
    e = (event_name or "").strip().lower()
    if not e:
        return ""
    # User I/O — the class the name-based fallback does NOT cover.
    if any(k in e for k in (
        "db file sequential read", "db file scattered read", "direct path read",
        "direct path write", "read by other session", "db file parallel read",
    )):
        return "User I/O"
    # System I/O
    if any(k in e for k in (
        "log file parallel write", "db file parallel write", "control file",
        "log file sequential read",
    )):
        return "System I/O"
    return ""  # let _classify_bottleneck decide from the event name


def _replay(incident: dict) -> str | None:
    """Replay the engineer's recorded wait signature through the tool's real
    classifier. Returns the tool's bottleneck class, or None if the incident
    carries no wait signature to replay."""
    waits = incident.get("wait") or []
    if not waits:
        return None
    n = len(waits)
    share = 80.0 / n  # dominant, evenly split — class is decided by which sums highest
    wait_events = [
        {"event_name": str(w).strip(),
         "wait_class": _infer_wait_class(str(w)), "pct_db_time": share}
        for w in waits if str(w).strip()
    ]
    if not wait_events:
        return None
    return comparator._classify_bottleneck({"wait_events": wait_events})


def _verdict(expert: str, tool: str | None) -> str:
    if tool is None:
        return "NO-WAIT"
    if tool == expert:
        return "AGREE"
    if "Mixed" in (tool, expert):  # one side hedged — not a hard contradiction
        return "PARTIAL"
    return "DIFFERENT"


def score(incidents: list[dict], heading: str) -> tuple[int, int, int, int]:
    print(f"\n{'='*108}\n{heading} (n={len(incidents)})\n{'='*108}")
    print(f"{'Engineer':<12}{'Incident':<34}{'EXPERT class':<15}{'TOOL class':<15}{'RESULT':<11}{'Fix (recorded)'}")
    print("-" * 108)
    agree = partial = diff = nowait = 0
    for inc in incidents:
        expert = _norm(inc.get("bottleneck", ""))
        tool = _replay(inc)
        res = _verdict(expert, tool)
        if res == "AGREE":
            agree += 1
        elif res == "PARTIAL":
            partial += 1
        elif res == "DIFFERENT":
            diff += 1
        else:
            nowait += 1
        eng = (inc.get("engineer") or "—")[:11]
        title = (inc.get("title") or "")[:33]
        fix = (inc.get("fix") or "—")
        fix = fix[:42] + ("…" if len(fix) > 42 else "")
        print(f"{eng:<12}{title:<34}{expert:<15}{(tool or '—'):<15}{res:<11}{fix}")
    print("-" * 108)
    total = len(incidents)
    print(f"AGREE: {agree}/{total}   PARTIAL: {partial}/{total}   "
          f"DIFFERENT: {diff}/{total}   NO-WAIT(unreplayable): {nowait}/{total}")
    if total - nowait > 0:
        replayable = total - nowait
        print(f"Tool agreement on replayable cases: {agree}/{replayable} exact, "
              f"{agree + partial}/{replayable} exact-or-partial")
    return agree, partial, diff, nowait


def main() -> int:
    st = kb_digest.status()
    incidents = kb_digest._load()  # real incidents from backend/data/kb_digest.md

    print(f"KB digest: {st['path']}")
    print(f"Real incidents indexed: {st['incidents_indexed']}   "
          f"Engineers: {', '.join(st['engineers']) or '(none)'}")

    if incidents:
        agree, partial, diff, nowait = score(incidents, "KB-vs-TOOL — REAL EXPERT CASES")
        print("\nLegend: AGREE = tool's bottleneck class matches the engineer's. "
              "PARTIAL = one side said 'Mixed'. DIFFERENT = the tool diverged "
              "(investigate that case). NO-WAIT = incident has no wait signature to replay.")
        # Non-zero exit if the tool diverges on any real case — surfaces drift in CI.
        return 1 if diff else 0

    # ── No real incidents yet ────────────────────────────────────────────────
    print("\nNo real incidents in the KB yet. Add them to backend/data/kb_digest.md")
    print("(one '## ' block per incident with at least a `bottleneck` and a `wait`")
    print("line), or let the Outlook digest puller append them. Then re-run this.\n")
    print("Running a DEMO on the bundled sample fixture so you can see the format")
    print("(this is SAMPLE data, NOT real expert cases):")

    demo = """
## Latch: shared pool contention during month-end batch
- engineer: Rangadu
- bottleneck: Concurrency
- wait: latch: shared pool, library cache: mutex X
- fix: cursor_sharing=FORCE on the batch service; bound the offending SQL

## Commit storm — log file sync spike
- engineer: Zafar
- bottleneck: Commit
- wait: log file sync
- fix: Batched commits to every 5000 rows

## Random-read regression after stats change
- engineer: Sukhamoy
- bottleneck: I/O
- wait: db file sequential read
- fix: Restored good plan via SQL plan baseline; re-gathered stats

## RAC global cache hot block
- engineer: Virendra
- bottleneck: Cluster
- wait: gc buffer busy acquire, gc cr block busy
- fix: Partitioned the hot index to spread blocks across instances
"""
    demo_incidents = kb_digest._parse(demo)
    score(demo_incidents, "DEMO — SAMPLE FIXTURE (not real data)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
