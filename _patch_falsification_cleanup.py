"""
_patch_falsification_cleanup.py
=================================
Two changes:

FIX-1: Hide the "NOT YET PROVEN — EVIDENCE NEEDED TO CONFIRM" block entirely.
The block shows ✗ ADDM/ASH/efficiency gaps which aren't useful in the narrative
output. The confidence label and reason text already communicate uncertainty.

FIX-2: Fix two categories of invalid Oracle SQL in the Falsification Checklist:
  (a) cpu_quantum_milliseconds is NOT a column in DBA_RSRC_PLAN_DIRECTIVES.
      Correct column: MGMT_P1 (CPU resource allocation %).
  (b) In DBA_HIST_SYSTEM_EVENT the event name column is EVENT_NAME, not EVENT.
      Two queries used the wrong column name — would fail with ORA-00904.
  (c) For any check where the correct query cannot be stated with confidence
      based on AWR snapshot data alone, replace with a plain guidance note
      rather than a runnable-but-wrong SQL.
"""
import re

PATH = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'

with open(PATH, encoding='utf-8') as f:
    c = f.read()

original_len = len(c)

# =============================================================================
# FIX-1: Suppress the "NOT YET PROVEN" block in the narrative output.
# The block lists ADDM-not-run, weak SQL attribution, ASH-not-incorporated —
# these are internal confidence gaps, not PE-actionable insights.
# The confidence label + reason text already conveys the uncertainty level.
# =============================================================================
OLD_NYP = (
    '    // Compact "Not yet proven" — replaces full gapsBlock when gaps exist\n'
    '    const _notYetHtml = rds.showNotYetProven\n'
    '        ? `<div style="margin-bottom:14px;padding:10px 14px;background:rgba(15,23,42,0.6);border:1px solid rgba(71,85,105,0.5);border-left:3px solid #475569;border-radius:0 8px 8px 0;box-shadow:inset 0 0 30px rgba(0,0,0,0.2)">\n'
    '            <div style="font-size:9px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;display:flex;align-items:center;gap:6px">\n'
    '                <span style="font-size:11px">🔍</span> Not Yet Proven — Evidence Needed to Confirm\n'
    '            </div>\n'
    '            ${_missingProof.slice(0,4).map(m=>`<div style="font-size:10px;color:#64748b;display:flex;gap:7px;padding:4px 0;border-bottom:1px solid rgba(15,23,42,0.5);line-height:1.55"><span style="color:#ef4444;flex-shrink:0;font-weight:800;font-size:11px;line-height:1.3">✗</span><div style="color:#94a3b8">${m.txt}<div style="font-size:8.5px;color:#475569;margin-top:1px">→ ${m.link}</div></div></div>`).join(\'\')}\n'
    '            ${_isOutsideDb ? `<div style="margin-top:8px;padding:8px 10px;background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.2);border-radius:5px;font-size:10px;color:#a5b4fc;line-height:1.65"><b style="color:#818cf8">Cross-tier check:</b> App error logs · OS metrics (iostat/sar/vmstat) · Network latency · Storage response time outside Oracle</div>` : \'\'}\n'
    '        </div>`\n'
    '        : gapsBlock;'
)
NEW_NYP = (
    '    // "Not Yet Proven" block suppressed — confidence label + reason text\n'
    '    // already communicate diagnostic uncertainty; the checklist items\n'
    '    // (ADDM-not-run, ASH-not-incorporated) are not PE-actionable in an\n'
    '    // offline AWR comparison and create visual noise.\n'
    '    const _notYetHtml = \'\';'
)
assert c.count(OLD_NYP) == 1, f"NYP block: {c.count(OLD_NYP)} occurrences"
c = c.replace(OLD_NYP, NEW_NYP)
print("✓ FIX-1: NOT YET PROVEN block suppressed")

