"""
Patch: implement 6-rule structured verdict narrative.
1. Insert _buildVerdictSignalScore + _buildFalsificationBlock before generateComparisonVerdictNarrative
2. Wire scorecard call after isSqlVerdict declaration
3. Replace existing signal-chip IIFE in whatBlock with scorecard HTML
4. Add falsificationBlock variable computation after howBlock
5. Update verdict label in confidenceBlock to use [CONF] [VERDICT_NAME]
6. Add ${falsificationBlock} to the final template return
"""
import re

FILE = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'

with open(FILE, encoding='utf-8') as f:
    src = f.read()

# ── PATCH 1: Insert two new functions before generateComparisonVerdictNarrative ──

NEW_FUNCTIONS = r"""
// =============================================================================
// VERDICT SIGNAL SCORECARD ENGINE
// Rule 1:  Verdict label = [CONFIDENCE] [VERDICT_NAME] — always both, never one.
// Rule 2:  INCONCLUSIVE is a first-class verdict, not a fallback.
// Rule 6:  N of M signals — show ALL M signal names, values, and fired/not state.
// =============================================================================
function _buildVerdictSignalScore(ctx, finalPv) {
    var lp2  = ctx.loadProfile && ctx.loadProfile.bad  || {};
    var lp1  = ctx.loadProfile && ctx.loadProfile.good || {};
    var ev2  = ctx.waitEvents  && ctx.waitEvents.bad   || [];
    var eff2 = ctx.instanceEfficiency && ctx.instanceEfficiency.bad || {};
    var cpus = (ctx.meta && ctx.meta.cpu_count) || 1;
    var aas2 = (ctx.aas && ctx.aas.bad) || 0;
    var segs = ctx.segments || {};
    var latches    = (ctx._raw && ctx._raw.bad && ctx._raw.bad._latch_activity) || [];
    var tsIO       = ((ctx._raw && ctx._raw.bad && ctx._raw.bad._tablespace_io) || []).filter(function(t){return (t.reads||0)>0;});
    var bufAdv     = (ctx._raw && ctx._raw.bad && ctx._raw.bad._buffer_cache_advisory) || [];
    var sqlAtt     = ctx.sqlAttribution || [];

    var _evPct = function(re){ return ev2.filter(function(e){return re.test(e.event_name||'');}).reduce(function(s,e){return s+(e.pct_db_time||0);},0); };
    var _evWait= function(re){ var e=ev2.find(function(f){return re.test(f.event_name||'');}); return e&&e.avg_wait_ms||0; };

    var cpuPct2       = _evPct(/^DB CPU$/i);
    var seqPct        = _evPct(/db file sequential/i);
    var scaPct        = _evPct(/db file scattered/i);
    var latchPct2     = _evPct(/latch|buffer busy|cursor.*pin|enq:/i);
    var cursorPinXPct = _evPct(/cursor:\s*pin\s+S\s+wait\s+on\s+X/i);
    var cbcPct        = _evPct(/latch:\s*cache buffers chains/i);
    var shpPct        = _evPct(/latch:\s*shared pool|latch:\s*row cache/i);
    var logSyncPct    = _evPct(/log file sync/i);
    var pxWaitPct     = _evPct(/^PX |px deq|parallel query/i);
    var hwEnqPct      = _evPct(/enq:\s*HW\s*-\s*contention/i);
    var resmgrPct     = _evPct(/resmgr:cpu quantum/i);
    var lsWaitMs      = _evWait(/log file sync/i);
    var lbsPct        = _evPct(/log buffer space/i);
    var lsArPct       = _evPct(/log file switch.*archiv/i);
    var hwAvgWait     = _evWait(/enq:\s*HW/i);

    var physDelta = lp1.physical_reads > 0.001 ? ((lp2.physical_reads||0)-(lp1.physical_reads||0))/(lp1.physical_reads)*100 : 0;
    var redoPct   = lp1.redo_size > 0 ? ((lp2.redo_size||0)-(lp1.redo_size||0))/(lp1.redo_size)*100 : 0;
    var bchr      = eff2.buffer_cache_hit_pct || 0;
    var hardParseR= lp2.hard_parses || 0;
    var commitRate= lp2.user_commits || 0;
    var execRate  = lp2.executes || 0;
    var lcRatio   = execRate > 0 ? commitRate/execRate*100 : 0;
    var loopCommit= lcRatio > 15 && logSyncPct > 3;

    var topPhysLabel = (segs.byPhysRead && segs.byPhysRead[0] && segs.byPhysRead[0].object_name) || '';
    var topBufLabel  = (segs.byBufGets  && segs.byBufGets[0]  && segs.byBufGets[0].object_name)  || '';

    var cbcLatch   = latches.find(function(l){return /cache buffers chains/i.test(l.latch_name||'');});
    var cbcMissPct = cbcLatch ? (cbcLatch.miss_pct || (cbcLatch.gets > 0 ? cbcLatch.misses/cbcLatch.gets*100 : 0)) : 0;

    var slowestTs  = tsIO.slice().sort(function(a,b){return (b.avg_read_ms||0)-(a.avg_read_ms||0);}).find(function(t){return (t.avg_read_ms||0)>5;});

    var bufAdvBest = bufAdv.filter(function(r){
        var sf=parseFloat(r.size_factor||r['size factor']||0); return sf>1.0&&sf<=2.0;
    }).sort(function(a,b){
        return parseFloat(a.estd_physical_read_factor||1)-parseFloat(b.estd_physical_read_factor||1);
    })[0];
    var bufAdvPct = bufAdvBest ? Math.round((1-parseFloat(bufAdvBest.estd_physical_read_factor||1))*100) : 0;

    var topSql      = sqlAtt[0] || null;
    var domSqlShare = topSql ? (topSql.pctDb||0) : 0;
    var secondSqlPct= sqlAtt[1] ? (sqlAtt[1].pctDb||0) : 0;

    var f = function(v){ return (+v||0).toFixed(1); };

    var SIGNALS = {
        CPU_SATURATION: [
            { name:'DB CPU % >= 35%',                    fired: cpuPct2>=35,           value: f(cpuPct2)+'%',                    threshold:'>=35%',   panel:'Wait Events',   absentMeans:'CPU not dominant — seek wait-class bottleneck' },
            { name:'AAS > CPU count',                    fired: aas2>cpus,             value: f(aas2)+' vs '+cpus+' CPUs',       threshold:'>CPUs',   panel:'Load Profile',  absentMeans:'No CPU queuing — look at wait-class breakdown' },
            { name:'Hard parse rate > 200/s',            fired: hardParseR>200,        value: f(hardParseR)+'/s',                threshold:'>200/s',  panel:'Load Profile',  absentMeans:'Parse overhead not a significant CPU contributor' },
            { name:'cursor: pin S wait > 2%',            fired: cursorPinXPct>2,       value: f(cursorPinXPct)+'%',              threshold:'>2%',     panel:'Wait Events',   absentMeans:'No parse-mutex serialisation' },
            { name:'Latch contention < 5% (clean CPU)',  fired: latchPct2<5,           value: f(latchPct2)+'%',                  threshold:'<5%',     panel:'Wait Events',   absentMeans:'Latch overhead inflating CPU — may be CONCURRENCY, not CPU_SAT' },
            { name:'PX workers not inflating AAS',       fired: pxWaitPct<3,           value: f(pxWaitPct)+'%',                  threshold:'<3%',     panel:'Wait Events',   absentMeans:'Parallel workers multiplying CPU demand — DOP reduction needed first' },
            { name:'resmgr:cpu quantum absent',          fired: resmgrPct<2,           value: f(resmgrPct)+'%',                  threshold:'<2%',     panel:'Wait Events',   absentMeans:'Resource Manager throttling — saturation is policy-enforced, not organic' }
        ],
        IO_BOTTLENECK: [
            { name:'db file sequential read >= 5%',      fired: seqPct>=5,             value: f(seqPct)+'%',                     threshold:'>=5%',    panel:'Wait Events',   absentMeans:'Index reads not the primary I/O type' },
            { name:'db file scattered read >= 3%',       fired: scaPct>=3,             value: f(scaPct)+'%',                     threshold:'>=3%',    panel:'Wait Events',   absentMeans:'Full scans not primary I/O type' },
            { name:'Physical reads delta > 30%',         fired: physDelta>30,          value: '+'+f(physDelta)+'%',              threshold:'>30%',    panel:'Load Profile',  absentMeans:'Physical read volume unchanged — I/O may be baseline behavior' },
            { name:'BCHR < 95%',                         fired: bchr>0&&bchr<95,       value: f(bchr)+'%',                       threshold:'<95%',    panel:'Efficiency',    absentMeans:'Buffer cache hit rate adequate — reads are from cache, not disk' },
            { name:'Storage latency > 5ms (TS I/O)',     fired: !!slowestTs,           value: slowestTs ? f(slowestTs.avg_read_ms)+'ms' : 'N/A', threshold:'>5ms', panel:'TS I/O Stats', absentMeans:'Storage latency within SLA — volume, not speed, is the constraint' },
            { name:'Top physical segment identified',    fired: !!topPhysLabel,        value: topPhysLabel||'Not found',         threshold:'Present', panel:'Segments',      absentMeans:'Cannot pinpoint which segment drives the reads' },
            { name:'Buffer cache advisory > 10%',        fired: bufAdvPct>10,          value: bufAdvPct+'% reduction est.',      threshold:'>10%',    panel:'Advisory',      absentMeans:'More buffer cache will not reduce physical reads — not a cache sizing issue' }
        ],
        COMMIT_LOGGING: [
            { name:'log file sync >= 5% DB Time',        fired: logSyncPct>=5,         value: f(logSyncPct)+'%',                 threshold:'>=5%',    panel:'Wait Events',   absentMeans:'log file sync not dominant — check log switch / archiver variant' },
            { name:'Commit rate > 50/s',                 fired: commitRate>50,         value: f(commitRate)+'/s',                threshold:'>50/s',   panel:'Load Profile',  absentMeans:'Commit frequency is not the driver' },
            { name:'Loop-commit pattern confirmed',      fired: loopCommit,            value: loopCommit ? f(lcRatio)+'% ratio' : 'Not detected', threshold:'>15%', panel:'Load Profile', absentMeans:'Commits batched — frequency appropriate; check storage speed' },
            { name:'log file sync avg wait > 2ms',       fired: lsWaitMs>2,            value: f(lsWaitMs)+'ms',                  threshold:'>2ms',    panel:'Wait Events',   absentMeans:'LGWR disk speed adequate — pure frequency problem, not storage' },
            { name:'Redo size increased > 20%',          fired: redoPct>20,            value: '+'+f(redoPct)+'%',                threshold:'>20%',    panel:'Load Profile',  absentMeans:'Redo volume stable — DML pattern unchanged from baseline' },
            { name:'No log switch sub-bottleneck',       fired: lbsPct<2&&lsArPct<2,  value: 'lbs:'+f(lbsPct)+'% arc:'+f(lsArPct)+'%', threshold:'Both<2%', panel:'Wait Events', absentMeans:'Secondary log bottleneck present — check log_buffer or ARCn count' }
        ],
        CONCURRENCY: [
            { name:'Total latch/enqueue >= 5%',          fired: latchPct2>=5,          value: f(latchPct2)+'%',                  threshold:'>=5%',    panel:'Wait Events',   absentMeans:'No significant concurrency contention' },
            { name:'CBC latch >= 2%',                    fired: cbcPct>=2,             value: f(cbcPct)+'%',                     threshold:'>=2%',    panel:'Wait Events',   absentMeans:'Hot-block contention not present' },
            { name:'cursor: pin S wait >= 2%',           fired: cursorPinXPct>=2,      value: f(cursorPinXPct)+'%',              threshold:'>=2%',    panel:'Wait Events',   absentMeans:'No parse-mutex serialisation' },
            { name:'Shared pool latch >= 2%',            fired: shpPct>=2,             value: f(shpPct)+'%',                     threshold:'>=2%',    panel:'Wait Events',   absentMeans:'No shared pool allocation pressure' },
            { name:'CBC latch miss ratio > 0.5%',        fired: cbcMissPct>0.5,        value: f(cbcMissPct)+'%',                 threshold:'>0.5%',   panel:'Latch Activity',absentMeans:'Low miss rate — hot block not confirmed by latch activity' },
            { name:'Hard parse rate > 100/s',            fired: hardParseR>100,        value: f(hardParseR)+'/s',                threshold:'>100/s',  panel:'Load Profile',  absentMeans:'No hard parse contribution to library cache pressure' },
            { name:'Hot segment identified (buf gets)',  fired: !!topBufLabel,         value: topBufLabel||'Not found',          threshold:'Present', panel:'Segments',      absentMeans:'Cannot confirm hot block source from segment stats' }
        ],
        SQL_VERDICT: [
            { name:'SQL dominates >= 15% DB Time',       fired: domSqlShare>=15,       value: f(domSqlShare)+'%',                threshold:'>=15%',   panel:'SQL Analysis',  absentMeans:'No single SQL is dominant — diffuse load or workload volume change' },
            { name:'Plan hash changed',                  fired: !!(topSql&&topSql.planChg), value: (topSql&&topSql.planChg)?'Changed':'Stable', threshold:'Changed', panel:'SQL Analysis', absentMeans:'Same plan — not plan regression; check data volume or frequency' },
            { name:'SQL absent from baseline (new)',     fired: !!(topSql&&topSql.type==='new'), value: (topSql&&topSql.type==='new')?'New in problem':'In both', threshold:'New', panel:'SQL Analysis', absentMeans:'SQL ran in baseline — regression, not new workload' },
            { name:'Physical reads spike > 50%',         fired: physDelta>50,          value: '+'+f(physDelta)+'%',              threshold:'>50%',    panel:'Load Profile',  absentMeans:'Physical I/O not spiking — plan uses same access path' },
            { name:'Buffer gets/exec elevated (>50K)',   fired: !!(topSql&&(topSql.gets||0)>50000), value: topSql ? Math.round((topSql.gets||0)/1000)+'K/exec' : '0', threshold:'>50K', panel:'SQL Analysis', absentMeans:'Logical I/O per execution reasonable — not a cardinality/plan issue' },
            { name:'Top SQL dominates vs 2nd SQL',       fired: domSqlShare>20&&secondSqlPct<domSqlShare*0.5, value: 'Top:'+f(domSqlShare)+'% 2nd:'+f(secondSqlPct)+'%', threshold:'Top>2x 2nd', panel:'SQL Analysis', absentMeans:'Multiple SQLs contributing equally — single-SQL fix insufficient' },
            { name:'No competing bottleneck class',      fired: latchPct2<10&&logSyncPct<8, value: 'latch:'+f(latchPct2)+'% sync:'+f(logSyncPct)+'%', threshold:'Both low', panel:'Wait Events', absentMeans:'Secondary bottleneck present — SQL fix alone may not restore baseline' }
        ],
        HW_ENQUEUE_CONTENTION: [
            { name:'enq: HW >= 5% DB Time',             fired: hwEnqPct>=5,           value: f(hwEnqPct)+'%',                   threshold:'>=5%',    panel:'Wait Events',   absentMeans:'HW contention not confirmed from wait events' },
            { name:'Concurrent INSERT pattern',          fired: commitRate>20,         value: f(commitRate)+'/s',                threshold:'>20/s',   panel:'Load Profile',  absentMeans:'Not a concurrent insert pattern' },
            { name:'HW avg wait > 10ms',                 fired: hwAvgWait>10,          value: f(hwAvgWait)+'ms',                 threshold:'>10ms',   panel:'Wait Events',   absentMeans:'Short waits — ASSM may be self-managing' },
            { name:'SQL identified as DML carrier',      fired: !!topSql,              value: topSql ? 'SQL '+topSql.id : 'Not identified', threshold:'Present', panel:'SQL Analysis', absentMeans:'Cannot confirm insert-pattern SQL without SQL attribution' },
            { name:'Segment identified',                 fired: !!topPhysLabel,        value: topPhysLabel||'Not found',         threshold:'Present', panel:'Segments',      absentMeans:'Must identify target segment before pre-allocating extents' }
        ]
    };

    var SQL_VERDICTS = ['DOMINANT_SQL','NEW_SQL','PLAN_CHANGE','SQL_REGRESSION','SQL_DOMINANT'];
    var sigKey = SQL_VERDICTS.indexOf(finalPv) >= 0 ? 'SQL_VERDICT' : (SIGNALS[finalPv] ? finalPv : 'CPU_SATURATION');
    var sigs   = SIGNALS[sigKey] || SIGNALS.CPU_SATURATION;
    var n      = sigs.filter(function(s){return s.fired;}).length;
    var m      = sigs.length;

    var confLevel = n >= Math.ceil(m*0.57) ? 'CONFIRMED'
                  : n >= 2                 ? 'PROBABLE'
                  : n === 1               ? 'POSSIBLE'
                  :                         'INCONCLUSIVE';

    var VERDICT_NAMES = {
        CPU_SATURATION:'CPU_SATURATION', IO_BOTTLENECK:'IO_BOTTLENECK',
        COMMIT_LOGGING:'COMMIT_FREQUENCY', CONCURRENCY:'CONCURRENCY_CONTENTION',
        PLAN_CHANGE:'PLAN_REGRESSION', DOMINANT_SQL:'DOMINANT_SQL',
        NEW_SQL:'NEW_WORKLOAD', SQL_REGRESSION:'SQL_REGRESSION',
        SQL_DOMINANT:'SQL_DOMINANT', HW_ENQUEUE_CONTENTION:'HW_ENQUEUE',
        TX_INDEX_CONTENTION:'TX_INDEX_CONTENTION',
        TX_ROW_LOCK_CONTENTION:'TX_ROW_LOCK',
        UNDO_SEGMENT_EXTENSION:'UNDO_EXTENSION',
        BUFFER_WRITE_PRESSURE:'BUFFER_WRITE_PRESSURE'
    };
    var vName = VERDICT_NAMES[finalPv] || (finalPv||'').replace(/_/g,' ');
    var label = confLevel === 'INCONCLUSIVE' ? 'INCONCLUSIVE \u2014 MULTIPLE HYPOTHESES'
              : (confLevel + ' ' + vName);

    var confCols = { CONFIRMED:'#10b981', PROBABLE:'#f59e0b', POSSIBLE:'#94a3b8', INCONCLUSIVE:'#64748b' };
    var col = confCols[confLevel] || '#94a3b8';

    // Build scorecard HTML using string concatenation (no nested template literals)
    var _scoreRow = function(s) {
        var fc = s.fired ? '#10b981' : '#ef4444';
        var ic = s.fired ? '\u2713' : '\u2717';
        var nameHtml = s.fired
            ? '<span style="font-size:9.5px;color:#cbd5e1">' + esc(s.name) + '</span>'
            : '<span style="font-size:9.5px;color:#475569">' + esc(s.name)
              + ' <span style="font-size:8px;color:#334155;font-style:italic">\u2014 ' + esc(s.absentMeans) + '</span></span>';
        return '<div style="display:grid;grid-template-columns:14px 1fr 60px 70px;gap:6px;align-items:center;padding:3px 0;border-bottom:1px solid rgba(15,23,42,0.5)">'
            + '<span style="color:' + fc + ';font-weight:900;font-size:10px;text-align:center">' + ic + '</span>'
            + nameHtml
            + '<span style="font-size:8.5px;color:' + (s.fired ? col : '#334155') + ';text-align:right;font-weight:700">' + esc(s.value) + '</span>'
            + '<span style="font-size:7.5px;color:#334155;text-align:right">' + esc(s.panel) + '</span>'
            + '</div>';
    };

    var barFilled = '';
    for (var i=0; i<n; i++) barFilled += '<span style="display:inline-block;width:16px;height:8px;background:'+col+';border-radius:2px;box-shadow:0 0 4px '+col+'60"></span>';
    var barEmpty = '';
    for (var j=n; j<m; j++) barEmpty += '<span style="display:inline-block;width:16px;height:8px;background:rgba(71,85,105,0.3);border-radius:2px"></span>';

    var rowsHtml = sigs.map(_scoreRow).join('');
    var scorecardHtml =
        '<div style="margin-bottom:10px;padding:8px 12px;background:rgba(15,23,42,0.6);border:1px solid '+col+'30;border-radius:6px">'
        + '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px">'
        + '<span style="font-size:11px;font-weight:900;color:'+col+';letter-spacing:1px;text-transform:uppercase;text-shadow:0 0 10px '+col+'60">'
        + esc(label) + '</span>'
        + '<div style="display:flex;gap:2px;align-items:center;margin-left:auto">' + barFilled + barEmpty + '</div>'
        + '<span style="font-size:10px;font-weight:900;color:'+col+';white-space:nowrap">' + n + '\u00a0/\u00a0' + m + ' signals</span>'
        + '</div>'
        + '<details style="margin:0"><summary style="font-size:8.5px;color:#64748b;cursor:pointer;list-style:none;font-weight:700;text-transform:uppercase;letter-spacing:0.4px">'
        + 'Show all ' + m + ' signals checked \u25be</summary>'
        + '<div style="margin-top:6px">' + rowsHtml + '</div>'
        + '</details>'
        + '</div>';

    return { n: n, m: m, sigs: sigs, confLevel: confLevel, label: label, col: col, scorecardHtml: scorecardHtml };
}

// =============================================================================
// VERDICT FALSIFICATION CHECKLIST
// Rule 4: Each item names: what to check, what value would falsify it,
//         and what alternative verdict applies instead.
// =============================================================================
function _buildFalsificationBlock(finalPv, ctx, domSqlId) {
    var SQL_VERDICTS = ['DOMINANT_SQL','NEW_SQL','PLAN_CHANGE','SQL_REGRESSION','SQL_DOMINANT'];
    var _esc = function(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };
    var sid = domSqlId || '[sql_id]';

    var ITEMS = {
        CPU_SATURATION: [
            { what:'AAS vs CPU count across AWR snapshots',
              check:'SELECT metric_name, ROUND(average,2) avg_val, ROUND(maximum,2) max_val FROM dba_hist_sysmetric_summary WHERE metric_name=\'Average Active Sessions\' AND snap_id BETWEEN [s1] AND [s2]',
              falsifies:'If AAS < CPU count throughout the problem window, CPU saturation is falsified. Seek wait event or SQL root cause instead.',
              alt:'IO_BOTTLENECK or SQL_DOMINANT' },
            { what:'Is DB CPU from real work or parse overhead?',
              check:'SELECT stat_name, value FROM dba_hist_sysstat WHERE stat_name IN (\'parse count (hard)\',\'CPU used by this session\',\'recursive cpu usage\') AND snap_id BETWEEN [s1] AND [s2]',
              falsifies:'If hard_parse_rate < 50/s, parse overhead is not inflating DB CPU. The CPU burn is from application SQL logical I/O volume.',
              alt:'SQL logical I/O is the real CPU consumer' },
            { what:'DBRM throttle masking organic saturation',
              check:'SELECT consumer_group, cpu_quantum_milliseconds, active_sess_pool_P1, parallel_degree_limit_p1 FROM dba_rsrc_plan_directives WHERE plan IN (SELECT name FROM v$rsrc_plan WHERE is_top_plan=\'TRUE\')',
              falsifies:'If resmgr:cpu quantum > 5% DB Time, part of saturation is policy-enforced. Removing DBRM limits may NOT reveal a clean CPU ceiling.',
              alt:'Resource Manager policy change, not workload increase' }
        ],
        IO_BOTTLENECK: [
            { what:'Buffer cache hit ratio throughout problem window',
              check:'SELECT metric_name, ROUND(average,2) avg_pct, ROUND(minimum,2) min_pct FROM dba_hist_sysmetric_summary WHERE metric_name=\'Buffer Cache Hit Ratio\' AND snap_id BETWEEN [s1] AND [s2]',
              falsifies:'If BCHR > 98% throughout the window, physical I/O volume is not the binding constraint. Seek CPU or concurrency cause instead.',
              alt:'CPU_SATURATION if BCHR consistently > 98%' },
            { what:'Are physical reads expected for this SQL access path?',
              check:'SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR(\'' + _esc(sid) + '\',NULL,NULL,\'ALL\'))',
              falsifies:'If the SQL uses a selective index with a low clustering factor, the physical reads are proportional and expected. Not an anomaly to fix.',
              alt:'SQL_DOMINANT with expected physical read pattern' },
            { what:'Direct path vs scattered read ratio',
              check:'SELECT event, total_waits, ROUND(time_waited_micro/1e6,1) total_secs FROM dba_hist_system_event WHERE event IN (\'db file sequential read\',\'db file scattered read\',\'direct path read\') AND snap_id BETWEEN [s1] AND [s2]',
              falsifies:'If direct path read dominates, the I/O is from parallel query or smart scan — not a missing index. Infrastructure sizing or DOP problem.',
              alt:'Parallel query CPU inflation or temp spill to disk' }
        ],
        COMMIT_LOGGING: [
            { what:'Redo log file storage speed and placement',
              check:'SELECT member, type FROM v$logfile ORDER BY type, member',
              falsifies:'If redo logs are already on SSD with < 2ms write latency AND log file sync avg wait is still high, the problem is commit frequency — the storage fix alone is insufficient.',
              alt:'Confirm avg_wait > 20ms on dedicated SSD = storage bottleneck' },
            { what:'Loop-commit anti-pattern in DML statements',
              check:'SELECT sql_id, executions, rows_processed, ROUND(rows_processed/NULLIF(executions,0),0) rows_per_exec FROM v$sql WHERE command_type IN (2,6,7) AND executions > 1000 ORDER BY executions DESC FETCH FIRST 10 ROWS ONLY',
              falsifies:'If rows_per_exec > 100 for top DML, bulk DML is already batched. Commit frequency is NOT from a loop-commit pattern.',
              alt:'Distributed transaction or application-level commit storm' },
            { what:'Log file switch sub-bottleneck',
              check:'SELECT event, total_waits, ROUND(time_waited_micro/1e6,1) secs FROM dba_hist_system_event WHERE event LIKE \'log file switch%\' AND snap_id BETWEEN [s1] AND [s2]',
              falsifies:'If log file switch (checkpoint incomplete) or (archiving needed) > 0 waits alongside log file sync, there are TWO separate root causes — redo infrastructure is also failing.',
              alt:'REDO_INFRASTRUCTURE: fix log sizes and DBWR concurrently with commit batching' }
        ],
        CONCURRENCY: [
            { what:'Latch miss ratio in Latch Activity section',
              check:'SELECT latch_name, gets, misses, ROUND(misses/NULLIF(gets,0)*100,3) miss_pct FROM v$latch WHERE latch_name IN (\'cache buffers chains\',\'library cache\',\'shared pool\') ORDER BY miss_pct DESC',
              falsifies:'If miss_pct < 0.1% for all latches despite high wait DB Time%, the contention is incidental — caused by CPU saturation forcing more latch cycles, not independent contention.',
              alt:'CPU_SATURATION driving incidental latch overhead' },
            { what:'Hot block identification from buffer pool',
              check:'SELECT o.object_name, o.object_type, COUNT(*) pin_count FROM v$bh b JOIN dba_objects o ON o.object_id=b.obj GROUP BY o.object_name, o.object_type ORDER BY pin_count DESC FETCH FIRST 10 ROWS ONLY',
              falsifies:'If no single block has pin_count > 10x average, contention is diffuse — general hard-parse storm rather than a hot-block pattern.',
              alt:'Hard parse storm if no single hot block identified' },
            { what:'Cursor version count explosion',
              check:'SELECT sql_id, version_count, SUBSTR(sql_text,1,60) txt FROM v$sqlarea WHERE version_count > 10 ORDER BY version_count DESC FETCH FIRST 10 ROWS ONLY',
              falsifies:'If no SQL has version_count > 20 AND hard parse rate < 100/s, cursor pin S waits are from concurrent DDL invalidation, not a persistent application parse pattern.',
              alt:'Concurrent DDL invalidating hot cursors during peak load' }
        ]
    };

    var SQL_ITEMS = [
        { what:'Plan hash stability across problem window',
          check:'SELECT plan_hash_value, TO_CHAR(last_active_time,\'YYYY-MM-DD HH24\') hr, COUNT(*) execs FROM v$sql WHERE sql_id=\'' + _esc(sid) + '\' GROUP BY plan_hash_value, TO_CHAR(last_active_time,\'YYYY-MM-DD HH24\') ORDER BY hr',
          falsifies:'If plan hash is stable and per-exec elapsed is unchanged vs baseline, the issue is pure execution frequency increase — reduce call count, not change the plan.',
          alt:'Workload frequency increase rather than plan regression' },
        { what:'Actual rows vs estimated rows (cardinality accuracy)',
          check:'SELECT id, operation, cardinality estimated, last_output_rows actual, ROUND(last_output_rows/NULLIF(cardinality,0),1) ratio FROM v$sql_plan_statistics_all WHERE sql_id=\'' + _esc(sid) + '\' ORDER BY id',
          falsifies:'If all cardinality_ratio values are between 0.5 and 2.0, the optimizer has accurate statistics. The plan is correctly chosen — data volume or frequency is the driver, not optimizer error.',
          alt:'Data volume growth with correct execution plan' },
        { what:'Module / action source of executions',
          check:'SELECT module, action, COUNT(*) cnt FROM dba_hist_active_sess_history WHERE sql_id=\'' + _esc(sid) + '\' AND snap_id BETWEEN [s1] AND [s2] GROUP BY module, action ORDER BY cnt DESC',
          falsifies:'If multiple distinct modules drive this SQL at equal rates, it is a shared infrastructure SQL. Fixing the plan affects ALL callers and requires cross-team coordination.',
          alt:'Shared utility SQL pattern' }
    ];

    var key   = SQL_VERDICTS.indexOf(finalPv) >= 0 ? 'SQL_VERDICT' : finalPv;
    var items = SQL_VERDICTS.indexOf(finalPv) >= 0 ? SQL_ITEMS : (ITEMS[key] || ITEMS.CPU_SATURATION);

    if (!items.length) return '';

    var _fi = function(item) {
        return '<div style="margin-bottom:8px;padding:8px 12px;background:rgba(15,23,42,0.5);border:1px solid rgba(100,116,139,0.12);border-radius:5px">'
            + '<div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:3px">Check: '
            + _esc(item.what) + '</div>'
            + '<div style="font-size:8.5px;color:#334155;background:rgba(0,0,0,0.25);padding:4px 7px;border-radius:3px;margin-bottom:4px;font-family:monospace;white-space:pre-wrap;word-break:break-all">'
            + _esc(item.check) + '</div>'
            + '<div style="font-size:9.5px;color:#94a3b8;line-height:1.5">'
            + '<strong style="color:#ef4444;font-size:8px">Falsifies if: </strong>' + _esc(item.falsifies) + '</div>'
            + '<div style="font-size:8.5px;color:#475569;margin-top:2px">'
            + '<strong style="color:#64748b;font-size:8px">Alt verdict: </strong>' + _esc(item.alt) + '</div>'
            + '</div>';
    };

    return '<div style="margin:0 0 18px;padding:14px 16px;background:rgba(100,116,139,0.05);border:1px solid rgba(100,116,139,0.18);border-left:4px solid #475569;border-radius:0 9px 9px 0">'
        + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
        + '<span style="font-size:10px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:1.5px">Falsification Checklist</span>'
        + '<span style="font-size:8px;color:#334155;font-weight:600">what would disprove this diagnosis \u2014 verify before acting</span>'
        + '</div>'
        + items.map(_fi).join('')
        + '</div>';
}

"""

