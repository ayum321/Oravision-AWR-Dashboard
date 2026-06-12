"""Fix all remaining ? box characters in backend/templates/index.html."""
FILE = 'backend/templates/index.html'
with open(FILE, encoding='utf-8') as f:
    c = f.read()
orig_len = len(c)
fixes = 0

def rep(old, new):
    global c, fixes
    n = c.count(old)
    if n:
        c = c.replace(old, new)
        fixes += n
        print(f"  +{n}  {repr(old[:60])} -> {repr(new[:60])}")
    else:
        print(f"  MISS {repr(old[:60])}")

# Disclaimer warning icon (L1052)
rep(
    '<span class="mt-0.5 shrink-0 text-[22px] leading-none text-Camber">?</span>',
    '<span class="mt-0.5 shrink-0 leading-none text-Camber" style="display:inline-flex;align-items:center">'
    + '<svg xmlns="http://www.w3.org/2000/svg" style="width:22px;height:22px" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">'
    + '<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>'
    + '</svg></span>'
)
# Loading step icon
rep(
    '<span class="loading-step-icon text-gray-700" style="font-size:11px;width:16px;text-align:center">?</span>',
    '<span class="loading-step-icon text-gray-700" style="font-size:11px;width:16px;text-align:center">\u00b7</span>'
)
# Direction arrow: regression line (both variants on same line)
rep(
    'r.direction===\'regression\'\n            ? (_upGood ? `<span style="color:#f87171;font-size:9px">?</span>` : `<span style="color:#f87171;font-size:9px">?</span>`)',
    'r.direction===\'regression\'\n            ? (_upGood ? `<span style="color:#f87171;font-size:9px">\u25bc</span>` : `<span style="color:#f87171;font-size:9px">\u25b2</span>`)'
)
# Direction arrow: improvement line
rep(
    ': r.direction===\'improvement\'\n            ? (_upGood ? `<span style="color:#4ade80;font-size:9px">?</span>` : `<span style="color:#4ade80;font-size:9px">?</span>`)',
    ': r.direction===\'improvement\'\n            ? (_upGood ? `<span style="color:#4ade80;font-size:9px">\u25b2</span>` : `<span style="color:#4ade80;font-size:9px">\u25bc</span>`)'
)
# Direction arrow: neutral
rep(
    ': `<span style="color:#475569;font-size:9px">?</span>`;',
    ': `<span style="color:#475569;font-size:9px">\u2192</span>`;'
)
# Table delta column headers
rep('<th ${TH}>?</th>', '<th ${TH}>\u0394</th>')
# Chain step arrow separator
rep(
    '\'<div style="padding:0 4px;color:#334155;font-size:16px;font-weight:bold;flex-shrink:0">?</div>\'',
    '\'<div style="padding:0 4px;color:#334155;font-size:16px;font-weight:bold;flex-shrink:0">\u2192</div>\''
)
# Hard parses value separator
rep(
    "num(hp1,1) + ' ? ' + num(hp2,1) + ' (+' + num(hpDelta,0)",
    "num(hp1,1) + ' \u2192 ' + num(hp2,1) + ' (+' + num(hpDelta,0)"
)
# Parse Pressure icon
rep(
    "'<span style=\"font-size:14px\">?</span>'",
    "'<span style=\"font-size:14px\">\u26a1</span>'"
)
# Severity palette squares
rep(
    '<span title="Common zone severity colors"><span style="color:#ef4444;font-size:9px">?</span><span style="color:#f97316;font-size:9px">?</span><span style="color:#f59e0b;font-size:9px">?</span><span style="color:#3b82f6;font-size:9px">?</span><span style="color:#818cf8;font-size:9px">?</span>',
    '<span title="Common zone severity colors"><span style="color:#ef4444;font-size:9px">\u25a0</span><span style="color:#f97316;font-size:9px">\u25a0</span><span style="color:#f59e0b;font-size:9px">\u25a0</span><span style="color:#3b82f6;font-size:9px">\u25a0</span><span style="color:#818cf8;font-size:9px">\u25a0</span>'
)
# Good→Bad value arrows (color:#475569;font-size:10px) panels
rep(
    '<span style="color:#475569;font-size:10px">?</span>',
    '<span style="color:#475569;font-size:10px">\u2192</span>'
)
# txn1→txn2 arrow
rep(
    '<div class="text-gray-600 text-base mb-1">?</div>',
    '<div class="text-gray-600 text-base mb-1">\u2192</div>'
)
# "CHANGE" column header label
rep(
    '<div class="text-[9px] text-Cmuted uppercase">?</div>',
    '<div class="text-[9px] text-Cmuted uppercase">CHANGE</div>'
)
# "DB Time ?" label
rep(
    '<div class="text-[9px] text-Cmuted uppercase font-bold mb-1">DB Time ?</div>',
    '<div class="text-[9px] text-Cmuted uppercase font-bold mb-1">DB Time \u0394</div>'
)
# Logons/sec & Net Sessions arrow separators
rep(
    '<span class="text-gray-600 text-[10px]">?</span>',
    '<span class="text-gray-600 text-[10px]">\u2192</span>'
)
# "Net Sessions/sec ?" label
rep(
    '<div class="text-[9px] text-Cblue mb-1 font-bold uppercase">Net Sessions/sec ?</div>',
    '<div class="text-[9px] text-Cblue mb-1 font-bold uppercase">Net Sessions/sec \u0394</div>'
)
# Session metrics table delta header
rep(
    '<td class="pb-1 text-right" style="color:#94a3b8;font-size:10px;font-weight:700">?</td>',
    '<td class="pb-1 text-right" style="color:#94a3b8;font-size:10px;font-weight:700">\u0394</td>'
)
# Exec time good→bad arrow
rep(
    '<span style="color:#475569;font-size:10px;align-self:center">?</span>',
    '<span style="color:#475569;font-size:10px;align-self:center">\u2192</span>'
)
# Green checkmark
rep(
    '<span style="color:#4ade80;font-size:12px;flex-shrink:0">?</span>',
    '<span style="color:#4ade80;font-size:12px;flex-shrink:0">\u2713</span>'
)
# Baseline→Problem separator (12px dark)
rep(
    '\'<span style="color:#334155;font-size:12px">?</span>\'',
    '\'<span style="color:#334155;font-size:12px">\u2192</span>\''
)
# Plan hash separator (3px margin)
rep(
    '<span style="color:#6b7280;margin:0 3px">?</span>',
    '<span style="color:#6b7280;margin:0 3px">\u2192</span>'
)
# Plan hash separator (5px margin)
rep(
    '<span style="color:#6b7280;margin:0 5px">?</span>',
    '<span style="color:#6b7280;margin:0 5px">\u2192</span>'
)
# Row rank indicator
rep(
    '<span style="font-size:8px;color:#334155">?</span>',
    '<span style="font-size:8px;color:#334155">\u25be</span>'
)
# Sort indicators
rep(
    '<span class="sort-ind" style="font-size:9px;color:#475569;font-weight:normal">?</span>',
    '<span class="sort-ind" style="font-size:9px;color:#475569;font-weight:normal">\u21c5</span>'
)
# Exec intelligence separator
rep(
    '\' <span style="color:#475569">?</span> \'',
    '\' <span style="color:#475569">\u2192</span> \''
)
# Wait event pct separator
rep(
    '\'<span style="color:#4ade80">\' + num(r.pct1,1) + \'%</span><span style="color:#475569">?</span>\'',
    '\'<span style="color:#4ade80">\' + num(r.pct1,1) + \'%</span><span style="color:#475569">\u2192</span>\''
)
# avg ms inline separator
rep(
    "num(r.avg1,1) + '?' + num(r.avg2,1) + 'ms'",
    "num(r.avg1,1) + '\u2192' + num(r.avg2,1) + 'ms'"
)

