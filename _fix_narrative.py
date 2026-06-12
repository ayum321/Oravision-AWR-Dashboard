"""Fix PE narrative generation: severity/bottleneck/IO/root-cause/session issues."""
import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

original = html

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: "Both periods X-bound" → distinguish light-load baseline
# Also fix btnLine to use _baselineLight
# ─────────────────────────────────────────────────────────────────────────────
old1 = (
    "    // ① SEVERITY ASSESSMENT\n"
    "\n"
    "    const satState = s2.aas>cpus\n"
    "\n"
    "        ? `<b class=\"sev-critical\">SATURATED — AAS ${num(s2.aas,1)} exceeds ${cpus}-CPU capacity</b>`\n"
    "\n"
    "        : s2.aas>cpus*0.7\n"
    "\n"
    "        ? `<b class=\"sev-warning\">NEAR CAPACITY — AAS ${num(s2.aas,1)} / ${cpus} CPUs (${num(s2.aas/cpus*100,0)}% utilised)</b>`\n"
    "\n"
    "        : `within capacity — AAS ${num(s2.aas,1)} / ${cpus} CPUs (${num(s2.aas/cpus*100,0)}% utilised)`;\n"
    "\n"
    "    parts.push(\n"
    "\n"
    "        `<b style=\"color:#38bdf8\">① SEVERITY</b> &nbsp;`+\n"
    "\n"
    "        `<b>${esc(lbl2)}</b> consumed <b style=\"color:${dtChange>30?'#f87171':dtChange>10?'#fbbf24':'#34d399'}\">${dtChange>0?'+':''}${dtChange.toFixed(0)}% DB Time</b> `+\n"
    "\n"
    "        `vs <b>${esc(lbl1)}</b> &nbsp;(${num((s1.db_time_secs||0)/60,1)} → <b>${num((s2.db_time_secs||0)/60,1)} min</b>). `+\n"
    "\n"
    "        `System is ${satState}. AAS delta: ${aasChange>0?'+':''}${num(aasChange,0)}%. `+\n"
    "\n"
    "        `${critDelta.length} critical · ${warnDelta.length} warning delta findings.`\n"
    "\n"
    "    );\n"
    "\n"
    "\n"
    "\n"
    "    // ② BOTTLENECK + WAIT EVENT DIAGNOSIS\n"
    "\n"
    "    const btnLine = btn1!==btn2\n"
    "\n"
    "        ? `<b class=\"sev-critical\">Bottleneck shifted: ${btn1L} → ${btn2L}.</b>`\n"
    "\n"
    "        : `Both periods <b>${btn2L}-bound</b>.`;"
)

new1 = (
    "    // ① SEVERITY ASSESSMENT\n"
    "    // Detect light-load baseline: AAS/CPU < 20% means baseline was not stressed\n"
    "    const _baselineLight = s1.aas > 0 && (s1.aas / Math.max(cpus,1)) < 0.2;\n"
    "    const satState = s2.aas>cpus\n"
    "        ? `<b class=\"sev-critical\">SATURATED — AAS ${num(s2.aas,1)} exceeds ${cpus}-CPU capacity</b>`\n"
    "        : s2.aas>cpus*0.7\n"
    "        ? `<b class=\"sev-warning\">NEAR CAPACITY — AAS ${num(s2.aas,1)} / ${cpus} CPUs (${num(s2.aas/cpus*100,0)}% utilised)</b>`\n"
    "        : `within capacity — AAS ${num(s2.aas,1)} / ${cpus} CPUs (${num(s2.aas/cpus*100,0)}% utilised)`;\n"
    "    const baselineDesc = _baselineLight\n"
    "        ? `<b style=\"color:#34d399\">light-load baseline</b> (AAS ${num(s1.aas,2)}/${cpus} CPUs)`\n"
    "        : `<b>${esc(lbl1)}</b>`;\n"
    "    parts.push(\n"
    "        `<b style=\"color:#38bdf8\">① SEVERITY</b> &nbsp;`+\n"
    "        `<b>${esc(lbl2)}</b> consumed <b style=\"color:${dtChange>30?'#f87171':dtChange>10?'#fbbf24':'#34d399'}\">${dtChange>0?'+':''}${dtChange.toFixed(0)}% DB Time</b> `+\n"
    "        `vs ${baselineDesc} &nbsp;(${num((s1.db_time_secs||0)/60,1)} → <b>${num((s2.db_time_secs||0)/60,1)} min</b>). `+\n"
    "        `Problem period: ${satState}. AAS delta: ${aasChange>0?'+':''}${num(aasChange,0)}%. `+\n"
    "        `${critDelta.length} critical · ${warnDelta.length} warning delta findings.`\n"
    "    );\n"
    "\n"
    "\n"
    "    // ② BOTTLENECK + WAIT EVENT DIAGNOSIS\n"
    "    // When baseline was light-load, avoid saying \"both periods X-bound\"\n"
    "    const btnLine = btn1!==btn2\n"
    "        ? `<b class=\"sev-critical\">Bottleneck shifted: ${_baselineLight ? 'light-load baseline' : btn1L} → ${btn2L}.</b>`\n"
    "        : _baselineLight\n"
    "        ? `<b class=\"sev-warning\">Baseline was light-load; problem period became ${btn2L}-stressed.</b>`\n"
    "        : `Both periods <b>${btn2L}-bound</b>.`;"
)

