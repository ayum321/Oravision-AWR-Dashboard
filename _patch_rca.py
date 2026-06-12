# -*- coding: utf-8 -*-
"""
Rebuild RCA Verdict tab as structured driver cards.
Replaces raw text dump with max 3 structured cards per the spec.
"""

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the comparison RCA rendering (second rca-content innerHTML)
marker = "document.getElementById('rca-content').innerHTML = `"
first_pos = content.index(marker)
second_pos = content.index(marker, first_pos + 100)

# Find where this innerHTML template ends - look for the closing backtick + semicolon
# after the investigation board, then the setTimeout for charts
# The template ends with:  `;\n\n    // Render pie charts
chart_marker = "// Render pie charts"
chart_pos = content.index(chart_marker, second_pos)
# Go backwards to find the closing backtick-semicolon
template_end = content.rfind('`;', second_pos, chart_pos)
assert template_end > 0, "Could not find template end"

# Also find the end of the setTimeout block that renders pie charts + patterns
# It ends with: }, 100);\n}\n
func_end_marker = "function generateComparisonVerdictNarrative"
func_end_pos = content.index(func_end_marker, chart_pos)
# Go back to find the closing of renderComparisonRCA
close_brace = content.rfind('\n}\n', chart_pos, func_end_pos)
assert close_brace > 0, "Could not find function closing"

# Now we need to find the start of the innerHTML assignment
# Include the preparatory code before it (the _critFindings, etc.)
# Actually, let's keep the preparation code and just replace the innerHTML content
# The innerHTML assignment starts at second_pos + len(marker)

# Let's replace from the innerHTML opening backtick to the template_end closing backtick
inner_start = second_pos + len(marker)  # right after the opening backtick
inner_end = template_end  # the closing backtick position

old_inner = content[inner_start:inner_end]
print(f"Replacing RCA innerHTML: {len(old_inner)} chars (L{content[:inner_start].count(chr(10))+1} to L{content[:inner_end].count(chr(10))+1})")

