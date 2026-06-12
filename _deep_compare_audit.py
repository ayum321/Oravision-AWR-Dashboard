"""Deep accuracy audit of compare AWR mode - all key areas."""
import requests, json, sys

BASE = "http://127.0.0.1:8000"

# 1. Re-upload GOOD and BAD via COMPARE endpoint (both at once)
print("=" * 70)
print("COMPARE MODE DEEP ACCURACY AUDIT")
print("=" * 70)

print("\n--- Uploading GOOD + BAD via /api/upload/compare ---")
with open(r"C:\Users\1039081\Downloads\GOOD.html", "rb") as g, \
     open(r"C:\Users\1039081\Downloads\BAD.html", "rb") as b:
    r = requests.post(f"{BASE}/api/upload/compare",
                      files={"good_file": ("good.html", g, "text/html"),
                             "bad_file": ("bad.html", b, "text/html")})
upload_resp = r.json()
print(f"  good_upload_id: {upload_resp.get('good_upload_id')}")
print(f"  bad_upload_id: {upload_resp.get('bad_upload_id')}")

# 2. Run compare
print("\n--- Running Compare ---")
r = requests.post(f"{BASE}/api/compare/", json={"good_period": "uploaded_good", "bad_period": "uploaded_bad"})
cmp = r.json()

# Save full response for inspection
with open("_compare_deep_audit.json", "w") as f:
    json.dump(cmp, f, indent=2, default=str)
print(f"  Full compare response saved to _compare_deep_audit.json")

report = cmp.get("report", {})
summary = report.get("summary", {})

# =============================================
# AREA 1: Overall Summary / Verdict
# =============================================
print("\n" + "=" * 70)
print("AREA 1: OVERALL SUMMARY & VERDICT")
print("=" * 70)
print(f"  severity: {summary.get('severity')}")
print(f"  bottleneck_shift: {summary.get('bottleneck_shift')}")
print(f"  causal_chain_text: {summary.get('causal_chain_text','')[:200]}")
print(f"  overall_diagnosis: {summary.get('overall_diagnosis','')[:300]}")
print(f"  ratio_inversion: {summary.get('ratio_inversion')}")
print(f"  confidence_score: {summary.get('confidence_score')}")
print(f"  severity_score: {summary.get('severity_score')}")

# =============================================
# AREA 2: Wait Event Comparisons
# =============================================
print("\n" + "=" * 70)
print("AREA 2: WAIT EVENT COMPARISONS")
print("=" * 70)
wait_data = report.get("top_wait_events", {})
comparisons = wait_data.get("comparisons", [])
print(f"  Total comparisons: {len(comparisons)}")
for w in comparisons:
    name = w.get("event_name", "?")
    cls = w.get("classification", "?")
    good_pct = w.get("good_pct_db_time", 0)
    bad_pct = w.get("bad_pct_db_time", 0)
    delta = w.get("delta_pct_db_time", 0)
    meaning = (w.get("pathology_meaning", "") or "")[:80]
    wc = w.get("wait_class", "")
    print(f"  {name}")
    print(f"    class={cls} | good={good_pct}% | bad={bad_pct}% | delta={delta}pp | wc={wc}")
    print(f"    meaning: {meaning}")

# =============================================
# AREA 3: SQL Regressions
# =============================================
print("\n" + "=" * 70)
print("AREA 3: SQL REGRESSIONS")
print("=" * 70)
regs = report.get("sql_regressions", [])
print(f"  Total regressions: {len(regs)}")
for s in regs:
    sid = s.get("sql_id", "?")
    good_pct = s.get("good_pct_db_time", 0)
    bad_pct = s.get("bad_pct_db_time", 0)
    ratio = s.get("regression_ratio", 0)
    plan_changed = s.get("plan_changed")
    good_plan = s.get("good_plan_hash", "")
    bad_plan = s.get("bad_plan_hash", "")
    good_ela = s.get("good_elapsed_per_exec", 0)
    bad_ela = s.get("bad_elapsed_per_exec", 0)
    good_gets = s.get("good_buffer_gets_per_exec", 0)
    bad_gets = s.get("bad_buffer_gets_per_exec", 0)
    culprit_score = s.get("culprit_score", "")
    culprit_reason = s.get("culprit_reason", "")
    print(f"  {sid}: good={good_pct}% bad={bad_pct}% ratio={ratio:.1f}x plan_changed={plan_changed}")
    print(f"    elapsed/exec: {good_ela} -> {bad_ela}")
    print(f"    gets/exec: {good_gets} -> {bad_gets}")
    print(f"    plans: {good_plan} -> {bad_plan}")
    print(f"    culprit_score={culprit_score} culprit_reason={culprit_reason}")

# =============================================
# AREA 4: Advanced Analytics
# =============================================
print("\n" + "=" * 70)
print("AREA 4: ADVANCED ANALYTICS")
print("=" * 70)
advanced = report.get("advanced", {})
print(f"  Keys in advanced: {list(advanced.keys())}")