# Find insertion point — right before "function generateComparisonVerdictNarrative"
MARKER = 'function generateComparisonVerdictNarrative(ctx, wkPatterns, sreConn) {'
assert src.count(MARKER) == 1, f"Expected 1 match for MARKER, got {src.count(MARKER)}"
idx = src.index(MARKER)
src = src[:idx] + NEW_FUNCTIONS + src[idx:]

# ── PATCH 2: Wire _buildVerdictSignalScore call after isSqlVerdict declaration ──

OLD_ISVERDDICT = "    const isSqlVerdict = ['DOMINANT_SQL','NEW_SQL','PLAN_CHANGE','SQL_REGRESSION','SQL_DOMINANT'].includes(_finalPv);"
NEW_ISVERDDICT = OLD_ISVERDDICT + """

    // ── SIGNAL SCORECARD — computed from ctx + finalPv before assembly ────────
    // Rule 1: label = [CONFIDENCE] [VERDICT_NAME]
    // Rule 6: N of M signals, all M shown in expandable scorecard
    const _verdictScore = _buildVerdictSignalScore(ctx, _finalPv);"""

assert src.count(OLD_ISVERDDICT) == 1, f"PATCH 2 target not found ({src.count(OLD_ISVERDDICT)})"
src = src.replace(OLD_ISVERDDICT, NEW_ISVERDDICT, 1)