# Build the new driver cards template
new_inner = r'''
        <!-- ═══ RCA VERDICT — STRUCTURED DRIVER CARDS ═══ -->
        ${(() => {
            const vd = ctx.verdict || {};
            const sev = vd.severity || 'STABLE';
            const conf = vd.confidence || 'POSSIBLE';
            const sevColors = { CRITICAL:'#ef4444', DEGRADED:'#f59e0b', WORKLOAD_SHIFT:'#f59e0b', IMPROVED:'#10b981', STABLE:'#64748b' };
            const sevBg = { CRITICAL:'rgba(239,68,68,0.06)', DEGRADED:'rgba(245,158,11,0.06)', WORKLOAD_SHIFT:'rgba(245,158,11,0.06)', IMPROVED:'rgba(16,185,129,0.06)', STABLE:'rgba(100,116,139,0.06)' };
            const sevC = sevColors[sev] || '#64748b';
            const confC = conf === 'CONFIRMED' ? '#34d399' : conf === 'PROBABLE' ? '#fbbf24' : '#94a3b8';

            // Build up to 3 driver cards from culpritCandidates + primary signal
            const drivers = [];
            const topC = vd.topCulprit;
            const candidates = (vd.culpritCandidates || []).slice(0, 3);
            const primary = (vd.primarySignals || [])[0] || {};
            const catalog = primary.type === 'wait_event' ? WAIT_EVENT_CATALOG[primary.metric] : null;

            // Driver 1: Primary driver (topCulprit or primary wait event)
            if (topC) {
                const cls = topC.classification || 'UNKNOWN';
                const clsColors = {
                    CONTENTION_VICTIM:'#ef4444', NEW_HIGH_IMPACT:'#a855f7', PLAN_REGRESSION:'#ef4444',
                    PLAN_IMPROVED:'#10b981', EXEC_REGRESSION:'#f59e0b', HIGH_FREQUENCY_INCREASE:'#f97316',
                    IO_SHIFT:'#3b82f6', NEW_SQL:'#a855f7', STABLE:'#64748b'
                };
                const clsC = clsColors[cls] || '#94a3b8';
                const clsLabels = {
                    CONTENTION_VICTIM:'CONTENTION VICTIM', NEW_HIGH_IMPACT:'NEW HIGH IMPACT',
                    PLAN_REGRESSION:'PLAN REGRESSION', PLAN_IMPROVED:'PLAN IMPROVED',
                    EXEC_REGRESSION:'EXEC REGRESSION', HIGH_FREQUENCY_INCREASE:'HIGH FREQUENCY',
                    IO_SHIFT:'I/O SHIFT', NEW_SQL:'NEW SQL', STABLE:'STABLE'
                };

                // Build causal chain boxes (mechanism-based, not metric names)
                const chainBoxes = [];
                if (catalog) {
                    // Parse mechanism into chain steps
                    const mech = catalog.mechanism || '';
                    const mechParts = mech.split(' \u2014 ');
                    if (mechParts.length >= 2) {
                        chainBoxes.push({ label: mechParts[0], detail: primary.metric, color: sevC });
                        chainBoxes.push({ label: mechParts[1], detail: num(primary.entry?.bad || 0, 1) + '% DB time', color: sevC });
                    } else {
                        chainBoxes.push({ label: catalog.mechanism.split('.')[0], detail: primary.metric, color: sevC });
                    }
                    if (topC.sqlId) {
                        chainBoxes.push({ label: 'SQL: ' + topC.sqlId, detail: (topC.hint || topC.module || '').substring(0, 30), color: '#a855f7' });
                    }
                    if (catalog.fixAction) {
                        chainBoxes.push({ label: 'Fix', detail: catalog.fixAction.substring(0, 40), color: '#10b981' });
                    }
                } else if (primary.type === 'workload_volume') {
                    chainBoxes.push({ label: 'Workload Volume', detail: (primary.delta_pct > 0 ? '+' : '') + num(primary.delta_pct, 0) + '%', color: '#f59e0b' });
                    if (topC.sqlId) chainBoxes.push({ label: 'SQL: ' + topC.sqlId, detail: num(topC.pctDb || 0, 1) + '% DB time', color: '#a855f7' });
                    chainBoxes.push({ label: 'Impact', detail: 'DB Time ' + (vd.dtChange > 0 ? '+' : '') + num(vd.dtChange || 0, 0) + '%', color: sevC });
                }

                const impactPct = topC.pctDb || 0;

                drivers.push({
                    title: vd.rootCause || 'Primary Driver',
                    badge: clsLabels[cls] || cls,
                    badgeColor: clsC,
                    impact: num(impactPct, 1) + '% DB time',
                    chain: chainBoxes,
                    evidence: 'SQL ' + topC.sqlId
                        + (topC.module ? ' \u00b7 Module: ' + topC.module : '')
                        + (topC.tables && topC.tables.length ? ' \u00b7 Tables: ' + topC.tables.slice(0, 3).join(', ') : '')
                        + ' \u00b7 ' + (topC.isNew ? 'New in bad period' : num(topC.epeGood || 0, 2) + 's \u2192 ' + num(topC.epeBad || 0, 2) + 's/exec')
                        + (topC.planChanged ? ' \u00b7 Plan changed' : ''),
                    fix: (vd.actionSteps && vd.actionSteps[0]) ? vd.actionSteps[0].what + (vd.actionSteps[0].query ? ':\n' + vd.actionSteps[0].query : '') : (catalog ? catalog.fixAction : vd.action || ''),
                    fixQuery: (vd.actionSteps && vd.actionSteps[0]) ? vd.actionSteps[0].query : (vd.fixQuery || ''),
                    primary: true
                });
            }

            // Driver 2-3: Secondary drivers from candidates (skip first = topCulprit)
            for (let ci = 1; ci < candidates.length && drivers.length < 3; ci++) {
                const c2 = candidates[ci];
                if (!c2 || !c2.sqlId) continue;
                if (c2.addlSecs !== undefined && Math.abs(c2.addlSecs) < 10) continue; // skip trivial
                const cls2 = c2.classification || 'UNKNOWN';
                const clsC2 = {CONTENTION_VICTIM:'#ef4444',NEW_HIGH_IMPACT:'#a855f7',PLAN_REGRESSION:'#ef4444',EXEC_REGRESSION:'#f59e0b',NEW_SQL:'#a855f7',IO_SHIFT:'#3b82f6'}[cls2] || '#94a3b8';
                drivers.push({
                    title: (c2.hint || 'SQL ' + c2.sqlId) + ' \u2014 ' + (c2.isNew ? 'new high-impact SQL' : cls2.toLowerCase().replace(/_/g, ' ')),
                    badge: cls2.replace(/_/g, ' '),
                    badgeColor: clsC2,
                    impact: num(c2.pctDb || 0, 1) + '% DB time',
                    chain: [],
                    evidence: 'SQL ' + c2.sqlId + ' \u00b7 ' + (c2.isNew ? 'New' : num(c2.epeGood || 0, 2) + 's \u2192 ' + num(c2.epeBad || 0, 2) + 's/exec') + (c2.waitCorrelation ? ' \u00b7 Correlated with ' + (c2.waitCorrelation.event || '') : ''),
                    fix: vd.actionSteps && vd.actionSteps[ci] ? vd.actionSteps[ci].what : 'Review execution plan: SELECT * FROM v$sql_plan WHERE sql_id = \'' + c2.sqlId + '\'',
                    fixQuery: vd.actionSteps && vd.actionSteps[ci] ? vd.actionSteps[ci].query || '' : '',
                    primary: false
                });
            }

            // If no drivers found, create a summary card
            if (drivers.length === 0) {
                drivers.push({
                    title: vd.rootCause || 'No specific SQL culprit identified',
                    badge: sev,
                    badgeColor: sevC,
                    impact: 'DB Time ' + (vd.dtChange > 0 ? '+' : '') + num(vd.dtChange || 0, 0) + '%',
                    chain: [
                        { label: primary.metric || 'Wait Event', detail: num(primary.delta_pp || 0, 1) + 'pp increase', color: sevC },
                        { label: 'Impact', detail: 'DB Time ' + (vd.dtChange > 0 ? '+' : '') + num(vd.dtChange || 0, 0) + '%', color: sevC }
                    ],
                    evidence: 'Primary signal: ' + (primary.metric || 'workload volume') + ' (' + num(primary.delta_pp || primary.delta_pct || 0, 1) + (primary.type === 'wait_event' ? 'pp' : '%') + ')',
                    fix: vd.action || catalog?.fixAction || 'Review top wait events and SQL execution plans',
                    fixQuery: vd.fixQuery || '',
                    primary: true
                });
            }

            // Render verdict header
            let html = '<div style="margin-bottom:16px">';

            // Severity + Confidence header bar
            html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;padding:12px 16px;background:' + sevBg[sev] + ';border:1px solid ' + sevC + '30;border-radius:10px">';
            html += '<div style="display:flex;align-items:center;gap:10px">';
            html += '<div style="width:8px;height:8px;border-radius:50%;background:' + sevC + ';box-shadow:0 0 8px ' + sevC + '"></div>';
            html += '<span style="font-size:11px;font-weight:900;color:' + sevC + ';text-transform:uppercase;letter-spacing:0.8px">' + sev.replace('_', ' ') + '</span>';
            html += '<span style="font-size:10px;color:#94a3b8">\u2014</span>';
            html += '<span style="font-size:11px;color:#e2e8f0;font-weight:600">' + esc(vd.rootCause || '').substring(0, 100) + '</span>';
            html += '</div>';
            html += '<div style="display:flex;align-items:center;gap:6px;padding:3px 10px;background:rgba(15,23,42,0.8);border:1px solid #1e293b;border-radius:6px">';
            html += '<span style="font-size:8px;color:#64748b;text-transform:uppercase;font-weight:700">Confidence</span>';
            html += '<span style="font-size:11px;font-weight:900;color:' + confC + '">' + conf + '</span>';
            html += '</div></div>';

            // Driver cards
            html += '<div style="display:grid;gap:12px">';
            drivers.forEach(function(drv, idx) {
                const borderC = drv.primary ? sevC : drv.badgeColor;
                html += '<div style="background:rgba(10,16,32,0.8);border:1px solid ' + borderC + '25;border-left:3px solid ' + borderC + ';border-radius:10px;padding:14px 16px">';

                // Header: badge + title + impact
                html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">';
                html += '<div style="display:flex;align-items:center;gap:8px;flex:1;min-width:0">';
                if (drv.primary) html += '<span style="font-size:13px;color:' + sevC + '">\u25c6</span>';
                html += '<span style="font-size:8px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;padding:2px 8px;border-radius:4px;background:' + drv.badgeColor + '15;color:' + drv.badgeColor + ';border:1px solid ' + drv.badgeColor + '40">' + esc(drv.badge) + '</span>';
                html += '<span style="font-size:11px;font-weight:700;color:#e2e8f0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(drv.title).substring(0, 80) + '</span>';
                html += '</div>';
                html += '<span style="font-size:11px;font-weight:900;color:' + borderC + ';white-space:nowrap;margin-left:8px">' + drv.impact + '</span>';
                html += '</div>';

                // Causal chain (if present)
                if (drv.chain.length > 0) {
                    html += '<div style="display:flex;align-items:center;gap:0;flex-wrap:wrap;row-gap:6px;margin-bottom:10px">';
                    drv.chain.forEach(function(box, bi) {
                        html += '<div style="background:' + box.color + '08;border:1px solid ' + box.color + '25;border-radius:6px;padding:5px 10px;min-width:90px">';
                        html += '<div style="font-size:8px;color:' + box.color + ';font-weight:800;text-transform:uppercase;letter-spacing:0.3px;margin-bottom:2px">' + esc(box.label) + '</div>';
                        html += '<div style="font-size:9px;color:#94a3b8">' + esc(box.detail) + '</div>';
                        html += '</div>';
                        if (bi < drv.chain.length - 1) html += '<div style="padding:0 4px;color:#334155;font-size:16px;font-weight:bold;flex-shrink:0">\u2192</div>';
                    });
                    html += '</div>';
                }

                // Evidence line
                html += '<div style="font-size:9px;color:#64748b;margin-bottom:8px;padding:4px 8px;background:rgba(15,23,42,0.5);border-radius:4px">';
                html += '<span style="color:#475569;font-weight:700;text-transform:uppercase;font-size:8px;margin-right:6px">Evidence:</span>' + esc(drv.evidence);
                html += '</div>';

                // Fix action
                html += '<div style="display:flex;align-items:flex-start;gap:6px">';
                html += '<span style="font-size:8px;font-weight:800;color:#10b981;text-transform:uppercase;white-space:nowrap;padding-top:1px">FIX:</span>';
                if (drv.fixQuery) {
                    html += '<div style="flex:1"><div style="font-size:9px;color:#d1d5db;margin-bottom:4px">' + esc(drv.fix.split('\n')[0] || drv.fix) + '</div>';
                    html += '<pre style="background:#0a0e1a;border:1px solid #1e293b;border-radius:4px;padding:6px 10px;font-size:9px;color:#e2e8f0;overflow-x:auto;white-space:pre-wrap;margin:0">' + esc(drv.fixQuery) + '</pre></div>';
                } else {
                    html += '<span style="font-size:9px;color:#d1d5db">' + esc(drv.fix) + '</span>';
                }
                html += '</div>';

                html += '</div>'; // close card
            });
            html += '</div>'; // close grid

            // Context notes
            const notes = vd.contextNotes || [];
            if (notes.length > 0) {
                html += '<div style="margin-top:12px;padding:10px 14px;background:rgba(245,158,11,0.04);border:1px solid rgba(245,158,11,0.15);border-radius:8px">';
                html += '<div style="font-size:8px;font-weight:800;color:#f59e0b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">Context</div>';
                notes.forEach(function(n) {
                    html += '<div style="font-size:9px;color:#94a3b8;margin-bottom:2px">\u2022 ' + esc(n) + '</div>';
                });
                html += '</div>';
            }

            html += '</div>'; // close wrapper
            return html;
        })()}

        <!-- Key Metrics Comparison Table -->
        <div class="card p-5 mb-4 fade-in fade-in-d1">
            <div class="text-sm font-bold text-gray-300 mb-3 uppercase tracking-wide">Key Metrics Comparison</div>
            <table class="breakdown-table">
                <thead><tr><th>Metric</th><th style="color:#34d399">${esc(lbl1)} (Baseline)</th><th style="color:#f87171">${esc(lbl2)} (Problem)</th><th>Delta</th><th>Interpretation</th></tr></thead>
                <tbody>
                ${(()=>{
                    const dt1=num((s1.db_time_secs||0)/60,1), dt2=num((s2.db_time_secs||0)/60,1);
                    const dtD=s1.db_time_secs>0?((s2.db_time_secs-s1.db_time_secs)/s1.db_time_secs*100):0;
                    const aas1=num(s1.aas||0,2), aas2=num(s2.aas||0,2);
                    const aasD=s1.aas>0?((s2.aas-s1.aas)/s1.aas*100):0;
                    const cpu1=s1.cpus||0, cpu2=s2.cpus||0;
                    const topW1=ev1[0]?.event_name||'\u2013', topW2=ev2[0]?.event_name||'\u2013';
                    const topWpct1=num(ev1[0]?.pct_db_time||0,1), topWpct2=num(ev2[0]?.pct_db_time||0,1);
                    const btn1=v1.primary_bottleneck?.toUpperCase()||'\u2013', btn2=v2.primary_bottleneck?.toUpperCase()||'\u2013';
                    const rows=[
                        {metric:'DB Time (min)',g:dt1,b:dt2,delta:(dtD>0?'+':'')+num(dtD,0)+'%',dCls:dtD>20?'text-red-400':dtD>0?'text-yellow-400':'text-green-400',interp:dtD>20?'Significant workload increase':dtD>0?'Moderate increase':'Improved or reduced load'},
                        {metric:'AAS',g:aas1,b:aas2,delta:(aasD>0?'+':'')+num(aasD,0)+'%',dCls:(()=>{const c2=s2.cpus||s1.cpus||1;return s2.aas>c2?'text-red-400':s2.aas>c2*0.7?'text-yellow-400':'text-green-400';})(),interp:(()=>{const c2=s2.cpus||s1.cpus||1;return s2.aas>c2?'SATURATED \u2014 sessions exceed '+c2+'-CPU capacity':s2.aas>c2*0.7?'Near saturation ('+num(s2.aas/c2*100,0)+'%)':'Within range ('+num(s2.aas/c2*100,0)+'%)';})()},
                        {metric:'Top Wait',g:topW1+' ('+topWpct1+'%)',b:topW2+' ('+topWpct2+'%)',delta:topW1!==topW2?'CHANGED':'SAME',dCls:topW1!==topW2?'text-orange-400':'text-gray-400',interp:topW1!==topW2?'Dominant wait changed':'Same primary wait'},
                    ];
                    return rows.map(r=>'<tr><td class="text-white font-semibold">'+r.metric+'</td><td class="text-green-300 font-mono">'+r.g+'</td><td class="text-red-300 font-mono">'+r.b+'</td><td class="font-bold '+r.dCls+'">'+r.delta+'</td><td class="text-gray-400 text-xs">'+r.interp+'</td></tr>').join('');
                })()}
                </tbody>
            </table>
        </div>

        <!-- Wait Distribution Charts -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4 fade-in fade-in-d2">
            <div class="card p-4">
                <div class="text-sm font-bold text-green-400 mb-2">${esc(lbl1)} \u2014 Wait Distribution</div>
                <div style="height:200px"><canvas id="rca-pie-1"></canvas></div>
            </div>
            <div class="card p-4">
                <div class="text-sm font-bold text-red-400 mb-2">${esc(lbl2)} \u2014 Wait Distribution</div>
                <div style="height:200px"><canvas id="rca-pie-2"></canvas></div>
            </div>
        </div>
    '''

content = content[:inner_start] + new_inner + content[inner_end:]

# Now remove the old Investigation Board, pie chart rendering, etc.
# The old setTimeout for pie charts should still work since we kept the canvas IDs
# But we removed the Investigation Board HTML, so let's also remove the pattern injection
# Find and clean up renderPatternNotes call for ib-patterns
old_pattern_inject = "if (wkPatterns && wkPatterns.length) renderPatternNotes(wkPatterns, 'ib-patterns');"
if old_pattern_inject in content:
    content = content.replace(old_pattern_inject, "// Pattern notes moved to driver cards")
    print("Cleaned up pattern injection")

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"RCA Verdict tab rebuilt with driver cards")
print(f"Braces: {content.count('{')}/{content.count('}')}")
print(f"Divs: {content.count('<div')}/{content.count('</div>')}")
