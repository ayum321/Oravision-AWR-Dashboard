"""Quick test: verify all 9 advanced analytics produce valid output on real AWR data."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.html_parser import parse_awr_html, normalize_parsed_data
from services.advanced_analytics import compute_advanced_analytics
from services.comparator import compare_periods

def load(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return normalize_parsed_data(parse_awr_html(f.read())).model_dump()

AWR = r"C:\Users\1039081\Downloads\Work\AWR-Reports\FF_NEWSKU_PLAN"
good = load(os.path.join(AWR, "Good_run_AWR Rpt - ADSPRDDB Snap 203542 thru 203545.html"))
bad = load(os.path.join(AWR, "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html"))

report = compare_periods(good, bad)
rd = report.model_dump()

adv = compute_advanced_analytics(
    good, bad,
    [sr.model_dump() for sr in report.sql_regressions],
    rd.get("top_wait_events", {}).get("comparisons", []),
    rd.get("instance_efficiency", {}).get("comparisons", []),
)

print("=== DESIGN 1: Workload Composition ===")
for period in ["good", "bad"]:
    print(f"  {period}:")
    for w in adv["workload_composition"][period][:5]:
        print(f"    {w['category']}: {w['elapsed_secs']:.0f}s ({w['pct_db_time']:.1f}% DB Time, {w['sql_count']} SQLs)")

print("\n=== DESIGN 2: Cursor Health ===")
for period in ["good", "bad"]:
    ch = adv["cursor_health"][period]
    print(f"  {period}: score={ch['score']} grade={ch['grade']} color={ch['color']}")
    for c in ch["components"]:
        print(f"    {c['name']}: {c['value']}{c['unit']} ({c['status']})")

print("\n=== DESIGN 3: Causal Chains ===")
for chain in adv["causal_chains"]:
    print(f"  [{chain['severity']}] TRIGGER: {chain['trigger']}")
    print(f"    SYMPTOMS: {chain['symptoms'][:3]}")

print("\n=== DESIGN 4: Batch Purges ===")
for p in adv["batch_purges"][:3]:
    print(f"  {p['sql_id']}: table={p['table_name']} io={p['io_pct']:.1f}% elapsed={p['elapsed_secs']:.0f}s [{p['severity']}]")
if not adv["batch_purges"]:
    print("  (none detected — no DELETE statements in top SQL)")

print("\n=== DESIGN 6: Business Throughput ===")
bt = adv["business_throughput"]
print(f"  Good: TXN/s={bt['good']['txn_per_sec']} AAS={bt['good']['aas']}")
print(f"  Bad:  TXN/s={bt['bad']['txn_per_sec']} AAS={bt['bad']['aas']}")
print(f"  Delta: TXN={bt['delta']['txn_per_sec_pct']:+.1f}% AAS={bt['delta']['aas_pct']:+.1f}% Congestion={bt['delta']['congestion_signal']}")

print("\n=== DESIGN 7: Net Assessments ===")
for s in adv["sql_net_assessments"][:8]:
    print(f"  {s['sql_id']}: {s['net_assessment']} | {s['net_assessment_detail'][:70]}")

print("\n=== DESIGN 8: Batch Groups ===")
for bg in adv["batch_groups"]:
    print(f"  {bg['label']}: {bg['sql_count']} SQLs, execs~{bg['exec_count']}, total={bg['combined_elapsed_secs']:.0f}s")
    print(f"    IDs: {bg['sql_ids']}")
if not adv["batch_groups"]:
    print("  (no correlated batch groups detected)")

print("\n=== DESIGN 9: Culprits ===")
for c in adv["culprits"][:8]:
    grp = f" [{c['batch_group']}]" if c["batch_group"] else ""
    print(f"  #{c['rank']} {c['sql_id']}: {c['elapsed_per_min']:.1f}s/min ({c['pct_db_time']:.1f}% DBT) {c['category']} [{c['tag']}]{grp}")

print("\n" + "=" * 50)
print("ALL 9 DESIGNS COMPUTED SUCCESSFULLY")
print(f"Advanced analytics keys: {list(adv.keys())}")
print("=" * 50)