# ── PATCH 3: Replace the signal-chip IIFE in whatBlock with scorecard HTML ──

OLD_CHIP = r"""        ${(()=>{
            // Verdict signal trail — show exactly WHICH signals fired this diagnosis
            const _signals = [];
            if (topWait && (topWait.pct_db_time||0) > 2) _signals.push({label: esc(topWaitName), val: f1(topWait.pct_db_time||0)+'% DB Time', col:'#f87171'});
            if (domSqlShare > 15) _signals.push({label: 'SQL '+esc(domSqlId), val: f1(domSqlShare)+'% DB Time', col:'#fbbf24'});
            if ((lp2.hard_parses||0) > 500) _signals.push({label: 'Hard parses', val: comma(lp2.hard_parses||0)+'/s', col:'#c084fc'});
            if ((cursorPinXEv?.pct_db_time||0) > 3) _signals.push({label: 'cursor: pin S wait on X', val: f1(cursorPinXEv.pct_db_time||0)+'%', col:'#f59e0b'});
            if ((latchCBCEv?.pct_db_time||0) > 3) _signals.push({label: 'latch: CBC', val: f1(latchCBCEv.pct_db_time||0)+'%', col:'#f59e0b'});
            // Confidence: HIGH = 3+ signals, MEDIUM = 2, LOW = 1
            const _conf = _signals.length >= 3 ? {label:'HIGH',col:'#22c55e'} : _signals.length === 2 ? {label:'MEDIUM',col:'#fbbf24'} : {label:'LOW',col:'#94a3b8'};
            // Boost confidence if advisory, latch activity, or tablespace IO corroborates
            const _hasAdvisory = (_bufAdvReadPct > 15) || (_spAdvBest != null);
            const _hasLatch    = _cbcMissPct > 0.5 || _lcMissPct > 0.5;
            const _hasTs       = !!_slowestTs;
            const _corrobCount = _signals.length + (_hasAdvisory?1:0) + (_hasLatch?1:0) + (_hasTs?1:0);
            const _finalConf   = _corrobCount >= 3 ? {label:'HIGH',col:'#22c55e'} : _corrobCount === 2 ? {label:'MEDIUM',col:'#fbbf24'} : {label:'LOW',col:'#94a3b8'};
            const _pvCol = {CONCURRENCY:'#f59e0b',IO_BOTTLENECK:'#14b8a6',CPU_SATURATION:'#ef4444',COMMIT_LOGGING:'#3b82f6',PLAN_REGRESSION:'#f87171',BUFFER_WRITE_PRESSURE:'#a78bfa',GENERIC_SQL:'#94a3b8',NEW_WORKLOAD:'#22c55e',LATCH_CONTENTION:'#f97316'};
            if (!_signals.length) return '';
            return `<div style="margin-bottom:10px;padding:7px 10px;background:rgba(15,23,42,0.6);border:1px solid rgba(56,189,248,0.15);border-radius:6px;display:flex;flex-wrap:wrap;align-items:center;gap:6px">
                <span style="font-size:9px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-right:2px">Signals that triggered <span style="color:${_pvCol[_pv]||'#94a3b8'}">${(_pv||'').replace(/_/g,' ')}</span> diagnosis:</span>
                ${_signals.map(s=>`<span style="font-size:9px;font-weight:700;padding:2px 7px;border-radius:3px;background:${s.col}18;color:${s.col};border:1px solid ${s.col}40">${s.label}: ${s.val}</span>`).join('')}
                <span style="margin-left:auto;font-size:9px;font-weight:800;padding:2px 8px;border-radius:3px;background:${_finalConf.col}15;color:${_finalConf.col};border:1px solid ${_finalConf.col}40;text-transform:uppercase;letter-spacing:0.5px">${_finalConf.label} confidence</span>
            </div>`;
        })()}"""