# Culprits
culprits = advanced.get("culprits", [])
print(f"\n  Culprits: {len(culprits)}")
for c in culprits:
    print(f"    type={c.get('type','?')} name={c.get('name','?')} score={c.get('score','?')} reason={c.get('reason','?')[:100]}")

# Correlations
corrs = advanced.get("correlations", [])
print(f"\n  Correlations: {len(corrs)}")
for c in corrs[:5]:
    print(f"    {c.get('description','?')[:100]}")

# Root causes
root_causes = advanced.get("root_causes", [])
print(f"\n  Root causes: {len(root_causes)}")
for rc in root_causes[:5]:
    print(f"    category={rc.get('category','?')} evidence={rc.get('evidence','?')[:80]}")

# =============================================
# AREA 5: Recommendations
# =============================================
print("\n" + "=" * 70)
print("AREA 5: RECOMMENDATIONS")
print("=" * 70)
recs = report.get("recommendations", [])
print(f"  Total recommendations: {len(recs)}")
for r in recs[:10]:
    print(f"  [{r.get('priority','?')}] {r.get('category','?')}: {r.get('recommendation','?')[:100]}")
    print(f"    evidence: {r.get('evidence','')[:80]}")

# =============================================
# AREA 6: Load Profile Comparison
# =============================================
print("\n" + "=" * 70)
print("AREA 6: LOAD PROFILE COMPARISON")
print("=" * 70)
lp = report.get("load_profile_comparison", {})
if lp:
    for key in ["db_time_per_s", "db_cpu_per_s", "redo_per_s", "logical_reads_per_s", "physical_reads_per_s", "transactions_per_s", "executions_per_s"]:
        entry = lp.get(key, {})
        if isinstance(entry, dict):
            print(f"  {key}: good={entry.get('good','?')} bad={entry.get('bad','?')} pct_change={entry.get('pct_change','?')}%")
        else:
            print(f"  {key}: {entry}")
else:
    print("  EMPTY - no load profile comparison!")

# =============================================
# AREA 7: Efficiency Comparison
# =============================================
print("\n" + "=" * 70)
print("AREA 7: EFFICIENCY COMPARISON")
print("=" * 70)
eff = report.get("efficiency_comparison", {})
if eff:
    for key, val in eff.items():
        if isinstance(val, dict):
            print(f"  {key}: good={val.get('good','?')} bad={val.get('bad','?')}")
        else:
            print(f"  {key}: {val}")
else:
    print("  EMPTY - no efficiency comparison!")

# =============================================
# AREA 8: AI-RCA Intelligence endpoint
# =============================================
print("\n" + "=" * 70)
print("AREA 8: AI-RCA / INTELLIGENCE ENDPOINT")
print("=" * 70)
try:
    r = requests.post(f"{BASE}/api/ai-rca/analyze", json={"context": {}}, timeout=10)
    rca = r.json()
    print(f"  Status: {r.status_code}")
    print(f"  Keys: {list(rca.keys())[:10]}")
    verdict = rca.get("verdict", rca.get("rca_verdict", ""))
    if isinstance(verdict, dict):
        print(f"  verdict.summary: {str(verdict.get('summary',''))[:200]}")
        print(f"  verdict.root_cause: {str(verdict.get('root_cause',''))[:200]}")
    else:
        print(f"  verdict: {str(verdict)[:200]}")
except Exception as e:
    print(f"  ERROR: {e}")

# =============================================
# AREA 9: Check for empty/missing fields
# =============================================
print("\n" + "=" * 70)
print("AREA 9: EMPTY/MISSING FIELD AUDIT")
print("=" * 70)

issues = []

# Check summary fields
for field in ["severity", "bottleneck_shift", "causal_chain_text", "overall_diagnosis"]:
    val = summary.get(field)
    if not val or val == "" or val == "unknown":
        issues.append(f"summary.{field} is empty/unknown: '{val}'")

# Check wait event fields
for w in comparisons:
    name = w.get("event_name", "?")
    if not w.get("pathology_meaning"):
        issues.append(f"wait '{name}' missing pathology_meaning")
    if not w.get("wait_class") and w.get("classification") in ("new_bottleneck", "worsening"):
        issues.append(f"wait '{name}' ({w.get('classification')}) missing wait_class")

# Check SQL regression fields
for s in regs:
    sid = s.get("sql_id", "?")
    if s.get("culprit_score") in (None, "", 0):
        issues.append(f"SQL {sid} has empty culprit_score")
    if not s.get("culprit_reason"):
        issues.append(f"SQL {sid} has empty culprit_reason")

# Check recommendations
if len(recs) == 0:
    issues.append("No recommendations generated")

# Check load profile
if not lp:
    issues.append("No load profile comparison")

# Check advanced
if not culprits:
    issues.append("No culprits identified")
if not root_causes:
    issues.append("No root causes identified")

print(f"  Total issues found: {len(issues)}")
for i, issue in enumerate(issues):
    print(f"  {i+1}. {issue}")

print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)
