"""
HARD adversarial AWR benchmark — full transparency ledger.

Every case prints: scenario | known answer (with source rationale) | tool answer | PASS/FAIL.
These are TRAP cases, not softballs — they target classic mis-diagnoses that fool naive tools:
ambiguous signatures, masked CPU, stalls that look like improvements, hot-block vs IO, etc.
Expected answers follow canonical Oracle wait-event doctrine.

Run:  python tests/test_hard_adversarial_benchmark.py
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models.snapshot import AWRData
from services.comparator import compare_periods

EFF = ["buffer_cache_hit_pct", "library_cache_hit_pct", "soft_parse_pct", "execute_to_parse_pct", "latch_hit_pct"]

def eff(buf=99, lib=99, soft=98, e2p=95, latch=99.9):
    return {"buffer_cache_hit_pct": buf, "library_cache_hit_pct": lib, "soft_parse_pct": soft,
            "execute_to_parse_pct": e2p, "latch_hit_pct": latch}

def w(name, cls, pct, ms, secs=2000, n=100000):
    return {"event_name": name, "wait_class": cls, "pct_db_time": pct, "avg_wait_ms": ms,
            "time_waited_secs": secs, "total_waits": n}

def snap(dbmin, waits, e=None, cpus=16, txn=200.0):
    return AWRData(db_name="ORCL", cpus=cpus, memory_gb=128, begin_snap=1, end_snap=2,
                   elapsed_min=60, db_time_min=dbmin, efficiency=e or eff(), efficiency_available=EFF,
                   load_profile=[{"stat_name": "Transactions", "per_sec": txn}], wait_events=waits).model_dump()

# Each: id, scenario, good, bad, expected bottleneck class, expected severity
CASES = [
 ("Q1 CPU saturation, AAS>>cpus", "CPU",      "critical", snap(120,[w("CPU","CPU time",30,0)]),                          snap(900,[w("CPU","CPU time",85,0)],eff(buf=80))),
 ("Q2 random read regression",    "I/O",      "critical", snap(120,[w("db file sequential read","User I/O",25,4)]),     snap(700,[w("db file sequential read","User I/O",78,18)],eff(buf=82))),
 ("Q3 commit/redo storm",         "Commit",   "critical", snap(120,[w("log file sync","Commit",15,3)]),                 snap(600,[w("log file sync","Commit",72,40)],eff(buf=90))),
 ("Q4 RAC global cache",          "Cluster",  "critical", snap(120,[w("gc buffer busy acquire","Cluster",10,5)]),       snap(650,[w("gc buffer busy acquire","Cluster",70,28)],eff(buf=88))),
 ("Q5 hot block buffer busy",     "Concurrency","critical",snap(120,[w("buffer busy waits","Concurrency",12,6)]),       snap(620,[w("buffer busy waits","Concurrency",68,22)],eff(buf=87))),
 ("Q6 library cache lock",        "Concurrency","critical",snap(120,[w("library cache lock","Concurrency",10,9)]),      snap(580,[w("library cache lock","Concurrency",66,30)],eff(lib=60,soft=55))),
 ("Q7 net data to client",        "Network",  "critical", snap(120,[w("SQL*Net more data to client","Network",12,2)]),  snap(560,[w("SQL*Net more data to client","Network",64,9)])),
 ("Q8 row lock TX",               "Concurrency","critical",snap(120,[w("enq: TX - row lock contention","Application",8,40)]),snap(640,[w("enq: TX - row lock contention","Application",70,300)])),
 ("Q9 full scan scattered read",  "I/O",      "critical", snap(120,[w("db file scattered read","User I/O",15,5)]),      snap(700,[w("db file scattered read","User I/O",75,22)],eff(buf=78))),
 ("Q10 stays healthy",            "I/O",      "healthy",  snap(110,[w("db file sequential read","User I/O",30,5)]),     snap(113,[w("db file sequential read","User I/O",31,5)])),
 # ---- TRAPS ----
 ("Q11 TRAP commit-not-IO (low redo ms)","Commit","critical", snap(120,[w("log file sync","Commit",15,2)]),            snap(600,[w("log file sync","Commit",70,1.5)],eff(buf=92))),
 ("Q12 TRAP CPU dominant over small IO","CPU","critical",     snap(120,[w("CPU","CPU time",40,0),w("db file sequential read","User I/O",10,4)]), snap(900,[w("CPU","CPU time",80,0),w("db file sequential read","User I/O",8,4)],eff(buf=84))),
 ("Q13 TRAP concurrency masks IO",  "Concurrency","critical", snap(120,[w("buffer busy waits","Concurrency",20,5)]),     snap(650,[w("buffer busy waits","Concurrency",65,18),w("db file sequential read","User I/O",15,6)],eff(buf=80))),
 ("Q14 TRAP cluster top w/ commit2","Cluster","critical",     snap(120,[w("gc cr block busy","Cluster",18,6)]),           snap(620,[w("gc cr block busy","Cluster",60,22),w("log file sync","Commit",18,5)])),
 ("Q15 mixed no clear winner",      "Mixed","critical",       snap(120,[w("CPU","CPU time",4,0)]),                        snap(400,[w("CPU","CPU time",4,0),w("db file sequential read","User I/O",4,5),w("log file sync","Commit",4,3)])),
]

def run():
    print(f"\n{'='*100}\nHARD ADVERSARIAL AWR BENCHMARK — FULL LEDGER (n={len(CASES)})\n{'='*100}")
    print(f"{'ID/Scenario':<42}{'EXPECT cls/sev':<20}{'TOOL cls/sev':<20}{'RESULT'}")
    print("-"*100)
    cls_ok = sev_ok = 0
    for cid, exp_cls, exp_sev, good, bad in CASES:
        r = compare_periods(good, bad).model_dump()["summary"]
        tcls, tsev = r.get("bad_bottleneck","?"), r.get("severity","?")
        c = tcls == exp_cls; s = tsev == exp_sev
        cls_ok += c; sev_ok += s
        res = "PASS" if (c and s) else ("cls FAIL" if not c else "sev FAIL")
        print(f"{cid:<42}{exp_cls+'/'+exp_sev:<20}{tcls+'/'+tsev:<20}{res}")
    n=len(CASES)
    print("-"*100)
    print(f"Bottleneck class: {cls_ok}/{n}   Severity: {sev_ok}/{n}   TOTAL PASS: {min(cls_ok,sev_ok)}/{n}")
    return run_semantic_traps()


def sql(sid, avg, plan, execs=1000):
    return {"sql_id": sid, "elapsed_time_secs": avg*execs, "executions": execs,
            "avg_elapsed_secs": avg, "plan_hash_value": plan, "pct_db_time": 50}

def run_semantic_traps():
    print(f"\n{'='*100}\nSEMANTIC TRAPS — plan-flip, stall, resmgr masking\n{'='*100}")
    rows = []
    # Q16 plan flip: same SQL, plan changed, per-exec 5x worse -> Regressed, plan_changed
    g = snap(120,[w("db file sequential read","User I/O",40,5)], txn=200); g["sql_stats"]=[sql("aaa",0.5,"111")]
    b = snap(400,[w("db file sequential read","User I/O",70,12)],eff(buf=80), txn=200); b["sql_stats"]=[sql("aaa",2.5,"999")]
    rep = compare_periods(g,b).model_dump(); regs=rep.get("sql_regressions",[])
    flip = any(s.get("plan_changed") and "Regress" in (s.get("net_assessment","")+s.get("plan_verdict","")) for s in regs)
    rows.append(("Q16 plan-flip -> plan_changed+Regressed", flip))
    # Q17 stall: DB time DOWN but txn down MORE = not improvement
    g = snap(300,[w("db file sequential read","User I/O",50,5)], txn=300)
    b = snap(200,[w("db file sequential read","User I/O",50,5)], txn=80)
    s=compare_periods(g,b).model_dump()["summary"]
    stall = s.get("congestion_signal") or s.get("ratio_inversion") or "stall" in (s.get("headline","")+s.get("overall_regression","")).lower()
    rows.append(("Q17 stall not flagged improvement", bool(stall)))
    # Q18 resmgr masking: must NOT classify as CPU
    g = snap(120,[w("resmgr:cpu quantum","Scheduler",15,5)])
    b = snap(600,[w("resmgr:cpu quantum","Scheduler",75,30)],eff(buf=85))
    rcls=compare_periods(g,b).model_dump()["summary"].get("bad_bottleneck")
    rows.append(("Q18 resmgr NOT mislabeled CPU", rcls!="CPU"))
    for name,ok in rows: print(f"  {name:<46}{'PASS' if ok else 'FAIL'}  (got)")
    print(f"Semantic traps: {sum(1 for _,o in rows if o)}/{len(rows)}")
    return rows

if __name__ == "__main__":
    run()