if old1 in html:
    html = html.replace(old1, new1, 1)
    print("FIX 1 applied: Severity + btnLine")
else:
    print("FIX 1 FAILED: could not find target")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 2: I/O line — compare wait CLASS to CLASS, not class% to event name
# Also fix cpuLine missing semicolon
# ─────────────────────────────────────────────────────────────────────────────
old2 = (
    "\n"
    "    const ioLine  = ioPct2>2?`I/O waits: ${num(ioPct1,1)}% → <b style=\"color:${ioPct2>ioPct1+5?'#f87171':'#fbbf24'}\">${num(ioPct2,1)}%</b>${topIoEv?' (\"'+esc(topIoEv.event_name)+'\")':\"\"}`.`:''"
    ";\n"
    "\n"
    "    const conLine"
)

new2 = (
    "\n"
    "    // I/O: compare wait CLASS totals — label as 'User I/O waits', not event name mapped to class%\n"
    "    // Only show event detail if we can compare event-to-event (same event exists in both periods)\n"
    "    const topIoEv1match = topIoEv ? ev1.find(e=>e.event_name===topIoEv.event_name) : null;\n"
    "    const ioEventDetail = topIoEv\n"
    "        ? (topIoEv1match\n"
    "            ? ` (led by \"${esc(topIoEv.event_name)}\": ${num(topIoEv1match.pct_db_time||0,1)}% → ${num(topIoEv.pct_db_time||0,1)}%)`\n"
    "            : ` (top event: \"${esc(topIoEv.event_name)}\" ${num(topIoEv.pct_db_time||0,1)}%)`)\n"
    "        : '';\n"
    "    const ioLine  = ioPct2>2?`User I/O waits: ${num(ioPct1,1)}% → <b style=\"color:${ioPct2>ioPct1+5?'#f87171':'#fbbf24'}\">${num(ioPct2,1)}%</b>${ioEventDetail}.`:'';\n"
    "\n"
    "    const conLine"
)

if old2 in html:
    html = html.replace(old2, new2, 1)
    print("FIX 2 applied: I/O wait class vs event fix")
else:
    print("FIX 2 FAILED: could not find target")
    # Try to find partial
    partial = "const ioLine  = ioPct2>2?`I/O waits:"
    idx = html.find(partial)
    print(f"  Partial search for ioLine: {idx}")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 3: Root cause — use EvidenceObject primaryVerdict when available