NEW_CHIP = '        ${_verdictScore.scorecardHtml}'

assert src.count(OLD_CHIP) == 1, f"PATCH 3 old chip not found ({src.count(OLD_CHIP)})"
src = src.replace(OLD_CHIP, NEW_CHIP, 1)

# ── PATCH 4: Add falsificationBlock computation after howBlock assignment ──

OLD_AFTER_HOW = """    // ── CORROBORATING SIGNALS TABLE (compact) ─────────────────────────────────
    const corrTitle = _sigCount > 0"""

NEW_AFTER_HOW = """    // ── FALSIFICATION CHECKLIST (Rule 4) ─────────────────────────────────────
    const falsificationBlock = _buildFalsificationBlock(_finalPv, ctx, domSqlId);

    // ── CORROBORATING SIGNALS TABLE (compact) ─────────────────────────────────
    const corrTitle = _sigCount > 0"""

assert src.count(OLD_AFTER_HOW) == 1, f"PATCH 4 target not found ({src.count(OLD_AFTER_HOW)})"
src = src.replace(OLD_AFTER_HOW, NEW_AFTER_HOW, 1)

# ── PATCH 5: Update verdict label in confidenceBlock to [CONF] [VERDICT_NAME] ──

OLD_CONF_LABEL = "                <div style=\"font-size:15px;font-weight:900;color:${_cc.color};letter-spacing:1.2px;text-transform:uppercase;animation:verdict-flash 2.8s ease-in-out infinite;text-shadow:0 0 14px ${_cc.color}99\">${_cc.label}</div>"
NEW_CONF_LABEL = "                <div style=\"font-size:15px;font-weight:900;color:${_verdictScore.col};letter-spacing:1.2px;text-transform:uppercase;animation:verdict-flash 2.8s ease-in-out infinite;text-shadow:0 0 14px ${_verdictScore.col}99\">${_verdictScore.label}</div>"

