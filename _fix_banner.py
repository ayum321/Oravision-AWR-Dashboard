"""Fix the comparison banner logic:
1. Add dtBegin/dtEnd to _buildSnapMeta return
2. Detect different databases and use date math instead of snap ID math
3. Fix the gap banner to use actual dates
4. Fix the window-order check to use dates when DBs differ
"""
import sys

path = r"backend\templates\index.html"
content = open(path, encoding='utf-8').read()
original = content

# Fix 1: Add dtBegin/dtEnd to _buildSnapMeta return value
old1 = "return { snapBegin, snapEnd, snapIntervals, durationMin, beginMin, endMin,\n                 beginHour, endHour, crossesMidnight, inferredInterval, period,\n                 timeBegin: s.begin_time||'', timeEnd: s.end_time||'' };"
new1 = "return { snapBegin, snapEnd, snapIntervals, durationMin, beginMin, endMin,\n                 beginHour, endHour, crossesMidnight, inferredInterval, period,\n                 dtBegin, dtEnd,\n                 timeBegin: s.begin_time||'', timeEnd: s.end_time||'' };"

if old1 in content:
    content = content.replace(old1, new1, 1)
    print("Fix 1: Added dtBegin/dtEnd to _buildSnapMeta return")
else:
    print("SKIP Fix 1: pattern not found")

# Fix 2: Add cross-DB detection and use real dates for gap/order banners
# Replace the snapIdGap calculation and the Banner F + error check
old2 = """    const snapIdGap = meta2.snapBegin - meta1.snapEnd;
    const sameTime = Math.abs((meta1.beginHour*60+meta1.beginMin) - (meta2.beginHour*60+meta2.beginMin)) <= 30;"""

new2 = """    const diffDB = (s1.db_name||'').toLowerCase() !== (s2.db_name||'').toLowerCase()
                 || (s1.db_id||'') !== (s2.db_id||'');
    const snapIdGap = diffDB ? 0 : (meta2.snapBegin - meta1.snapEnd);
    // Compute actual date gap in days using parsed timestamps
    const _gapDays = (meta1.dtEnd && meta2.dtBegin)
        ? Math.abs(meta2.dtBegin.getTime() - meta1.dtEnd.getTime()) / 86400000
        : null;
    const sameTime = Math.abs((meta1.beginHour*60+meta1.beginMin) - (meta2.beginHour*60+meta2.beginMin)) <= 30;"""

if old2 in content:
    content = content.replace(old2, new2, 1)
    print("Fix 2: Added diffDB detection and real date gap")
else:
    print("SKIP Fix 2: pattern not found")

# Fix 3: Replace Banner F (large gap) to use dates when DBs differ
old3 = """    // Banner F: Large snap ID gap
    if (snapIdGap > 500) {
        const estDays = snapIdGap / (1440 / Math.max(meta1.inferredInterval, 1));
        banners.push({ sev:'warning', color:'#fbbf24', bg:'rgba(251,191,36,0.08)', border:'rgba(251,191,36,0.25)', icon:_iconSvg('calendar','#fbbf24'),
            title:'Large Gap Between Periods (~'+estDays.toFixed(0)+' days)',
            msg:'Good and bad periods are separated by ~'+estDays.toFixed(0)+' days ('+snapIdGap+' snap gap). Optimizer statistics, schema changes, data volume growth, or parameter changes may have occurred independently. Verify baseline validity via dba_tab_statistics.last_analyzed.' });
    }"""

