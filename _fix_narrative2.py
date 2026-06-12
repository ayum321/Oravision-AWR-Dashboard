"""Fix remaining PE narrative issues: ioLine class/event mixing and root cause block."""
with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

original = html

# ─────────────────────────────────────────────────────────────────────────────
# FIX 2: ioLine — change "I/O waits" to "User I/O waits" and add event-to-event comparison
# ─────────────────────────────────────────────────────────────────────────────
idx = html.find('\n    const ioLine  = ioPct2>2?`I/O waits:')
if idx >= 0:
    # Find end of ioLine (next \n\n    const)
    end_marker = '\n\n    const conLine'
    end_idx = html.find(end_marker, idx)
    if end_idx >= 0:
        old_slice = html[idx:end_idx]
        new_slice = (
            "\n"
            "    // I/O: compare wait CLASS totals (User I/O class) — not class% mapped to single event name\n"
            "    // Show event-to-event detail only if same event appears in both periods\n"
            "    const topIoEv1match = topIoEv ? ev1.find(e=>e.event_name===topIoEv.event_name) : null;\n"
            "    const ioEventDetail = topIoEv\n"
            "        ? (topIoEv1match\n"
            "            ? ` (led by \"${esc(topIoEv.event_name)}\": ${num(topIoEv1match.pct_db_time||0,1)}% → ${num(topIoEv.pct_db_time||0,1)}%)`\n"
            "            : ` (top event: \"${esc(topIoEv.event_name)}\" ${num(topIoEv.pct_db_time||0,1)}%)`)\n"
            "        : '';\n"
            "    const ioLine  = ioPct2>2?`User I/O waits: ${num(ioPct1,1)}% → <b style=\"color:${ioPct2>ioPct1+5?'#f87171':'#fbbf24'}\">${num(ioPct2,1)}%</b>${ioEventDetail}.`:'';"
        )
        html = html[:idx] + new_slice + html[end_idx:]
        print(f"FIX 2 applied: ioLine (User I/O waits + event-to-event)")
    else:
        print("FIX 2 FAILED: could not find end marker")
else:
    print("FIX 2 FAILED: could not find ioLine start")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 3: Root cause — prepend EvidenceObject path before topSql fallback
# Replace the entire root cause block from the comment through parts.push
# ─────────────────────────────────────────────────────────────────────────────
rc_start = html.find('    // ⑥ ROOT CAUSE — cross-referenced conclusion')
rc_end_marker = '\n    parts.push(`<b style="color:#38bdf8">⑥ ROOT CAUSE</b>'
rc_end = html.find(rc_end_marker, rc_start)
if rc_start >= 0 and rc_end >= 0:
    # Include the parts.push line itself (find the end of that line)
    rc_end_line = html.find('\n', rc_end + len(rc_end_marker))
    old_block = html[rc_start:rc_end_line]
    new_block = (
        "    // ⑥ ROOT CAUSE — use EvidenceObject primaryVerdict when available\n"
        "    let conclusion='';\n"
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
        "    } else if(typeof _baselineLight !== 'undefined' && _baselineLight) {\n"
        "        conclusion=`Baseline was light-load. Problem period ${btn2L}-stressed with \"${esc(topWName)}\" at ${num(topWPct2,1)}% DB time. Regression is workload-concentration driven.`;\n"
        "    } else if(btn1!==btn2){\n"
        "        conclusion=`Bottleneck shift from ${btn1L} to ${btn2L} is the primary driver. `+`\"${esc(topWName)}\" at ${num(topWPct2,1)}% DB time is the dominant symptom.`;\n"
        "    } else {\n"
        "        conclusion=`${btn2L} bottleneck sustained across both periods. `+`\"${esc(topWName)}\" at ${num(topWPct2,1)}% DB time remains the top constraint.`;\n"
        "    }\n"
        "    parts.push(`<b style=\"color:#38bdf8\">⑥ ROOT CAUSE</b> &nbsp;${conclusion}`);"
    )
    html = html[:rc_start] + new_block + html[rc_end_line:]
    print(f"FIX 3 applied: Root cause uses EvidenceObject")
else:
    print(f"FIX 3 FAILED: rc_start={rc_start}, rc_end={rc_end}")

# ─────────────────────────────────────────────────────────────────────────────
# Save
# ─────────────────────────────────────────────────────────────────────────────
if html != original:
    with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("\nFile saved successfully.")
else:
    print("\nWARNING: No changes were made.")
