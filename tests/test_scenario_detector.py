"""Scenario detector — verifies performance-architect pattern recognition on
report-shaped data (the same dict shape compare_periods().model_dump() emits)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services import scenario_detector  # noqa: E402


def _wickes_report() -> dict:
    """A long DELETE on a master table with heavy child I/O (Wickes class)."""
    return {
        "summary": {"bad_bottleneck": "i/o"},
        "top_wait_events": {"comparisons": [
            {"event_name": "db file sequential read", "good_time_secs": 400, "bad_time_secs": 1800},
            {"event_name": "log file sync", "good_time_secs": 50, "bad_time_secs": 220},
        ]},
        "sql_regressions": [{
            "sql_id": "6pg97b7tv41kk",
            "sql_text_full": "DELETE FROM SCPOMGR.TRANSMODE WHERE LOAD_ID = :B1",
            "tables_referenced": ["SCPOMGR.TRANSMODE"],
            "tag": "regression",
            "plan_changed": False,
            "good_elapsed_secs": 900, "bad_elapsed_secs": 2600,
            "good_disk_reads": 200000, "bad_disk_reads": 1800000,
            "good_rows_processed": 50000, "bad_rows_processed": 52000,
        }],
    }


def _pepsico_report() -> dict:
    """A parallel gather-stats colliding with steady-plan application SQL (PepsiCo class)."""
    return {
        "summary": {"bad_bottleneck": "concurrency"},
        "top_wait_events": {"comparisons": [
            {"event_name": "direct path read", "good_time_secs": 300, "bad_time_secs": 1500},
        ]},
        "sql_maintenance": [{
            "sql_id": "9zzgatherstat1",
            "sql_text_full": "BEGIN DBMS_STATS.GATHER_TABLE_STATS('ABPPMGR_SOP','MD_CUBE_WATERFALL', degree=>16); END;",
            "is_oracle_maintenance": True,
            "tables_referenced": ["ABPPMGR_SOP.MD_CUBE_WATERFALL"],
            "good_elapsed_secs": 0, "bad_elapsed_secs": 7200,
        }],
        "sql_regressions": [{
            "sql_id": "8wpxq2gfhjc98",
            "sql_text_full": "INSERT INTO ABPPMGR_SOP.MD_CUBE_WATERFALL SELECT ...",
            "tables_referenced": ["ABPPMGR_SOP.MD_CUBE_WATERFALL"],
            "is_oracle_maintenance": False,
            "plan_changed": False,
            "tag": "regression",
            "avg_elapsed_delta_pct": 60,
            "good_elapsed_secs": 39600, "bad_elapsed_secs": 54000,
        }],
    }


def main() -> None:
    checks: list[tuple[str, bool]] = []

    # 1. Cascading delete recognised on the master table.
    f1 = scenario_detector.detect(_wickes_report())
    cas = [x for x in f1 if x["scenario"] == "cascading_delete"]
    checks.append(("cascading_delete detected", bool(cas)))
    if cas:
        c = cas[0]
        checks.append(("  names target table TRANSMODE", "TRANSMODE" in c["title"]))
        checks.append(("  why mentions foreign-key/child", "foreign-key" in c["why"].lower() or "child" in c["why"].lower()))
        checks.append(("  evidence cites disk reads", any("Disk reads" in e for e in c["evidence"])))
        checks.append(("  not mislabelled a plan flip", not any(x["scenario"] == "plan_flip" for x in f1)))

    # 2. Concurrent-maintenance collision recognised; victim has no plan change.
    f2 = scenario_detector.detect(_pepsico_report())
    con = [x for x in f2 if x["scenario"] == "concurrent_maintenance"]
    checks.append(("concurrent_maintenance detected", bool(con)))
    if con:
        c = con[0]
        checks.append(("  references the victim SQL", "8wpxq2gfhjc98" in " ".join(c["evidence"])))
        checks.append(("  why mentions DBMS_STATS/parallel", "dbms_stats" in c["why"].lower() or "parallel" in c["why"].lower()))

    # 3. A strong (SQL_ID identity) match folds the prior fix into recommended_fix.
    kb = {"matches": [{
        "title": "Wickes LDE", "engineer": "Zafar",
        "root_cause": "cascading delete not optimized",
        "fix": "Use the MDD (Master Delete Dependency) tool under UtilityHubPro",
        "matched_on": ["SQL_ID 6pg97b7tv41kk"], "tags": ["delete", "batch"],
        "confidence": 1.0,
    }]}
    linked = scenario_detector.link_kb(scenario_detector.detect(_wickes_report()), kb)
    cas2 = [x for x in linked if x["scenario"] == "cascading_delete"]
    checks.append(("strong match folds prior fix into recommended_fix",
                   bool(cas2) and "MDD" in cas2[0].get("recommended_fix", "")
                   and cas2[0].get("reference_confidence", 0) >= 0.8))

    # 3b. A weak match (<80%, no SQL_ID, tag-only) is NOT referenced.
    kb_weak = {"matches": [{
        "title": "Unrelated", "fix": "do something else",
        "matched_on": ["bottleneck: I/O"], "tags": ["delete"], "confidence": 0.30,
    }]}
    weak = scenario_detector.link_kb(scenario_detector.detect(_wickes_report()), kb_weak)
    cas3 = [x for x in weak if x["scenario"] == "cascading_delete"]
    checks.append(("weak match (<80%) is not referenced",
                   bool(cas3) and not cas3[0].get("recommended_fix")))

    # 4. A clean report yields no false scenarios.
    clean = {"summary": {"bad_bottleneck": ""}, "top_wait_events": {"comparisons": []},
             "sql_regressions": [{"sql_id": "abc1234567890",
                                  "sql_text_full": "SELECT 1 FROM DUAL",
                                  "plan_changed": False, "tag": "stable",
                                  "good_elapsed_secs": 1, "bad_elapsed_secs": 1}]}
    checks.append(("no false positives on a clean report", scenario_detector.detect(clean) == []))

    passed = sum(1 for _, ok in checks if ok)
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"SCENARIO DETECTOR: {passed}/{len(checks)} checks passed")
    if passed != len(checks):
        sys.exit(1)


if __name__ == "__main__":
    main()