# ─────────────────────────────────────────────────────────────────────────────
old3 = (
    "\n"
    "    if(topSql && topW2ev){\n"
    "\n"
    "        const sqlRole=topSql.type==='new'?`introduction of new SQL <code style=\"color:#22d3ee\">${esc(topSql.id||'')}</code>`\n"
    "\n"
    "            :topSql.planChg?`execution plan change on SQL <code style=\"color:#22d3ee\">${esc(topSql.id||'')}</code>`\n"
    "\n"
    "            :`per-exec regression in SQL <code style=\"color:#22d3ee\">${esc(topSql.id||'')}</code>`;\n"
    "\n"
    "        const waitMech=`manifesting as <b>\"${esc(topWName)}\"</b> (${num(topWPct2,1)}% DB time${topWDelta>3?', +'+num(topWDelta,1)+'pp from baseline':''})`;\n"
    "\n"
    "        const lpProof=physD>20?`Physical reads +${num(physD,0)}%`:logD>30?`Logical reads +${num(logD,0)}%`:hpD>30?`Hard parses +${num(hpD,0)}%`:bkD>100?`Block changes +${num(bkD,0)}%`:'';\n"
    "\n"
    "        const effProof=sp2<sp1-3?`Soft parse degraded ${num(sp1,1)}%→${num(sp2,1)}%`:bc2<bc1-2?`Buffer cache dropped ${num(bc1,1)}%→${num(bc2,1)}%`:'';\n"
    "\n"
    "        conclusion=`Primary driver: <b class=\"sev-warning\">${sqlRole}</b>, ${waitMech}`+(lpProof?`, corroborated by Load Profile: ${lpProof}`:'')+( effProof?`; Efficiency impact: ${effProof}`:'')+'.'\n"
    "\n"
    "    } else if(btn1!==btn2){\n"
    "\n"
    "        conclusion=`Bottleneck shift from ${btn1L} to ${btn2L} is the primary driver. `+`\"${esc(topWName)}\" at ${num(topWPct2,1)}% DB time is the dominant symptom.`;\n"
    "\n"
    "    } else {\n"
    "\n"
    "        conclusion=`${btn2L} bottleneck sustained across both periods. `+`\"${esc(topWName)}\" at ${num(topWPct2,1)}% DB ti"
)

new3 = (
    "\n"
    "    // Use EvidenceObject primaryVerdict when available (authoritative single source of truth)\n"
    "    const _ev = ctx.evidence || ctx.verdict;\n"
    "    if (_ev?.primaryVerdict && _ev.primaryVerdict !== 'INCONCLUSIVE') {\n"
    "        const _pv = _ev.primaryVerdict;\n"
    "        const _sqlId = _ev.dominantSQL || topSql?.id || '';\n"
    "        const _sqlShare = _ev.dominantSQLShare > 0 ? ` (${num(_ev.dominantSQLShare,1)}% DB Time)` : '';\n"
    "        const _parallel = _ev.isParallel\n"
    "            ? ` — <b style=\"color:#818cf8\">PARALLEL execution</b> (signals: ${(_ev.parallelSignals||[]).join(', ')})` : '';\n"
    "        const _disqNote = (_ev.disqualifiedCategories||[]).slice(0,2)\n"
    "            .map(d=>`${d.category}: ${d.reason.split('.')[0]}`).join('; ');\n"
    "        const _sideNote = (_ev.sideEffects||[]).length > 0\n"
    "            ? ` Expected side-effects: ${(_ev.sideEffects||[]).slice(0,3).join(', ')}.` : '';\n"
    "        const lpProof = physD>20?`Physical reads +${num(physD,0)}%`:logD>30?`Logical reads +${num(logD,0)}%`:hpD>30?`Hard parses +${num(hpD,0)}%`:'';\n"
    "        if (['DOMINANT_SQL','NEW_SQL','PLAN_CHANGE','SQL_REGRESSION'].includes(_pv)) {\n"
    "            conclusion = `<b style=\"color:#f87171\">SQL <code style=\"color:#22d3ee\">${esc(_sqlId)}</code>${_sqlShare}</b> is the primary driver${_parallel}. ${_ev.primaryReason||''}${_sideNote}`\n"
    "                + (lpProof ? ` Corroborated: ${lpProof}.` : '')\n"
    "                + (_disqNote ? `<br><span style=\"color:#64748b;font-size:9px\">Ruled out — ${esc(_disqNote)}</span>` : '');\n"
    "        } else {\n"
    "            conclusion = `<b style=\"color:#f87171\">${_pv.replace(/_/g,' ')}</b>: ${_ev.primaryReason||''} `\n"
    "                + (topWName ? `\"${esc(topWName)}\" at ${num(topWPct2,1)}% DB time.` : '')\n"
    "                + (_disqNote ? `<br><span style=\"color:#64748b;font-size:9px\">Ruled out — ${esc(_disqNote)}</span>` : '');\n"
    "        }\n"
    "    } else if(topSql && topW2ev){\n"
    "        const sqlRole=topSql.type==='new'?`introduction of new SQL <code style=\"color:#22d3ee\">${esc(topSql.id||'')}</code>`\n"
    "            :topSql.planChg?`execution plan change on SQL <code style=\"color:#22d3ee\">${esc(topSql.id||'')}</code>`\n"
    "            :`per-exec regression in SQL <code style=\"color:#22d3ee\">${esc(topSql.id||'')}</code>`;\n"
    "        const waitMech=`manifesting as <b>\"${esc(topWName)}\"</b> (${num(topWPct2,1)}% DB time${topWDelta>3?', +'+num(topWDelta,1)+'pp from baseline':''})`;\n"
    "        const lpProof=physD>20?`Physical reads +${num(physD,0)}%`:logD>30?`Logical reads +${num(logD,0)}%`:hpD>30?`Hard parses +${num(hpD,0)}%`:bkD>100?`Block changes +${num(bkD,0)}%`:'';\n"
    "        const effProof=sp2<sp1-3?`Soft parse degraded ${num(sp1,1)}%→${num(sp2,1)}%`:bc2<bc1-2?`Buffer cache dropped ${num(bc1,1)}%→${num(bc2,1)}%`:'';\n"
    "        conclusion=`Primary driver: <b class=\"sev-warning\">${sqlRole}</b>, ${waitMech}`+(lpProof?`, corroborated by Load Profile: ${lpProof}`:'')+( effProof?`; Efficiency impact: ${effProof}`:'')+'.'\n"
    "    } else if(_baselineLight) {\n"
    "        conclusion=`Baseline was light-load. Problem period ${btn2L}-stressed with \"${esc(topWName)}\" at ${num(topWPct2,1)}% DB time. Regression is workload-concentration driven.`;\n"
    "    } else if(btn1!==btn2){\n"
    "        conclusion=`Bottleneck shift from ${btn1L} to ${btn2L} is the primary driver. `+`\"${esc(topWName)}\" at ${num(topWPct2,1)}% DB time is the dominant symptom.`;\n"
    "    } else {\n"
    "        conclusion=`${btn2L} bottleneck sustained across both periods. `+`\"${esc(topWName)}\" at ${num(topWPct2,1)}% DB ti"
)

