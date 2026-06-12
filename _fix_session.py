"""
Comprehensive fix for Session Intelligence Panel:
1. Enhance fallback si object with execute_intelligence, stability.pattern, stability.pattern_detail
2. Fix all ? chars in insight cards to proper Unicode
3. Fix ? in analyzeSessionConnections rcaText
"""
FILE = 'backend/templates/index.html'
with open(FILE, encoding='utf-8') as f:
    c = f.read()
orig = len(c)
fixes = 0

def rep(old, new, label=''):
    global c, fixes
    n = c.count(old)
    if n:
        c = c.replace(old, new)
        fixes += n
        print(f"  +{n}  {label or old[:50]}")
    else:
        print(f"  MISS {label or old[:50]}")

# ============================================================
# PART 1: Enhance the fallback si object with execute_intelligence,
#          stability.pattern, and stability.pattern_detail
# ============================================================

old_fallback = """    if (!si) {
        const lp = ctx.loadProfile || {};
        const lpG = lp.good || {}, lpB = lp.bad || {};
        const elG = (ctx.meta?.good?.elapsed_min || 1) * 60;
        const elB = (ctx.meta?.bad?.elapsed_min || 1) * 60;
        const _aasG = ctx.aas?.good || 0, _aasB = ctx.aas?.bad || 0;
        const cpuCnt = ctx.meta?.cpu_count || 1;
        const logonsG = lpG.logons || 0, logonsB = lpB.logons || 0;
        const connMgmtG = ctx.timeModel?.good?.connection_mgmt || 0;
        const connMgmtB = ctx.timeModel?.bad?.connection_mgmt || 0;
        const execsG = lpG.executes || 0, execsB = lpB.executes || 0;
        si = {
            baseline: { logons_per_sec: logonsG, exec_per_sec: execsG, aas: _aasG, elapsed_sec: elG, conn_mgmt_s: connMgmtG, logons_cumulative_total: logonsG * elG, cpus: cpuCnt },
            comparison: { logons_per_sec: logonsB, exec_per_sec: execsB, aas: _aasB, elapsed_sec: elB, conn_mgmt_s: connMgmtB, logons_cumulative_total: logonsB * elB, cpus: cpuCnt },
            deltas: {},
            stability: { verdict: Math.abs(logonsB - logonsG) / Math.max(logonsG, 0.01) > 1 ? 'UNSTABLE' : Math.abs(logonsB - logonsG) / Math.max(logonsG, 0.01) > 0.3 ? 'ELEVATED' : 'STABLE' }
        };
    }"""