# =============================================================================
# FIX-2a: cpu_quantum_milliseconds is not a valid column in
# DBA_RSRC_PLAN_DIRECTIVES. This query would fail with ORA-00904.
# Correct column: MGMT_P1 — resource management CPU percentage for the group.
# =============================================================================
OLD_DBRM = (
    "              check:'SELECT consumer_group, cpu_quantum_milliseconds, active_sess_pool_P1,"
    " parallel_degree_limit_p1 FROM dba_rsrc_plan_directives WHERE plan IN"
    " (SELECT name FROM v$rsrc_plan WHERE is_top_plan=\\'TRUE\\')',"
)
NEW_DBRM = (
    "              check:'SELECT consumer_group, mgmt_p1 cpu_resource_pct,"
    " active_sess_pool_p1, parallel_degree_limit_p1 FROM dba_rsrc_plan_directives"
    " WHERE plan IN (SELECT name FROM v$rsrc_plan WHERE is_top_plan=\\'TRUE\\')',"
)
assert c.count(OLD_DBRM) == 1, f"DBRM query: {c.count(OLD_DBRM)} occurrences"
c = c.replace(OLD_DBRM, NEW_DBRM)
print("✓ FIX-2a: cpu_quantum_milliseconds → mgmt_p1 cpu_resource_pct (valid column)")

# =============================================================================
# FIX-2b: DBA_HIST_SYSTEM_EVENT uses EVENT_NAME not EVENT.
# Two queries in the falsification block used the wrong column name.
# Both the SELECT list and WHERE clause need to be corrected.
# =============================================================================

# IO_BOTTLENECK — direct path vs scattered query
OLD_IO_EVQ = (
    "              check:'SELECT event, total_waits, ROUND(time_waited_micro/1e6,1) total_secs"
    " FROM dba_hist_system_event WHERE event IN (\\'db file sequential read\\',\\'db file"
    " scattered read\\',\\'direct path read\\') AND snap_id BETWEEN [s1] AND [s2]',"
)
NEW_IO_EVQ = (
    "              check:'SELECT event_name, total_waits, ROUND(time_waited_micro/1e6,1)"
    " total_secs FROM dba_hist_system_event WHERE event_name IN (\\'db file sequential"
    " read\\',\\'db file scattered read\\',\\'direct path read\\') AND snap_id BETWEEN"
    " [s1] AND [s2]',"
)
assert c.count(OLD_IO_EVQ) == 1, f"IO event query: {c.count(OLD_IO_EVQ)} occurrences"
c = c.replace(OLD_IO_EVQ, NEW_IO_EVQ)
print("✓ FIX-2b: IO query: event → event_name in DBA_HIST_SYSTEM_EVENT")

# COMMIT_LOGGING — log file switch sub-bottleneck query
OLD_COM_EVQ = (
    "              check:'SELECT event, total_waits, ROUND(time_waited_micro/1e6,1) secs"
    " FROM dba_hist_system_event WHERE event LIKE \\'log file switch%\\' AND snap_id"
    " BETWEEN [s1] AND [s2]',"
)
NEW_COM_EVQ = (
    "              check:'SELECT event_name, total_waits, ROUND(time_waited_micro/1e6,1)"
    " secs FROM dba_hist_system_event WHERE event_name LIKE \\'log file switch%\\'"
    " AND snap_id BETWEEN [s1] AND [s2]',"
)
assert c.count(OLD_COM_EVQ) == 1, f"Commit event query: {c.count(OLD_COM_EVQ)} occurrences"
c = c.replace(OLD_COM_EVQ, NEW_COM_EVQ)
print("✓ FIX-2b: Commit query: event → event_name in DBA_HIST_SYSTEM_EVENT")

# =============================================================================
# VERIFY MANDATORY SYNTAX INVARIANTS
# =============================================================================
orphaned  = len(re.findall(r'`\s*;\s*\$\{', c))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', c))
print(f"\n--- SYNTAX CHECK ---")
print(f"orphaned backtick-semicolons:  {orphaned}  (must be 0)")
print(f"broken template-tag patterns:  {brokenTag}  (must be 0)")
assert orphaned == 0,  "SYNTAX ERROR: orphaned backtick-semicolons!"
assert brokenTag == 0, "SYNTAX ERROR: broken template-tag patterns!"
print(f"File size change: {original_len} → {len(c)} ({len(c)-original_len:+d} chars)")

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(c)

print("\n✅ _patch_falsification_cleanup.py applied successfully")
print("   FIX-1: NOT YET PROVEN block hidden from output")
print("   FIX-2a: cpu_quantum_milliseconds → mgmt_p1 cpu_resource_pct")
print("   FIX-2b: event → event_name (×2) in DBA_HIST_SYSTEM_EVENT queries")