if old3 in html:
    html = html.replace(old3, new3, 1)
    print("FIX 3 applied: Root cause uses EvidenceObject")
else:
    print("FIX 3 FAILED: could not find target")
    partial = "if(topSql && topW2ev){"
    idx = html.find(partial)
    print(f"  Partial search for root cause block: {idx}")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 4: Session narrative — use EvidenceObject sessionLabel, fix logon direction
# ─────────────────────────────────────────────────────────────────────────────
old4 = (
    "    // ⑨ SESSION & LOGON PRESSURE — from analyzeSessionConnections skill\n"
    "\n"
    "    if (sreConn) {\n"
    "\n"
    "        const lpsCol = sreConn.lps>60?'#f87171':sreConn.lps>30?'#fbbf24':'#34d399';\n"
    "\n"
    "        const lpsStr = `<b style=\"color:${lpsCol}\">LPS ${Math.round(sreConn.lps)}/100</b> (${sreConn.lpsRisk==='high'?'HIGH PRESSURE':sreConn.lpsRisk==='medium'?'MODERATE':'STABLE'})`;\n"
    "\n"
    "        const rcaStr = sreConn.rcaText ? `${sreConn.rcaText}` : 'Logon/sec data not captured in AWR Load Profile for this period pair.';\n"
    "\n"
    "        const recStr = sreConn.recommendation && !sreConn.recommendation.includes('Ensure AWR')\n"
    "\n"
    "            ? `<span style=\"color:#60a5fa\">Recommendation: ${esc(sreConn.recommendation)}</span>` : '';\n"
    "\n"
    "        parts.push(`<b style=\"color:#38bdf8\">⑨ SESSION &amp; LOGON PRESSURE</b> &nbsp;${lpsStr}. ${rcaStr}${recStr?'<br>'+recStr:''}`);\n"
    "\n"
    "    }"
)