new_fallback = """    if (!si) {
        const lp = ctx.loadProfile || {};
        const lpG = lp.good || {}, lpB = lp.bad || {};
        const elG = (ctx.meta?.good?.elapsed_min || 1) * 60;
        const elB = (ctx.meta?.bad?.elapsed_min || 1) * 60;
        const _aasG = ctx.aas?.good || 0, _aasB = ctx.aas?.bad || 0;
        const cpuCnt = ctx.meta?.cpu_count || 1;
        const logonsG = lpG.logons || 0, logonsB = lpB.logons || 0;
        const connMgmtG = ctx.timeModel?.good?.connection_mgmt || 0;
        const connMgmtB = ctx.timeModel?.bad?.connection_mgmt || 0;
        const execsG = lpG.executes || 0, execsB = lpB.executes || 0;
        const parsesG = lpG.parses || 0, parsesB = lpB.parses || 0;
        const hpG = lpG.hard_parses || 0, hpB = lpB.hard_parses || 0;
        const ucG = lpG.user_calls || 0, ucB = lpB.user_calls || 0;
        const txnG = lpG.transactions || 0, txnB = lpB.transactions || 0;

        // Compute logon deltas
        const _logDelta = logonsG > 0.01 ? ((logonsB - logonsG) / logonsG * 100) : (logonsB > 0 ? 100 : 0);
        const _logAbs = logonsB - logonsG;
        const _execDelta = execsG > 0 ? ((execsB - execsG) / execsG * 100) : (execsB > 0 ? 100 : 0);

        // Derive stability pattern from Oracle-expert session behavior analysis
        const _cumG = logonsG * elG, _cumB = logonsB * elB;
        const _cumRatio = _cumG > 0 ? _cumB / _cumG : 1;
        const _execPerLogG = _cumG > 100 ? (execsG * elG / _cumG) : 0;
        const _execPerLogB = _cumB > 100 ? (execsB * elB / _cumB) : 0;
        const _eplDrop = _execPerLogG > 50 ? ((_execPerLogB - _execPerLogG) / _execPerLogG * 100) : 0;
        const _hpSpike = hpG > 0 ? ((hpB - hpG) / hpG * 100) : (hpB > 1 ? 100 : 0);
        const _connCostG = _cumG > 0 ? (connMgmtG / _cumG * 1000) : 0;
        const _connCostB = _cumB > 0 ? (connMgmtB / _cumB * 1000) : 0;
        const _aasRatio = cpuCnt > 0 ? _aasB / cpuCnt : 0;

        // Pattern classification (Oracle PE expert logic)
        let _pattern, _patternDetail;
        if (_logDelta > 100 && _hpSpike > 40 && connMgmtB > connMgmtG * 1.5) {
            _pattern = 'LOGON_STORM';
            _patternDetail = 'All 3 storm indicators: logon rate +' + Math.round(_logDelta) + '%, hard parses +' + Math.round(_hpSpike) + '%, conn mgmt elevated.';
        } else if (_eplDrop < -25 && _logDelta > 50) {
            _pattern = 'HIGH_CHURN';
            _patternDetail = 'Sessions doing less work each (exec/logon dropped ' + Math.abs(Math.round(_eplDrop)) + '%) despite +' + Math.round(_logDelta) + '% logons \u2014 pool thrashing or retry loop.';
        } else if (_aasRatio > 2 && _logDelta > 20) {
            _pattern = 'AAS_DRIVEN_CHURN';
            _patternDetail = 'AAS ' + _aasB.toFixed(1) + ' is ' + _aasRatio.toFixed(1) + '\u00d7 CPUs. Session growth is secondary to wait/CPU saturation.';
        } else if (_logDelta < -20) {
            _pattern = 'NORMAL_CYCLING';
            _patternDetail = 'Logon rate decreased ' + Math.round(_logDelta) + '% \u2014 no connection pressure. Focus on SQL and wait events.';
        } else if (Math.abs(_logDelta) <= 30 && Math.abs(_execDelta) <= 30) {
            _pattern = 'NORMAL_CYCLING';
            _patternDetail = 'Stable session behavior: logons ' + ((_logDelta >= 0 ? '+' : '') + Math.round(_logDelta)) + '%, executes ' + ((_execDelta >= 0 ? '+' : '') + Math.round(_execDelta)) + '%.';
        } else {
            _pattern = 'FULL_CYCLING';
            _patternDetail = 'Mixed signals: logons ' + ((_logDelta >= 0 ? '+' : '') + Math.round(_logDelta)) + '%, executes ' + ((_execDelta >= 0 ? '+' : '') + Math.round(_execDelta)) + '%. Investigate application behavior.';
        }

        // Stability verdict (upgraded logic)
        let _verdict;
        if (_pattern === 'LOGON_STORM') _verdict = 'CRITICAL';
        else if (_pattern === 'HIGH_CHURN' || (_aasRatio > 2 && _logDelta > 50)) _verdict = 'UNSTABLE';
        else if (Math.abs(_logDelta) > 40 || _pattern === 'AAS_DRIVEN_CHURN' || _pattern === 'FULL_CYCLING') _verdict = 'ELEVATED';
        else if (Math.abs(_logDelta) > 20) _verdict = 'MONITOR';
        else _verdict = 'STABLE';

        // Execute intelligence classification
        let _execLabel;
        if (Math.abs(_execDelta) <= 10) _execLabel = 'STABLE';
        else if (_execDelta > 50) _execLabel = 'SURGE';
        else if (_execDelta > 10) _execLabel = 'CHANGED';
        else if (_execDelta < -30) _execLabel = 'DEGRADED';
        else _execLabel = 'CHANGED';

        si = {
            baseline: { logons_per_sec: logonsG, exec_per_sec: execsG, aas: _aasG, elapsed_sec: elG, conn_mgmt_s: connMgmtG, logons_cumulative_total: _cumG, cpus: cpuCnt },
            comparison: { logons_per_sec: logonsB, exec_per_sec: execsB, aas: _aasB, elapsed_sec: elB, conn_mgmt_s: connMgmtB, logons_cumulative_total: _cumB, cpus: cpuCnt },
            deltas: { logons_per_sec: { base: logonsG, comp: logonsB, abs: _logAbs, pct: Math.round(_logDelta * 10) / 10 } },
            stability: { verdict: _verdict, pattern: _pattern, pattern_detail: _patternDetail },
            execute_intelligence: { exec_per_sec_base: execsG, exec_per_sec_comp: execsB, label: _execLabel, exec_delta_pct: Math.round(_execDelta * 10) / 10 }
        };
    }"""

rep(old_fallback, new_fallback, 'FALLBACK si object enhancement')

# ============================================================
# PART 2: Fix all ? characters in insight card text
# ============================================================

# Action helper
rep(
    "const _act = (txt) => '<div class=\"mt-0.5\" style=\"color:#60a5fa\">? ' + txt + '</div>';",
    "const _act = (txt) => '<div class=\"mt-0.5\" style=\"color:#60a5fa\">\u2192 ' + txt + '</div>';",
    '_act helper ? -> arrow'
)

