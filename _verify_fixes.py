import requests, json, time

BASE = "http://127.0.0.1:8000"

print("=" * 60)
print("VERIFICATION: Re-upload & Test All Fixes")
print("=" * 60)

# Upload single AWR (TSVBJ4HC)
print("\n--- Uploading TSVBJ4HC single AWR ---")
with open(r"C:\Users\1039081\Downloads\AWR Rpt - TSVBJ4HC Snap 2006 thru 2012.html", "rb") as f:
    r = requests.post(f"{BASE}/api/upload/awr", files={"file": ("tsvbj4hc.html", f, "text/html")})
print(f"Status: {r.status_code}")
single_data = r.json()
d = single_data.get("data", single_data)

# Check wait_class
fg = d.get("_foreground_wait_events", [])
has_wc = sum(1 for e in fg if e.get("wait_class") and e["wait_class"] != "")
print(f"\n1. FOREGROUND WAIT_CLASS: {has_wc}/{len(fg)} events have wait_class")
for e in fg[:5]:
    print(f"   {e.get('event_name','?')}: {e.get('wait_class','EMPTY')}")

# Check plan_hash
sqls = d.get("sql_stats", [])
has_ph = sum(1 for s in sqls if s.get("plan_hash_value") and s["plan_hash_value"] != "")
print(f"\n2. PLAN_HASH: {has_ph}/{len(sqls)} SQLs have plan_hash")
for s in sqls[:5]:
    print(f"   {s.get('sql_id','?')}: plan_hash={s.get('plan_hash_value','EMPTY')}")

# Check efficiency
eff = d.get("efficiency", {})
print(f"\n3. EFFICIENCY: buffer_hit={eff.get('buffer_cache_hit_pct', 'EMPTY')}, "
      f"lib_hit={eff.get('library_cache_hit_pct', 'EMPTY')}, "
      f"soft_parse={eff.get('soft_parse_pct', 'EMPTY')}")

# Upload GOOD + BAD for compare
print("\n--- Uploading GOOD AWR ---")
with open(r"C:\Users\1039081\Downloads\GOOD.html", "rb") as f:
    r = requests.post(f"{BASE}/api/upload/awr", files={"file": ("good.html", f, "text/html")})
print(f"Status: {r.status_code}")
good_data = r.json().get("data", r.json())

print("\n--- Uploading BAD AWR ---")
with open(r"C:\Users\1039081\Downloads\BAD.html", "rb") as f:
    r = requests.post(f"{BASE}/api/upload/awr", files={"file": ("bad.html", f, "text/html")})
print(f"Status: {r.status_code}")
bad_data = r.json().get("data", r.json())

# Check compare mode wait_class
fg_good = good_data.get("_foreground_wait_events", [])
fg_bad = bad_data.get("_foreground_wait_events", [])
wc_good = sum(1 for e in fg_good if e.get("wait_class") and e["wait_class"] != "")
wc_bad = sum(1 for e in fg_bad if e.get("wait_class") and e["wait_class"] != "")
print(f"\n4. COMPARE FG WAIT_CLASS: Good={wc_good}/{len(fg_good)}, Bad={wc_bad}/{len(fg_bad)}")

# Run compare
print("\n--- Running compare ---")
r = requests.post(f"{BASE}/api/compare/", json={"good_period": "uploaded_good", "bad_period": "uploaded_bad"})
compare = r.json()

# Check causal chain
causal = compare.get("report", {}).get("summary", {}).get("causal_chain_text", "")
print(f"\n5. CAUSAL CHAIN: {causal[:200]}")

# Check if it's no longer "Isolated anomalous events"
if "Isolated" in causal:
    print("   *** STILL SHOWS ISOLATED - chain not fixed!")
else:
    print("   *** CAUSAL CHAIN WORKING - events are connected!")

# Check SQL regressions with plan_hash
regs = compare.get("report", {}).get("sql_regressions", [])
has_plan = sum(1 for r in regs if r.get("plan_changed") is not None)
print(f"\n6. COMPARE SQL PLAN DETECTION: {has_plan}/{len(regs)} have plan analysis")

# Check wait event comparisons
wait_comp = compare.get("report", {}).get("top_wait_events", {}).get("comparisons", [])
print(f"\n7. WAIT EVENT COMPARISONS: {len(wait_comp)} events")
for w in wait_comp[:5]:
    name = w.get("event_name", "?")
    cls = w.get("classification", "?")
    bad_pct = w.get("bad_pct_db_time", 0)
    meaning = (w.get("pathology_meaning", "") or "")[:60]
    print(f"   {name}: {bad_pct}% ({cls}) - {meaning}")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