print(f"\nTotal fixes: {fixes}  |  size delta: {len(c)-orig_len}")
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(c)
print("File written.")
"""Fix remaining AWRContext refactoring issues from the first pass."""
import re, sys

FILE = 'backend/templates/index.html'
with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

original_len = len(content.splitlines())
count = 0

# ============================================================
# FIX A: _ctx fallbacks in LP Cross-Correlation (inside template literal)
# These lines have single \n between them, not \n\n
# ============================================================

# The _ctx lines are inside a template literal and have single \n
old_physRead = "const physRead1 = _ctx ? _ctx.loadProfile.good.physical_reads : _lpVal(d1.load_profile,'physical read');"
new_physRead = "const physRead1 = loadProfile.good.physical_reads;"
if old_physRead in content:
    content = content.replace(old_physRead, new_physRead, 1)
    count += 1
    print('FIX A1: physRead1 fixed')

old_physRead2 = "const physRead2 = _ctx ? _ctx.loadProfile.bad.physical_reads : _lpVal(d2.load_profile,'physical read');"
new_physRead2 = "const physRead2 = loadProfile.bad.physical_reads;"
if old_physRead2 in content:
    content = content.replace(old_physRead2, new_physRead2, 1)
    count += 1
    print('FIX A2: physRead2 fixed')