new4 = (
    "    // ⑨ SESSION & LOGON PRESSURE — from analyzeSessionConnections + EvidenceObject\n"
    "    if (sreConn) {\n"
    "        const _sessEv = ctx.evidence || ctx.verdict;\n"
    "        const _sessLabel = _sessEv?.sessionLabel;  // STABLE|HIGH_PRESSURE|STORM|PARALLEL_EXPANSION\n"
    "        const _sessReason = _sessEv?.sessionReason || '';\n"
    "        const _logonGood = ctx.loadProfile?.good?.logons || 0;\n"
    "        const _logonBad  = ctx.loadProfile?.bad?.logons  || 0;\n"
    "        // Determine actual logon direction from LP rates (never assert +delta if logons decreased)\n"
    "        const _logonDecreased = _logonGood > 0.001 && _logonBad < _logonGood;\n"
    "        const _logonDir = _logonGood > 0.001\n"
    "            ? (_logonDecreased\n"
    "                ? `decreased ${num(_logonGood,2)} → ${num(_logonBad,2)}/s`\n"
    "                : `changed ${num(_logonGood,2)} → ${num(_logonBad,2)}/s`)\n"
    "            : `${num(_logonBad,2)}/s in bad period`;\n"
    "        // Override LPS score/risk when EvidenceObject says stable or parallel expansion\n"
    "        const _forceStable = _sessLabel==='STABLE' || _sessLabel==='PARALLEL_EXPANSION' || _logonDecreased;\n"
    "        const _effectiveLps = _forceStable ? Math.min(sreConn.lps, 10) : sreConn.lps;\n"
    "        const _effectiveRisk = _forceStable ? 'low' : sreConn.lpsRisk;\n"
    "        const lpsCol = _effectiveLps>60?'#f87171':_effectiveLps>30?'#fbbf24':'#34d399';\n"
    "        const lpsLabel = _sessLabel==='PARALLEL_EXPANSION' ? 'PARALLEL EXPANSION'\n"
    "            : _sessLabel==='STORM' && !_forceStable ? 'LOGON STORM'\n"
    "            : _effectiveRisk==='high' ? 'HIGH PRESSURE'\n"
    "            : _effectiveRisk==='medium' ? 'MODERATE' : 'STABLE';\n"
    "        const lpsStr = `<b style=\"color:${lpsCol}\">LPS ${Math.round(_effectiveLps)}/100</b> (${lpsLabel})`;\n"
    "        // Build RCA text — patch if rcaText incorrectly asserts logon increase when logons decreased\n"
    "        let rcaStr = sreConn.rcaText || 'Logon/sec data not captured in AWR Load Profile for this period pair.';\n"
    "        if (_logonDecreased && /logon rate increased|logons.*\\+[0-9]|increased.*logon/i.test(rcaStr)) {\n"
    "            rcaStr = _sessLabel==='PARALLEL_EXPANSION'\n"
    "                ? `Session activity reflects PX slave expansion from the dominant PARALLEL SQL, not genuine user connection growth. `\n"
    "                  + `Logons/sec ${_logonDir}. Connection management overhead was low-impact.`\n"
    "                : `Logons/sec ${_logonDir} — no connection pressure detected. `\n"
    "                  + `Session growth is workload-driven, not connection-driven.`;\n"
    "        }\n"
    "        const recStr = sreConn.recommendation && !sreConn.recommendation.includes('Ensure AWR') && !_forceStable\n"
    "            ? `<span style=\"color:#60a5fa\">Recommendation: ${esc(sreConn.recommendation)}</span>` : '';\n"
    "        const evidenceNote = _sessReason && _sessReason.length < 200\n"
    "            ? `<br><span style=\"color:#64748b;font-size:9px\">${esc(_sessReason)}</span>` : '';\n"
    "        parts.push(`<b style=\"color:#38bdf8\">⑨ SESSION &amp; LOGON PRESSURE</b> &nbsp;${lpsStr}. ${rcaStr}${recStr?'<br>'+recStr:''}${evidenceNote}`);\n"
    "    }"
)

if old4 in html:
    html = html.replace(old4, new4, 1)
    print("FIX 4 applied: Session narrative — EvidenceObject + logon direction")
else:
    print("FIX 4 FAILED: could not find target")
    partial = "// ⑨ SESSION & LOGON PRESSURE"
    idx = html.find(partial)
    print(f"  Partial search for session block: {idx}")

# ─────────────────────────────────────────────────────────────────────────────
# Save
# ─────────────────────────────────────────────────────────────────────────────
if html != original:
    with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("\nFile saved successfully.")
else:
    print("\nWARNING: No changes were made.")