new3 = """    // Banner F: Large gap between periods — use actual dates
    const _gapThresholdDays = 30;
    if (_gapDays !== null && _gapDays > _gapThresholdDays) {
        banners.push({ sev:'warning', color:'#fbbf24', bg:'rgba(251,191,36,0.08)', border:'rgba(251,191,36,0.25)', icon:_iconSvg('calendar','#fbbf24'),
            title:'Large Gap Between Periods (~'+Math.round(_gapDays)+' days)',
            msg:'Good and bad periods are separated by ~'+Math.round(_gapDays)+' days. Optimizer statistics, schema changes, data volume growth, or parameter changes may have occurred independently. Verify baseline validity via dba_tab_statistics.last_analyzed.' });
    } else if (!diffDB && snapIdGap > 500) {
        // Same DB: snap gap is meaningful as secondary signal
        const estDays = snapIdGap / (1440 / Math.max(meta1.inferredInterval, 1));
        if (estDays > _gapThresholdDays) {
            banners.push({ sev:'warning', color:'#fbbf24', bg:'rgba(251,191,36,0.08)', border:'rgba(251,191,36,0.25)', icon:_iconSvg('calendar','#fbbf24'),
                title:'Large Gap Between Periods (~'+estDays.toFixed(0)+' days)',
                msg:'Good and bad periods are separated by ~'+estDays.toFixed(0)+' days ('+snapIdGap+' snap gap). Optimizer statistics, schema changes, data volume growth, or parameter changes may have occurred independently. Verify baseline validity via dba_tab_statistics.last_analyzed.' });
        }
    }"""

if old3 in content:
    content = content.replace(old3, new3, 1)
    print("Fix 3: Fixed Banner F to use actual dates")
else:
    print("SKIP Fix 3: pattern not found")

# Fix 4: Fix the window order error check to handle different DBs
old4 = """    // Error: bad precedes good
    if (snapIdGap < 0) {
        banners.unshift({ sev:'critical', color:'#ef4444', bg:'rgba(239,68,68,0.08)', border:'rgba(239,68,68,0.3)', icon:_iconSvg('critical','#ef4444'),
            title:'Window Order Error',
            msg:'Bad period snap IDs ('+meta2.snapBegin+'\\u2013'+meta2.snapEnd+') precede good period ('+meta1.snapBegin+'\\u2013'+meta1.snapEnd+'). The uploaded files may be reversed.' });
    }"""

new4 = """    // Error: bad precedes good — only valid when same DB
    if (!diffDB && snapIdGap < 0) {
        banners.unshift({ sev:'critical', color:'#ef4444', bg:'rgba(239,68,68,0.08)', border:'rgba(239,68,68,0.3)', icon:_iconSvg('critical','#ef4444'),
            title:'Window Order Error',
            msg:'Bad period snap IDs ('+meta2.snapBegin+'\\u2013'+meta2.snapEnd+') precede good period ('+meta1.snapBegin+'\\u2013'+meta1.snapEnd+'). The uploaded files may be reversed.' });
    }"""

if old4 in content:
    content = content.replace(old4, new4, 1)
    print("Fix 4: Fixed window order check for cross-DB")
else:
    print("SKIP Fix 4: pattern not found")

# Fix 5: Add cross-DB info banner when databases are different
# Insert after Banner B (Same-Time Captures)
old5 = """    // Banner C: Both standard"""
new5 = """    // Banner B2: Cross-database comparison
    if (diffDB) {
        banners.push({ sev:'info', color:'#60a5fa', bg:'rgba(96,165,250,0.08)', border:'rgba(96,165,250,0.25)', icon:_iconSvg('info','#60a5fa'),
            title:'Cross-Database Comparison',
            msg:'Comparing '+esc(s1.db_name||'DB1')+' ('+esc(s1.instance||'')+') vs '+esc(s2.db_name||'DB2')+' ('+esc(s2.instance||'')+').'+(_gapDays!==null?' Periods are ~'+Math.round(_gapDays)+' day'+(Math.round(_gapDays)===1?'':'s')+' apart.':'')+' Snap IDs are unrelated across different databases — time-based comparison used.' });
    }
    // Banner C: Both standard"""

if old5 in content:
    content = content.replace(old5, new5, 1)
    print("Fix 5: Added cross-DB info banner")
else:
    print("SKIP Fix 5: pattern not found")

if content != original:
    open(path, 'w', encoding='utf-8').write(content)
    print(f"\nAll fixes applied to {path}")
else:
    print("\nNo changes made")