old_logRead1 = "const logRead1  = _ctx ? _ctx.loadProfile.good.logical_reads : _lpVal(d1.load_profile,'logical read');"
new_logRead1 = "const logRead1  = loadProfile.good.logical_reads;"
if old_logRead1 in content:
    content = content.replace(old_logRead1, new_logRead1, 1)
    count += 1
    print('FIX A3: logRead1 fixed')

old_logRead2 = "const logRead2  = _ctx ? _ctx.loadProfile.bad.logical_reads : _lpVal(d2.load_profile,'logical read');"
new_logRead2 = "const logRead2  = loadProfile.bad.logical_reads;"
if old_logRead2 in content:
    content = content.replace(old_logRead2, new_logRead2, 1)
    count += 1
    print('FIX A4: logRead2 fixed')

old_blkChg1 = "const blkChg1   = _ctx ? _ctx.loadProfile.good.block_changes : _lpVal(d1.load_profile,'block change');"
new_blkChg1 = "const blkChg1   = loadProfile.good.block_changes;"
if old_blkChg1 in content:
    content = content.replace(old_blkChg1, new_blkChg1, 1)
    count += 1
    print('FIX A5: blkChg1 fixed')

old_blkChg2 = "const blkChg2   = _ctx ? _ctx.loadProfile.bad.block_changes : _lpVal(d2.load_profile,'block change');"
new_blkChg2 = "const blkChg2   = loadProfile.bad.block_changes;"
if old_blkChg2 in content:
    content = content.replace(old_blkChg2, new_blkChg2, 1)
    count += 1
    print('FIX A6: blkChg2 fixed')

old_txn1 = "const txn1 = _ctx ? _ctx.loadProfile.good.transactions : _lpVal(d1.load_profile,'transaction');"
new_txn1 = "const txn1 = loadProfile.good.transactions;"
if old_txn1 in content:
    content = content.replace(old_txn1, new_txn1, 1)
    count += 1
    print('FIX A7: txn1 fixed')

old_txn2 = "const txn2 = _ctx ? _ctx.loadProfile.bad.transactions : _lpVal(d2.load_profile,'transaction');"
new_txn2 = "const txn2 = loadProfile.bad.transactions;"
if old_txn2 in content:
    content = content.replace(old_txn2, new_txn2, 1)
    count += 1
    print('FIX A8: txn2 fixed')

# Also fix the _ctx declaration
old_ctx_decl = "const _ctx = AWRContext;"
if old_ctx_decl in content:
    content = content.replace(old_ctx_decl, "// loadProfile accessed directly from ctx destructured above", 1)
    count += 1
    print('FIX A9: _ctx decl removed')

# ============================================================
# FIX B: generateComparisonAISummary signature (has \n\n between args)
# ============================================================

# The function has \n\n between the two lines of arguments
old_ai_sig = "function generateComparisonAISummary(crca, s1, s2, ev1, ev2, delta, lbl1, lbl2, execSpike, parseSpike,\n\n        sql1, sql2, eff1, eff2, lp1, lp2, hparse1, hparse2, redo1, redo2) {\n\n    const cpus = s1.cpus||s2.cpus||1;\n\n    const dtChange = s1.db_time_secs>0 ? (s2.db_time_secs-s1.db_time_secs)/s1.db_time_secs*100 : 0;\n\n    const btn1 = _deriveBottleneck(ev1, s1.db_time_secs);\n\n    const btn2 = _deriveBottleneck(ev2, s2.db_time_secs);"