assert src.count(OLD_CONF_LABEL) == 1, f"PATCH 5 target not found ({src.count(OLD_CONF_LABEL)})"
src = src.replace(OLD_CONF_LABEL, NEW_CONF_LABEL, 1)

# ── PATCH 6: Add ${falsificationBlock} to the final template return ──

OLD_RETURN_PART = "        ${howBlock}\n        ${_notYetHtml}"
NEW_RETURN_PART = "        ${howBlock}\n        ${falsificationBlock}\n        ${_notYetHtml}"

assert src.count(OLD_RETURN_PART) == 1, f"PATCH 6 target not found ({src.count(OLD_RETURN_PART)})"
src = src.replace(OLD_RETURN_PART, NEW_RETURN_PART, 1)

# ── Write the patched file ──
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print(f"Done. File length: {len(src)} chars")

# ── Post-edit syntax validation ──
import re
orphaned  = len(re.findall(r'`\s*;\s*\$\{', src))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', src))
scoreCard = len(re.findall(r'_verdictScore\.scorecardHtml', src))
falseBlock= len(re.findall(r'falsificationBlock', src))
confLabel = len(re.findall(r'_verdictScore\.label', src))
print(f"Syntax: orphaned={orphaned} brokenTag={brokenTag} (both must be 0)")
print(f"New symbols: scorecardHtml={scoreCard} falsification={falseBlock} label={confLabel}")
