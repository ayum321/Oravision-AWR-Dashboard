"""Fix CPU_SATURATION action priority queue — merge redundant actions into one."""
import sys

path = r"backend\templates\index.html"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

# ── FIX 1: Replace 2 redundant CPU_SATURATION actions with 1 merged action ──
old_cpu_block = """        } else if (cat === 'CPU_SATURATION') {
            actions.push({
                prio:'IMMEDIATE', col:'#ef4444',
                title:'Reduce concurrent workload or schedule batch jobs off-peak',
                sql:`-- Top CPU-intensive modules during the problem window
SELECT module, COUNT(*) cpu_samples
FROM   dba_hist_active_sess_history
WHERE  session_state = 'ON CPU'
AND    snap_id BETWEEN ${_snB_b} AND ${_snB_e}
GROUP BY module ORDER BY cpu_samples DESC FETCH FIRST 10 ROWS ONLY;`,
                expect:'Identifies modules that can be deferred or throttled to reduce concurrent CPU pressure.'
            });
            actions.push({
                prio:'IMPORTANT', col:'#f59e0b',
                title:'Tune top-N CPU SQL by elapsed/exec',
                sql:`-- Top CPU SQL during problem window
SELECT sql_id,
       ROUND(SUM(cpu_time_delta)/1e6,1) cpu_secs,
       SUM(executions_delta)            execs,
       ROUND(SUM(elapsed_time_delta)/GREATEST(SUM(executions_delta),1)/1e6,3) avg_elapsed_s
FROM   dba_hist_sqlstat
WHERE  snap_id BETWEEN ${_snB_b} AND ${_snB_e}
GROUP BY sql_id
ORDER BY cpu_secs DESC FETCH FIRST 10 ROWS ONLY;`,
                expect:'Top SQL by CPU consumption — target these for predicate/index optimization.'
            });"""

new_cpu_block = """        } else if (cat === 'CPU_SATURATION') {
            actions.push({
                prio:'IMMEDIATE', col:'#ef4444',
                title:'Identify top CPU consumers by module and SQL',
                sql:`-- Top CPU consumers by module + SQL during problem window
SELECT module, sql_id, COUNT(*) cpu_samples,
       ROUND(COUNT(*)*100/SUM(COUNT(*)) OVER(),1) pct_cpu
FROM   dba_hist_active_sess_history
WHERE  session_state = 'ON CPU'
AND    snap_id BETWEEN \${_snB_b} AND \${_snB_e}
GROUP BY module, sql_id
ORDER BY cpu_samples DESC FETCH FIRST 15 ROWS ONLY;`,
                expect:'Cross-reference module with SQL — batch modules can be deferred off-peak, top SQL tuned via DBMS_XPLAN.DISPLAY_AWR.'
            });"""

if old_cpu_block not in src:
    print("ERROR: Could not find CPU_SATURATION actions block to replace")
    sys.exit(1)
src = src.replace(old_cpu_block, new_cpu_block)
print("FIX 1 OK: Merged 2 CPU_SATURATION actions into 1")

# ── FIX 2: Add _classify pattern for 'cpu consumer' before the /identify/ catch-all ──
old_classify = """            if (/identify|review|attribut|ash analysis/.test(t))          return { impact:'TRIAGE',  effort:'LOW',  timeMin:10,  dot:'#06b6d4' };"""
new_classify = """            if (/cpu consumer/.test(t))                                     return { impact:'HIGH',    effort:'LOW',  timeMin:15,  dot:'#ef4444' };
            if (/identify|review|attribut|ash analysis/.test(t))          return { impact:'TRIAGE',  effort:'LOW',  timeMin:10,  dot:'#06b6d4' };"""

if old_classify not in src:
    print("ERROR: Could not find _classify /identify/ pattern")
    sys.exit(1)
src = src.replace(old_classify, new_classify)
print("FIX 2 OK: Added _classify pattern for 'cpu consumer' (HIGH/LOW/15min)")

# ── FIX 3: Add _peContext pattern for 'cpu consumer' before 'ASH module attribution' ──
old_pe = """            // ASH module attribution
            if (/module|action|attribut|originating/.test(t)) return {"""
new_pe = """            // CPU saturation — top consumers
            if (/cpu consumer/.test(t)) return {
                rcaAlignment: 'RCA verdict is CPU saturation \\u2014 AAS exceeds available CPU cores with DB CPU dominating DB Time. No single SQL is the root cause; the bottleneck is aggregate CPU pressure across concurrent sessions. This combined module+SQL query pinpoints exactly where CPU time is spent so you can act on the right target.',
                whatToLookFor: 'If a single module (DBMS_SCHEDULER, batch application) accounts for >50% CPU samples \\u2192 schedule off-peak to reduce concurrent pressure. If CPU is spread across OLTP modules \\u2192 target top 3 SQL IDs for plan analysis via DBMS_XPLAN.DISPLAY_AWR. NULL module = direct connections consuming CPU.',
                conclusiveAction: 'Batch-dominant \\u2192 reschedule to off-peak and re-run AWR comparison to validate. OLTP-dominant \\u2192 tune top SQL (target FTS\\u2192index, nested-loop\\u2192hash join, excessive buffer gets). No tunable inefficiency \\u2192 CPU capacity is the constraint; add cores or RAC node.'
            };
            // ASH module attribution
            if (/module|action|attribut|originating/.test(t)) return {"""

if old_pe not in src:
    print("ERROR: Could not find _peContext 'ASH module attribution' block")
    sys.exit(1)
src = src.replace(old_pe, new_pe)
print("FIX 3 OK: Added _peContext for 'cpu consumer' (before /module/ pattern)")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("\nAll 3 fixes applied successfully.")