new_ai_sig = """function generateComparisonAISummary(ctx) {

    const {meta, loadProfile, waitEvents, delta, spikes, sqlAttribution, _raw} = ctx;
    const {s1, s2, crca} = _raw;
    const ev1 = waitEvents.good.slice(0, 10), ev2 = waitEvents.bad.slice(0, 10);
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const execSpike = spikes.exec, parseSpike = spikes.parse;
    const sql1 = _raw.good.sql_stats || [], sql2 = _raw.bad.sql_stats || [];
    const eff1 = ctx.instanceEfficiency.good, eff2 = ctx.instanceEfficiency.bad;
    const hparse1 = loadProfile.good.hard_parses, hparse2 = loadProfile.bad.hard_parses;
    const redo1 = loadProfile.good.redo_size, redo2 = loadProfile.bad.redo_size;
    const cpus = meta.cpu_count;

    const dtChange = meta.good.db_time_secs>0 ? (meta.bad.db_time_secs-meta.good.db_time_secs)/meta.good.db_time_secs*100 : 0;

    const btn1 = _deriveBottleneck(ev1, meta.good.db_time_secs);

    const btn2 = _deriveBottleneck(ev2, meta.bad.db_time_secs);"""

if old_ai_sig in content:
    content = content.replace(old_ai_sig, new_ai_sig, 1)
    count += 1
    print('FIX B: AI summary signature replaced')
else:
    print('FIX B: ERROR - AI summary signature still not found')
    # Debug
    idx = content.find('function generateComparisonAISummary(')
    if idx > 0:
        sig = content[idx:idx+400]
        print(f'  Actual sig: {repr(sig[:300])}')

# ============================================================
# FIX C: renderComparisonRCA header (has \n\n between lines)
# ============================================================

old_rca = "function renderComparisonRCA(data) {\n\n    const crca=data.comparison_rca||{}, rca1=crca.rca1||{}, rca2=crca.rca2||{};\n\n    const v1=rca1.verdict||{}, v2=rca2.verdict||{};\n\n    const s1=crca.db_summary_1||{}, s2=crca.db_summary_2||{};\n\n    const lbl1=data._label1||'P1', lbl2=data._label2||'P2';\n\n    const h1=data.health_good||{}, h2=data.health_bad||{};\n\n    const delta=crca.delta_findings||[];\n\n    const d1=data.good_data||{}, d2=data.bad_data||{};\n\n    const ev1=(d1.wait_events||[]).slice(0,10), ev2=(d2.wait_events||[]).slice(0,10);"

new_rca = """function renderComparisonRCA(ctx) {

    // === ALL DATA FROM AWRContext ===
    const {meta, loadProfile, instanceEfficiency, waitEvents, timeModel, delta, spikes, connWaitPct, verdicts, sqlAttribution, _raw} = ctx;
    const {crca, s1, s2, rca1, rca2} = _raw;
    const d1 = _raw.good, d2 = _raw.bad;
    const v1 = verdicts.good, v2 = verdicts.bad;
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const h1 = _raw.health_good, h2 = _raw.health_bad;
    const ev1 = waitEvents.good.slice(0, 10), ev2 = waitEvents.bad.slice(0, 10);"""

if old_rca in content:
    content = content.replace(old_rca, new_rca, 1)
    count += 1
    print('FIX C1: renderComparisonRCA header replaced')
else:
    print('FIX C1: ERROR - RCA header still not found')
    idx = content.find('function renderComparisonRCA(')
    if idx > 0:
        print(f'  Actual: {repr(content[idx:idx+500])}')

# Now remove the old parsing block that follows (sql1r, eff1r, lp1r, _lpVrca, etc.)
old_rca_parsing = "\n    const sql1r=d1.sql_stats||[], sql2r=d2.sql_stats||[], eff1r=d1.efficiency||{}, eff2r=d2.efficiency||{};\n\n    const lp1r=d1.load_profile||[], lp2r=d2.load_profile||[];"

# Try with double newline
if old_rca_parsing in content:
    new_rca_parsing = "\n    const sql1r = d1.sql_stats || [], sql2r = d2.sql_stats || [];\n    const eff1r = instanceEfficiency.good, eff2r = instanceEfficiency.bad;\n    const lp1r = d1.load_profile || [], lp2r = d2.load_profile || [];"
    content = content.replace(old_rca_parsing, new_rca_parsing, 1)
    count += 1
    print('FIX C2: RCA old parsing block replaced')

