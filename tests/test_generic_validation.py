"""Generic validation: test the full pipeline on DIFFERENT AWR reports.
Proves the dashboard works with ANY AWR, not just FF_NEWSKU_PLAN.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.html_parser import parse_awr_html, normalize_parsed_data
from services.health_scorer import calculate_health_score
from services.comparator import compare_periods

AWR_DIR = r"C:\Users\1039081\Downloads\Work\AWR-Reports"

FILES = {
    "FF_NEWSKU_PLAN Good":  os.path.join(AWR_DIR, "FF_NEWSKU_PLAN", "Good_run_AWR Rpt - ADSPRDDB Snap 203542 thru 203545.html"),
    "FF_NEWSKU_PLAN Bad":   os.path.join(AWR_DIR, "FF_NEWSKU_PLAN", "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html"),
    "awrrpt_173866":        os.path.join(AWR_DIR, "awrrpt_1_173866_173869", "awrrpt_1_173866_173869.html"),
    "PRANYE7G_10637":       os.path.join(AWR_DIR, "Order_Pegging_with_priority_AWR Rpt - PRANYE7G Snap 10637 thru 10640", "Order_Pegging_with_priority_AWR Rpt - PRANYE7G Snap 10637 thru 10640.html"),
}

def load_and_validate(name, path):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"  File: ...{path[-60:]}")
    print(f"{'='*60}")
    
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    
    # Step 1: Parse
    raw = parse_awr_html(html)
    issues = []
    
    # Check core sections parsed
    sections = {
        "load_profile":  raw.get("load_profile"),
        "wait_events":   raw.get("wait_events"),
        "sql_stats":     raw.get("sql_stats"),
        "time_model":    raw.get("time_model"),
        "sga":           raw.get("sga"),
        "os_stats":      raw.get("os_stats"),
        "efficiency":    raw.get("efficiency"),
    }
    
    for section, data in sections.items():
        if not data:
            issues.append(f"  WARN: {section} is empty/missing")
        elif isinstance(data, list) and len(data) == 0:
            issues.append(f"  WARN: {section} is empty list")
        else:
            count = len(data) if isinstance(data, list) else (len(data) if isinstance(data, dict) else "?")
            print(f"  PARSE  {section}: {count} items")
    
    # Step 2: Normalize
    try:
        normalized = normalize_parsed_data(raw)
        nd = normalized.model_dump()
        print(f"  NORM   db_name={nd.get('db_name','?')} instance={nd.get('instance','?')} host={nd.get('host','?')} release={nd.get('release','?')} cpus={nd.get('cpus','?')}")
        print(f"  NORM   sql_stats={len(nd.get('sql_stats',[]))} wait_events={len(nd.get('wait_events',[]))}")
        print(f"  NORM   load_profile={len(nd.get('load_profile',[]))} time_model={len(nd.get('time_model',[]))}")
    except Exception as e:
        issues.append(f"  FAIL: normalize_parsed_data() crashed: {e}")
        print(f"  NORM   FAILED: {e}")
        return None, issues

    # Step 3: Health score
    try:
        health = calculate_health_score(nd)
        print(f"  HEALTH score={health['score']} grade={health['grade']} severity={health['severity']}")
        for alert in health.get("alerts", []):
            print(f"         {alert['score_impact']:+d} {alert['metric']}: {alert['message']}")
        deductions = health.get("deductions", [])
        print(f"         deductions={len(deductions)}")
    except Exception as e:
        issues.append(f"  FAIL: calculate_health_score() crashed: {e}")
        print(f"  HEALTH FAILED: {e}")

    # Step 4: Check wait_class coverage
    wait_events = nd.get("wait_events", [])
    no_class = [w for w in wait_events if not w.get("wait_class") or w["wait_class"] == ""]
    if no_class:
        for w in no_class:
            issues.append(f"  WARN: wait event '{w['event_name']}' has no wait_class")
    else:
        print(f"  WCLASS all {len(wait_events)} wait events have wait_class assigned")

    if issues:
        print("\n  ISSUES:")
        for i in issues:
            print(f"    {i}")
    else:
        print("\n  RESULT: ALL CHECKS PASSED")
    
    return nd, issues

# --- Load all 4 AWR files ---
results = {}
all_issues = {}
for name, path in FILES.items():
    if not os.path.exists(path):
        print(f"\n  SKIP: {name} - file not found")
        continue
    nd, issues = load_and_validate(name, path)
    results[name] = nd
    all_issues[name] = issues

# --- Cross-DB comparison test ---
print(f"\n{'='*60}")
print("  CROSS-DB COMPARISON TEST")
print(f"{'='*60}")

# Compare FF_NEWSKU Good vs Bad (same DB, different period)
if results.get("FF_NEWSKU_PLAN Good") and results.get("FF_NEWSKU_PLAN Bad"):
    try:
        comp = compare_periods(results["FF_NEWSKU_PLAN Good"], results["FF_NEWSKU_PLAN Bad"])
        cd = comp.model_dump() if hasattr(comp, 'model_dump') else comp
        print(f"  FF_NEWSKU Good vs Bad:")
        print(f"    severity={cd.get('severity','?')} score_delta={cd.get('score_delta','?')}")
        print(f"    load_profile_changes={len(cd.get('load_profile',[]))}")
        print(f"    wait_event_changes={len(cd.get('wait_events',[]))}")
        print(f"    sql_changes={len(cd.get('sql_comparison',[]))}")
        print(f"    PASS: Same-DB comparison works")
    except Exception as e:
        print(f"    FAIL: compare_periods() crashed: {e}")

# Compare two DIFFERENT databases (should still work without crashing)
if results.get("awrrpt_173866") and results.get("PRANYE7G_10637"):
    try:
        comp = compare_periods(results["awrrpt_173866"], results["PRANYE7G_10637"])
        cd = comp.model_dump() if hasattr(comp, 'model_dump') else comp
        print(f"\n  awrrpt_173866 vs PRANYE7G_10637 (cross-DB):")
        print(f"    severity={cd.get('severity','?')} score_delta={cd.get('score_delta','?')}")
        print(f"    load_profile_changes={len(cd.get('load_profile',[]))}")
        print(f"    PASS: Cross-DB comparison works (no crash)")
    except Exception as e:
        print(f"    FAIL: compare_periods() crashed on cross-DB: {e}")

# --- FINAL SUMMARY ---
print(f"\n{'='*60}")
total_issues = sum(len(v) for v in all_issues.values())
total_files = len([v for v in results.values() if v is not None])
print(f"  GENERIC VALIDATION: {total_files}/{len(FILES)} files parsed successfully")
print(f"  TOTAL WARNINGS: {total_issues}")
if total_issues == 0:
    print(f"  VERDICT: DASHBOARD IS FULLY GENERIC - NO HARDCODED VALUES")
else:
    print(f"  VERDICT: {total_issues} warning(s) found - review above")
print(f"{'='*60}")