# Cross-ref helper
rep(
    "const _xref = (txt) => '<span style=\"color:#94a3b8;font-style:italic\">? ' + txt + '</span>';",
    "const _xref = (txt) => '<span style=\"color:#94a3b8;font-style:italic\">\u21d7 ' + txt + '</span>';",
    '_xref helper ? -> arrow'
)

# Rule 1 cards: Wait/CPU/Session saturation
rep("head = '? <b>Wait Saturation</b>", "head = '\u26a0 <b>Wait Saturation</b>", 'Wait Saturation icon')
rep("head = '? <b>CPU Saturation</b>", "head = '\u26a0 <b>CPU Saturation</b>", 'CPU Saturation icon')
rep("head = '? <b>Session Pile-Up</b>", "head = '\u26a0 <b>Session Pile-Up</b>", 'Session Pile-Up icon')

# Rule 2 cards: Logon changes
rep("head = '? <b>More Application Activity</b>", "head = '\u25b2 <b>More Application Activity</b>", 'More App Activity icon')
rep("head = '? <b>More Logons, Less Work/Session</b>", "head = '\u25b2 <b>More Logons, Less Work/Session</b>", 'More Logons Less Work icon')

# Increased Connection Activity + arrow separator
rep(
    "head = '? <b>Increased Connection Activity</b> \\u2014 cumulative logons +' + Math.round(_adjCumDelta) + '% (' + Math.round(cumB).toLocaleString() + ' ? ' + Math.round(cumC).toLocaleString() + ').'",
    "head = '\u25b2 <b>Increased Connection Activity</b> \\u2014 cumulative logons +' + Math.round(_adjCumDelta) + '% (' + Math.round(cumB).toLocaleString() + ' \u2192 ' + Math.round(cumC).toLocaleString() + ').'",
    'Increased Connection icon+arrow'
)

# Reduced Connection Activity
rep(
    "head: '? <b>Reduced Connection Activity</b>",
    "head: '\u25bc <b>Reduced Connection Activity</b>",
    'Reduced Connection icon'
)

# Retry-Storm + arrow separator
rep(
    "head: '? <b>Retry-Storm Pattern</b>",
    "head: '\u26a0 <b>Retry-Storm Pattern</b>",
    'Retry-Storm icon'
)
rep(
    "' + _execPerLogonB.toLocaleString() + ' ? ' + _execPerLogonC.toLocaleString() + '",
    "' + _execPerLogonB.toLocaleString() + ' \u2192 ' + _execPerLogonC.toLocaleString() + '",
    'Retry-Storm value arrow'
)

# Connection Overhead Spike + arrow
rep(
    "head: '? <b>Connection Overhead Spike</b>",
    "head: '\u26a0 <b>Connection Overhead Spike</b>",
    'Connection Overhead icon'
)
rep(
    "connCostB.toFixed(1) + 'ms ? ' + connCostC.toFixed(1) + 'ms",
    "connCostB.toFixed(1) + 'ms \u2192 ' + connCostC.toFixed(1) + 'ms",
    'Connection cost arrow'
)

# No Connection Pooling
rep(
    "head: '? <b>No Connection Pooling</b>",
    "head: '\u26a0 <b>No Connection Pooling</b>",
    'No Connection Pooling icon'
)

# Over-Provisioned Sessions
rep(
    "head: '? <b>Over-Provisioned Sessions</b>",
    "head: '\u2139 <b>Over-Provisioned Sessions</b>",
    'Over-Provisioned icon'
)

# New Workload Detected
rep(
    "head: '? <b>New Workload Detected</b>",
    "head: '\u25b2 <b>New Workload Detected</b>",
    'New Workload icon'
)

# Session Layer Stable
rep(
    "head: '? <b>Session Layer Stable</b>",
    "head: '\u2713 <b>Session Layer Stable</b>",
    'Session Stable icon'
)

# Footer: "RCA Verdict ? Session & Workload"
rep(
    'RCA Verdict ? Session &amp; Workload',
    'RCA Verdict \u203a Session &amp; Workload',
    'RCA Verdict footer arrow'
)

# ============================================================
# PART 3: Fix ? in analyzeSessionConnections rcaText
# ============================================================

# Stable fallback rcaText: "?' + num..."
rep(
    "('?' + num(deltaLogons,0) + '%')",
    "((deltaLogons >= 0 ? '+' : '') + num(deltaLogons,0) + '%')",
    'analyzeSessionConnections stable delta prefix'
)

# Last branch rcaText: "?, ?' + num..."
rep(
    "(LPS ' + lps + ', ?' + num(Math.abs(deltaLogons),0) + '% logons)",
    "(LPS ' + lps + ', ' + (deltaLogons >= 0 ? '+' : '\\u2212') + num(Math.abs(deltaLogons),0) + '% logons)",
    'analyzeSessionConnections last branch delta'
)


print(f"\nTotal fixes: {fixes}  |  size delta: {len(c)-orig}")
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(c)
print("File written.")