# Remove _lpVrca and _tmvR helpers
old_lpvrca = "    const _lpVrca = (lp,kw)=>{ const r=(lp||[]).find(l=>(l.stat_name||'').toLowerCase().includes(kw.toLowerCase())); return r?(r.per_sec||r.per_second||0):0; };\n\n    const logon1r=_lpVrca(lp1r,'logon'), logon2r=_lpVrca(lp2r,'logon');"

if old_lpvrca in content:
    new_lpvrca = "    // LP from AWRContext — no re-parsing\n    const logon1r = loadProfile.good.logons, logon2r = loadProfile.bad.logons;"
    content = content.replace(old_lpvrca, new_lpvrca, 1)
    count += 1
    print('FIX C3: _lpVrca removed')

# Remove connW calculation and _tmvR
old_connw = "    const connW2r=ev2.filter(e=>/SQL\\*Net|connection management/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);\n\n    const connW1r=ev1.filter(e=>/SQL\\*Net|connection management/i.test(e.event_name)).reduce((s,e)=>s+(e.pct_db_time||0),0);\n\n    const _tmvR = (tm,kw) => { const r=(tm||[]).find(t=>(t.stat_name||'').toLowerCase().includes(kw.toLowerCase())); return r?(r.time_secs||0):0; };\n\n    const connMgmtR1 = _tmvR(d1.time_model||[],'connection management'), connMgmtR2 = _tmvR(d2.time_model||[],'connection management');"

if old_connw in content:
    new_connw = "    const connW1r = connWaitPct.good, connW2r = connWaitPct.bad;\n    const connMgmtR1 = timeModel.good.connection_mgmt, connMgmtR2 = timeModel.bad.connection_mgmt;"
    content = content.replace(old_connw, new_connw, 1)
    count += 1
    print('FIX C4: connW/tmvR removed')

# Remove old SQL attribution in RCA
old_rca_sql = "    // 3. SQL attribution for breakdown rows\n\n    const _sql1ids=new Set(sql1r.map(s=>s.sql_id)), _map1={};\n\n    sql1r.forEach(s=>{ _map1[s.sql_id]=s; });\n\n    const _sqlAtt=[];\n\n    sql2r.filter(s=>_sql1ids.has(s.sql_id)).forEach(s2x=>{\n\n        const s1x=_map1[s2x.sql_id], e2=(s2x.elapsed_time_secs||0)/Math.max(s2x.executions||1,1), e1=(s1x.elapsed_time_secs||0)/Math.max(s1x.executions||1,1);\n\n        if(e2>e1) _sqlAtt.push({ id:s2x.sql_id, addlSecs:(e2-e1)*(s2x.executions||0), type:'regression', planChg:!!(s1x.plan_hash_value&&s2x.plan_hash_value&&s1x.plan_hash_value!==s2x.plan_hash_value), pctDb:s2x.pct_db_time||0 });\n\n    });\n\n    sql2r.filter(s=>!_sql1ids.has(s.sql_id)).forEach(s2x=>{\n\n        const e2=(s2x.elapsed_time_secs||0)/Math.max(s2x.executions||1,1);"

if old_rca_sql in content:
    new_rca_sql = "    // 3. SQL attribution from AWRContext — already computed\n    const _sqlAtt = sqlAttribution;"
    content = content.replace(old_rca_sql, new_rca_sql, 1)
    count += 1
    print('FIX C5: RCA SQL attribution replaced')
else:
    print('FIX C5: WARNING - RCA SQL block not found, checking if already removed')

# ============================================================
# FIX D: Brace balance - check what the imbalance is
# ============================================================

opens = content.count('{')
closes = content.count('}')
print(f'\nBrace check: open={opens} close={closes} balance={opens-closes}')

# Write
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

final_len = len(content.splitlines())
ticks = content.count('`')
print(f'Final: {final_len} lines')
print(f'Braces: open={opens} close={closes}')
print(f'Backticks: {ticks} (even={ticks%2==0})')
print(f'Total fixes applied: {count}')
