"""Replace generateComparisonAISummary with answer-first version."""

NEW_FUNC = r'''
function generateComparisonAISummary(ctx) {
    const v = ctx.verdict;
    if (!v || v.severity === 'UNKNOWN') {
        return '<b>Analysis unavailable</b> — insufficient data to generate comparison summary.';
    }

    const {meta, loadProfile, waitEvents, delta, spikes, sqlAttribution, _raw} = ctx;
    const {s1, s2} = _raw;
    const lbl1 = meta.lbl1, lbl2 = meta.lbl2;
    const cpus = meta.cpu_count;
    const execSpike = spikes.exec;
    const eff2 = ctx.instanceEfficiency.bad;
    const eff1 = ctx.instanceEfficiency.good;

    const parts = [];

    // ── [1] ANSWER FIRST: Root cause + severity + action ──────────
    const sevCol = v.severity === 'CRITICAL' ? 'sev-critical' : v.severity === 'WARNING' ? 'sev-warning' : 'sev-good';
    const confBadge = v.confidence === 'CONFIRMED'
        ? '<span style="background:rgba(52,211,153,0.15);color:#34d399;font-size:9px;font-weight:800;padding:1px 6px;border-radius:9999px;margin-left:6px">ADDM CONFIRMED</span>'
        : v.confidence === 'UNKNOWN_PATTERN'
        ? '<span style="background:rgba(248,113,113,0.15);color:#f87171;font-size:9px;font-weight:800;padding:1px 6px;border-radius:9999px;margin-left:6px">UNKNOWN PATTERN</span>'
        : '';
    parts.push(`<b class="${sevCol}">Root Cause:</b> ${esc(v.rootCause)}${confBadge}<br><b style="color:#60a5fa">\u25B6 Action:</b> ${esc(v.action)}`);

    // ── [2] DB Time + AAS headline ────────────────────────────────
    const dtChange = v.dtChange;
    const satDesc = s2.aas > cpus
        ? `<b class="sev-critical">AAS ${num(s2.aas,1)} saturates all ${cpus} CPUs</b>`
        : s2.aas > cpus * 0.7
        ? `AAS ${num(s2.aas,1)} approaching ${cpus}-CPU limit (${num(s2.aas/cpus*100,0)}%)`
        : `AAS ${num(s2.aas,1)} within ${cpus}-CPU capacity (${num(s2.aas/cpus*100,0)}%)`;
    const dtSev = dtChange > 50 ? 'sev-critical' : dtChange > 20 ? 'sev-warning' : 'sev-good';
    const execSurgeLine = execSpike > 30
        ? ` Exec rate <b class="sev-warning">\u2191+${num(execSpike,0)}%</b> amplifies load.`
        : execSpike < -20 ? ` Exec rate \u2193${num(Math.abs(execSpike),0)}% \u2014 degradation is per-call.` : '';
    parts.push(`<b>${esc(lbl2)}</b> DB Time <b class="${dtSev}">${dtChange>0?'\u2191':'\u2193'}${Math.abs(dtChange).toFixed(0)}%</b> vs <b>${esc(lbl1)}</b> (${num((s1.db_time_secs||0)/60,1)}\u2192${num((s2.db_time_secs||0)/60,1)} min). ${satDesc}.${execSurgeLine}`);

    // ── [3] Key metrics that moved (from engine) ──────────────────
    if (v.keyMetrics && v.keyMetrics.length > 0) {
        const kmParts = v.keyMetrics.map(km => {
            const e = km.entry || {};
            const arrow = e.direction === 'up' ? '\u2191' : e.direction === 'down' ? '\u2193' : '\u2192';
            const sev = Math.abs(e.delta_pct) > 30 ? 'sev-warning' : '';
            return `<b${sev ? ' class="'+sev+'"' : ''}>${esc(km.metric.replace(/_/g,' '))}</b> ${arrow}${num(Math.abs(e.delta_pct),0)}%`;
        });
        parts.push(`Key signals: ${kmParts.join(' \u00B7 ')}.`);
    }

    // ── [4] SQL attribution ───────────────────────────────────────
    const topSql = v.topSql || sqlAttribution[0];
    if (topSql) {
        const sqlTypeStr = topSql.type === 'new'
            ? `<b>new SQL</b>`
            : topSql.planChg
            ? `<b class="sev-warning">plan changed</b> (${num(topSql.epe1,2)}s\u2192${num(topSql.epe2,2)}s/exec)`
            : `per-exec ${num(topSql.epe1,2)}s\u2192${num(topSql.epe2,2)}s \u00D7 ${topSql.execs.toLocaleString()} execs`;
        parts.push(`Top SQL: <b class="sev-warning"><code>${esc(topSql.id)}</code></b> (${sqlTypeStr}) \u2014 +${num(topSql.addlSecs,0)}s elapsed (${num(topSql.pctDb,1)}% DB time).`);
    }

    // ── [5] Instance efficiency warnings ──────────────────────────
    const effWarn = [];
    const sp2 = eff2?.soft_parse_pct || 100, sp1 = eff1?.soft_parse_pct || 100;
    const bc2 = eff2?.buffer_cache_hit_pct || 0, bc1 = eff1?.buffer_cache_hit_pct || 0;
    if (sp2 < 80) effWarn.push(`Soft parse <b class="sev-critical">${num(sp2,1)}%</b> \u2014 hard parse storm`);
    else if (sp2 < sp1 - 3) effWarn.push(`Soft parse degraded ${num(sp1,1)}%\u2192${num(sp2,1)}%`);
    if (bc2 < 90) effWarn.push(`Buffer cache <b class="sev-warning">${num(bc2,1)}%</b>`);
    else if (bc2 < bc1 - 2) effWarn.push(`Buffer cache ${num(bc1,1)}%\u2192${num(bc2,1)}%`);
    if (effWarn.length > 0) parts.push(`Efficiency: ${effWarn.join(' \u00B7 ')}.`);

    // ── [6] Rule engine findings ──────────────────────────────────
    const critDelta = delta.filter(f => f.severity === 'critical');
    const warnDelta = delta.filter(f => f.severity === 'warning');
    if (critDelta.length > 0 || warnDelta.length > 0) {
        const signals = [];
        critDelta.slice(0, 2).forEach(f => signals.push(`<b class="sev-critical">${esc(f.metric || f.title || '')}</b>`));
        warnDelta.slice(0, 2).forEach(f => signals.push(`<span class="sev-warning">${esc(f.metric || f.title || '')}</span>`));
        parts.push(`Rule engine: ${critDelta.length} critical + ${warnDelta.length} warning \u2014 ${signals.join(', ')}.`);
    }

    return parts.join('<br><span style="color:#374151;font-size:10px">\u25B8</span> ');
}
'''

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find function boundaries
start_marker = 'function generateComparisonAISummary(ctx) {'
end_marker = '// === CHART RENDERING ==='

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print(f'ERROR: start={start_idx}, end={end_idx}')
    exit(1)

# Find the blank lines before the function
prefix_start = content.rfind('\n\n', 0, start_idx)
if prefix_start == -1:
    prefix_start = start_idx

print(f'Replacing from offset {prefix_start} to {end_idx}')
old_text = content[prefix_start:end_idx]
print(f'Old text length: {len(old_text)} chars')
print(f'First 80 chars: {repr(old_text[:80])}')
print(f'Last 80 chars: {repr(old_text[-80:])}')

new_content = content[:prefix_start] + '\n' + NEW_FUNC + '\n\n' + content[end_idx:]

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f'Done. Old: {len(content)} chars, New: {len(new_content)} chars')
