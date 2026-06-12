/**
 * PEEngine Exam Runner — Extracts code from index.html and runs 27 test scenarios via Node.js
 * Usage: node _pe_exam_runner.js
 */
const fs = require('fs');
const path = require('path');

// ── Step 1: Extract PEEngine + buildAWRContext from index.html ────────────
const templatePath = path.join(__dirname, 'backend', 'templates', 'index.html');
const lines = fs.readFileSync(templatePath, 'utf-8').split('\n');

// PEEngine IIFE: lines 8550-9198 (0-indexed: 8549-9197)
const peCode = lines.slice(8549, 9198).join('\n');

// buildAWRContext: lines 1948-2194 (0-indexed: 1947-2193)
const buildCode = lines.slice(1947, 2194).join('\n');

// ── Step 2: Set up a minimal browser-like global scope ────────────────────
const window = {};
global.window = window;

// Execute buildAWRContext (it's a function declaration — needs no window)
const buildFn = new Function(buildCode + '\nreturn buildAWRContext;')();

// Execute PEEngine IIFE
new Function('window', peCode)(window);

const PEEngine = window.PEEngine;
if (!PEEngine) { console.error('FATAL: PEEngine not initialised'); process.exit(1); }
if (!buildFn) { console.error('FATAL: buildAWRContext not initialised'); process.exit(1); }

console.log('✓ PEEngine extracted (' + PEEngine.RULES.length + ' rules)');
console.log('✓ buildAWRContext extracted\n');

// ── Step 3: Helpers ───────────────────────────────────────────────────────
function makeWaitEvent(name, waitClass, pctDbTime, totalWaits, avgWaitMs) {
    return {
        event_name: name, wait_class: waitClass, pct_db_time: pctDbTime,
        total_waits: totalWaits || 10000,
        time_waited_secs: (totalWaits || 10000) * (avgWaitMs || 1) / 1000,
        avg_wait_ms: avgWaitMs || 1
    };
}
function makeLP(statName, perSec) {
    return { stat_name: statName, per_sec: perSec, per_second: perSec };
}
function makeSql(sqlId, pctDbTime, opts = {}) {
    return {
        sql_id: sqlId, plan_hash_value: opts.planHash || 123456,
        elapsed_time_secs: opts.elapsed || 100, executions: opts.execs || 1000,
        buffer_gets: opts.bufGets || 500000, disk_reads: opts.diskReads || 10000,
        cpu_time_secs: opts.cpuTime || 50, pct_db_time: pctDbTime,
        sql_text: opts.sqlText || 'SELECT * FROM DUAL',
        tables_referenced: opts.tables || [], table_name: opts.tableName || '',
        _isNew: !!opts._isNew, _isPlanChg: !!opts._isPlanChg, _isRegressed: !!opts._isRegressed
    };
}

function defaultLP(dbTimeMin, elapsedMin, cpuFraction) {
    const dbTimePerSec = dbTimeMin * 60 / elapsedMin / 60;
    return [
        makeLP('DB Time(s/s)',   dbTimePerSec),
        makeLP('DB CPU(s/s)',    dbTimePerSec * (cpuFraction || 0.4)),
        makeLP('Redo size',     5000000), makeLP('Logical reads', 100000),
        makeLP('Block changes', 5000), makeLP('Physical reads',10000),
        makeLP('Physical writes',2000), makeLP('User calls',    500),
        makeLP('Parses',        200), makeLP('Hard parses',   5),
        makeLP('Sorts',         100), makeLP('Logons',        2),
        makeLP('Executes',      3000), makeLP('Transactions',  100),
        makeLP('User Commits',  100), makeLP('User Rollbacks',1),
    ];
}

function buildScenario(name, c) {
    c = Object.assign({ cpus: 8, elapsedMin1: 60, elapsedMin2: 60, dbTimeMin1: 30, dbTimeMin2: 60,
        lp1: [], lp2: [], waits1: [], waits2: [], eff1: {}, eff2: {}, sql1: [], sql2: [], sqlAttrib: [] }, c);

    const lp1 = c.lp1.length ? c.lp1 : defaultLP(c.dbTimeMin1, c.elapsedMin1);
    const lp2 = c.lp2.length ? c.lp2 : defaultLP(c.dbTimeMin2, c.elapsedMin2);
    const defEff = { buffer_cache_hit_pct:99.5, library_cache_hit_pct:99.8, soft_parse_pct:99, execute_to_parse_pct:85, latch_hit_pct:99.9, parse_cpu_pct:5, non_parse_cpu_pct:95, in_memory_sort_pct:99, shared_pool_memory_usage_pct:75 };
    const eff1 = Object.assign({}, defEff, c.eff1);
    const eff2 = Object.assign({}, defEff, c.eff2);

    const data = {
        good_data: {
            elapsed_min: c.elapsedMin1, db_time_min: c.dbTimeMin1, cpus: c.cpus,
            load_profile: lp1, efficiency: eff1,
            wait_events: c.waits1.length ? c.waits1 : [
                makeWaitEvent('DB CPU','CPU',60), makeWaitEvent('db file sequential read','User I/O',20,50000,5),
                makeWaitEvent('log file sync','Commit',5,10000,1)
            ],
            time_model: [], sql_stats: c.sql1, segments: [], addm_findings: []
        },
        bad_data: {
            elapsed_min: c.elapsedMin2, db_time_min: c.dbTimeMin2, cpus: c.cpus,
            load_profile: lp2, efficiency: eff2,
            wait_events: c.waits2, time_model: [], sql_stats: c.sql2, segments: [], addm_findings: []
        },
        comparison_rca: {
            db_summary_1: { elapsed_min: c.elapsedMin1, db_time_secs: c.dbTimeMin1*60, cpus: c.cpus },
            db_summary_2: { elapsed_min: c.elapsedMin2, db_time_secs: c.dbTimeMin2*60, cpus: c.cpus }
        },
        health_good: {}, health_bad: {}
    };

    if (c.sqlAttrib.length === 0 && c.sql2.length > 0) {
        const top = c.sql2[0];
        c.sqlAttrib = [{ id:top.sql_id, sql_id:top.sql_id, pctDb:top.pct_db_time, pct_db_time:top.pct_db_time,
            epe1:0, epe2:top.elapsed_time_secs/Math.max(top.executions,1),
            isNew:!!top._isNew, is_new:!!top._isNew, isPlanChg:!!top._isPlanChg, is_plan_change:!!top._isPlanChg,
            isRegressed:!!top._isRegressed, is_regressed:!!top._isRegressed }];
    }
    return { name, data, sqlAttrib: c.sqlAttrib, _config: c };
}

// ── Step 4: Define all 27 scenarios ───────────────────────────────────────

const SCENARIOS = [];

// S01: Healthy
SCENARIOS.push(buildScenario('S01: Healthy DB — No Degradation', {
    cpus:16, dbTimeMin1:30, dbTimeMin2:32,
    waits2:[makeWaitEvent('DB CPU','CPU',55),makeWaitEvent('db file sequential read','User I/O',22,50000,4),makeWaitEvent('log file sync','Commit',5,10000,0.8)],
    sql2:[makeSql('abc123def',8,{sqlText:'SELECT id FROM orders WHERE status=:1'})],
    _expect:{ topRule:null, pTier:'P3', sessionRisk:'STABLE', dbTimeDelta_range:[-10,15] }
}));

// S02: Plan Regression
SCENARIOS.push(buildScenario('S02: Plan Regression', {
    cpus:8, dbTimeMin1:20, dbTimeMin2:90,
    waits2:[makeWaitEvent('DB CPU','CPU',25),makeWaitEvent('db file sequential read','User I/O',45,500000,12),makeWaitEvent('db file scattered read','User I/O',15,100000,15),makeWaitEvent('log file sync','Commit',3,5000,1)],
    sql2:[makeSql('plan_flip01',55,{planHash:999888,elapsed:400,execs:500,bufGets:5000000,diskReads:800000,sqlText:'SELECT * FROM big_table WHERE created_date > :1',tableName:'BIG_TABLE',_isPlanChg:true,_isRegressed:true})],
    sql1:[makeSql('plan_flip01',10,{planHash:111222,elapsed:20,execs:500,bufGets:50000,diskReads:1000,sqlText:'SELECT * FROM big_table WHERE created_date > :1'})],
    sqlAttrib:[{id:'plan_flip01',sql_id:'plan_flip01',pctDb:55,pct_db_time:55,epe1:0.04,epe2:0.8,isNew:false,is_new:false,isPlanChg:true,is_plan_change:true,isRegressed:true,is_regressed:true}],
    _expect:{ topRule:'PLAN_REGRESSION', pTier:'P1', dbTimeReduction_range:[40,55], rationale_must_contain:['plan','plan_flip01'] }
}));

// S03: New SQL Deploy
SCENARIOS.push(buildScenario('S03: New SQL Deploy', {
    cpus:8, dbTimeMin1:25, dbTimeMin2:80,
    waits2:[makeWaitEvent('DB CPU','CPU',40),makeWaitEvent('db file sequential read','User I/O',30,200000,10),makeWaitEvent('log file sync','Commit',5,8000,2)],
    sql2:[makeSql('new_sql_001',40,{elapsed:300,execs:200,bufGets:3000000,diskReads:400000,sqlText:'SELECT /*+ NEW_REPORT */ a.* FROM customer_data a, order_hist b WHERE a.cust_id = b.cust_id',tableName:'CUSTOMER_DATA',_isNew:true})],
    sqlAttrib:[{id:'new_sql_001',sql_id:'new_sql_001',pctDb:40,pct_db_time:40,epe1:0,epe2:1.5,isNew:true,is_new:true,isPlanChg:false,is_plan_change:false}],
    _expect:{ topRule:'NEW_SQL_DEPLOY', pTier:'P1', dbTimeReduction_range:[25,35], rationale_must_contain:['new_sql_001','deploy'] }
}));

// S04: HW Enqueue — Extreme
SCENARIOS.push(buildScenario('S04: HW Enqueue — Extreme', {
    cpus:16, dbTimeMin1:40, dbTimeMin2:200,
    waits2:[makeWaitEvent('enq: HW - contention','Configuration',72,500000,25),makeWaitEvent('DB CPU','CPU',8),makeWaitEvent('buffer busy waits','Concurrency',8,100000,5),makeWaitEvent('log file sync','Commit',5,30000,3),makeWaitEvent('free buffer waits','Configuration',3,10000,10)],
    sql2:[makeSql('hw_insert01',35,{elapsed:500,execs:100000,sqlText:'INSERT INTO audit_log VALUES (:1,:2,:3,:4)',tableName:'AUDIT_LOG'})],
    _expect:{ topRule:'HW_ENQUEUE_CONTENTION', pTier:'P1', dbTimeReduction_range:[60,70], sessionsFreed_lte_aasB:true, rationale_must_contain:['HW','high-water','AUDIT_LOG'] }
}));

// S05: TX Row Lock
SCENARIOS.push(buildScenario('S05: TX Row Lock', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:65,
    waits2:[makeWaitEvent('enq: TX - row lock contention','Application',28,80000,50),makeWaitEvent('DB CPU','CPU',35),makeWaitEvent('db file sequential read','User I/O',15,30000,5),makeWaitEvent('log file sync','Commit',8,15000,2),makeWaitEvent('enq: TX - index contention','Concurrency',3,5000,8)],
    sql2:[makeSql('upd_acct01',20,{sqlText:'UPDATE accounts SET balance = balance - :1 WHERE account_id = :2',tableName:'ACCOUNTS'})],
    _expect:{ topRule:'TX_ROW_LOCK_CONTENTION', pTier:'P2', dbTimeReduction_range:[15,22], rationale_must_contain:['row lock','28.0'] }
}));

// S06: TX Mixed — txRowPct vs txEnqPct (Bug #2 regression test)
SCENARIOS.push(buildScenario('S06: TX Mixed — Bug2 regression', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:55,
    waits2:[makeWaitEvent('enq: TX - row lock contention','Application',15,40000,30),makeWaitEvent('enq: TX - index contention','Concurrency',18,30000,20),makeWaitEvent('enq: TX - allocate ITL entry','Configuration',7,10000,15),makeWaitEvent('DB CPU','CPU',30),makeWaitEvent('db file sequential read','User I/O',12,20000,5)],
    sql2:[makeSql('mixed_tx01',18,{sqlText:'UPDATE hot_table SET val=:1 WHERE id=:2'})],
    _expect:{ topRule:'TX_INDEX_CONTENTION',
        _custom:(ev,evaln)=>{
            const r=evaln.matches.find(m=>m.rule.id==='TX_ROW_LOCK_CONTENTION');
            if(!r)return{pass:true,note:'TX_ROW_LOCK did not fire'};
            const p=r.rule.project(ev);
            if(p.dbTimeReductionPct>15*0.7+1)return{pass:false,note:`BUG2: TX_ROW projects ${p.dbTimeReductionPct.toFixed(1)}% — using txEnqPct not txRowPct`};
            return{pass:true,note:`TX_ROW correctly uses txRowPct: ${p.dbTimeReductionPct.toFixed(1)}%`};
        }
    }
}));

// S07: Concurrent DML — Insert storm
SCENARIOS.push(buildScenario('S07: Concurrent DML', {
    cpus:8, dbTimeMin1:25, dbTimeMin2:120,
    lp2:[makeLP('DB Time(s/s)',2),makeLP('DB CPU(s/s)',0.3),makeLP('Redo size',50000000),makeLP('Logical reads',500000),makeLP('Block changes',80000),makeLP('Physical reads',20000),makeLP('Physical writes',60000),makeLP('User calls',1000),makeLP('Parses',300),makeLP('Hard parses',5),makeLP('Sorts',50),makeLP('Logons',3),makeLP('Executes',5000),makeLP('Transactions',500),makeLP('User Commits',500),makeLP('User Rollbacks',1)],
    waits2:[makeWaitEvent('free buffer waits','Configuration',35,200000,30),makeWaitEvent('buffer busy waits','Concurrency',18,100000,10),makeWaitEvent('enq: FB - contention','Other',8,20000,15),makeWaitEvent('log file sync','Commit',15,50000,5),makeWaitEvent('DB CPU','CPU',10),makeWaitEvent('db file parallel write','System I/O',6,30000,8)],
    sql2:[makeSql('mass_insert01',32,{sqlText:'INSERT INTO transaction_log (id,ts,amt,acct) VALUES (:1,SYSDATE,:2,:3)',tableName:'TRANSACTION_LOG',execs:200000})],
    _expect:{ topRule:'CONCURRENT_DML_BOTTLENECK', pTier:'P1', dbTimeReduction_range:[38,48],
        rationale_must_contain:['INSERT','mass_insert01','TRANSACTION_LOG'],
        _custom:(ev,evaln)=>{
            if(evaln.projection.dbTimeReductionPct>50)return{pass:false,note:`Reclaim inflation: ${evaln.projection.dbTimeReductionPct.toFixed(1)}%>50%`};
            return{pass:true,note:`Reclaim ${evaln.projection.dbTimeReductionPct.toFixed(1)}% within bounds`};
        }
    }
}));

// S08: Buffer Cache Write Pressure
SCENARIOS.push(buildScenario('S08: Buffer Cache Pressure', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:70,
    waits2:[makeWaitEvent('free buffer waits','Configuration',25,150000,20),makeWaitEvent('buffer busy waits','Concurrency',12,60000,8),makeWaitEvent('enq: FB - contention','Other',5,10000,12),makeWaitEvent('DB CPU','CPU',28),makeWaitEvent('db file sequential read','User I/O',15,40000,6),makeWaitEvent('log file sync','Commit',8,20000,3)],
    sql2:[makeSql('select_rpt01',15,{sqlText:'SELECT count(*) FROM orders WHERE order_date > :1'})],
    _expect:{ topRule:'BUFFER_CACHE_WRITE_PRESSURE', pTier:'P2', dbTimeReduction_range:[22,30], rationale_must_contain:['DBWR','free buffer waits'] }
}));

// S09: CPU Saturation
SCENARIOS.push(buildScenario('S09: CPU Saturation', {
    cpus:4, dbTimeMin1:15, dbTimeMin2:50,
    lp2:[makeLP('DB Time(s/s)',50),makeLP('DB CPU(s/s)',3.8),makeLP('Redo size',2000000),makeLP('Logical reads',800000),makeLP('Block changes',2000),makeLP('Physical reads',5000),makeLP('Physical writes',1000),makeLP('User calls',2000),makeLP('Parses',100),makeLP('Hard parses',3),makeLP('Sorts',200),makeLP('Logons',5),makeLP('Executes',8000),makeLP('Transactions',50),makeLP('User Commits',50),makeLP('User Rollbacks',0)],
    waits2:[makeWaitEvent('DB CPU','CPU',72),makeWaitEvent('db file sequential read','User I/O',12,20000,4),makeWaitEvent('latch: cache buffers chains','Concurrency',5,50000,0.5),makeWaitEvent('log file sync','Commit',4,5000,1)],
    sql2:[makeSql('cpu_hog01',22,{sqlText:'SELECT /*+ FULL(t) */ * FROM big_fact t WHERE UPPER(description) LIKE :1',bufGets:10000000})],
    _expect:{ topRule:'CPU_SATURATION', pTier:'P1', sessionRisk:/SATURATED|CPU-BOUND/, rationale_must_contain:['CPU','utilisation'] }
}));

// S10: I/O Pressure
SCENARIOS.push(buildScenario('S10: I/O Pressure', {
    cpus:8, dbTimeMin1:20, dbTimeMin2:55,
    waits2:[makeWaitEvent('db file sequential read','User I/O',38,300000,25),makeWaitEvent('db file scattered read','User I/O',12,50000,30),makeWaitEvent('DB CPU','CPU',22),makeWaitEvent('direct path read','User I/O',8,20000,15),makeWaitEvent('log file sync','Commit',5,8000,2)],
    sql2:[makeSql('io_query01',18,{sqlText:'SELECT * FROM customer_master WHERE region_code = :1',diskReads:500000})],
    _expect:{ topRule:'IO_PRESSURE', pTier:'P2', dbTimeReduction_range:[28,36], rationale_must_contain:['I/O'] }
}));

// S11: Redo/Commit Storm
SCENARIOS.push(buildScenario('S11: Redo Commit Storm', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:60,
    lp2:[makeLP('DB Time(s/s)',60),makeLP('DB CPU(s/s)',1.5),makeLP('Redo size',80000000),makeLP('Logical reads',200000),makeLP('Block changes',40000),makeLP('Physical reads',8000),makeLP('Physical writes',15000),makeLP('User calls',2000),makeLP('Parses',150),makeLP('Hard parses',2),makeLP('Sorts',50),makeLP('Logons',3),makeLP('Executes',5000),makeLP('Transactions',2000),makeLP('User Commits',2000),makeLP('User Rollbacks',5)],
    waits2:[makeWaitEvent('log file sync','Commit',32,200000,8),makeWaitEvent('DB CPU','CPU',25),makeWaitEvent('log file parallel write','System I/O',12,100000,5),makeWaitEvent('db file sequential read','User I/O',15,30000,6),makeWaitEvent('free buffer waits','Configuration',5,5000,10)],
    sql2:[makeSql('commit_loop01',15,{sqlText:'UPDATE balances SET amt = :1 WHERE id = :2'})],
    _expect:{ topRule:'REDO_COMMIT', pTier:'P2', dbTimeReduction_range:[18,26], rationale_must_contain:['commit','log file sync'] }
}));

// S12: Redo suppressed by DBWR backlog
SCENARIOS.push(buildScenario('S12: Redo suppressed by DBWR', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:100,
    waits2:[makeWaitEvent('free buffer waits','Configuration',30,200000,25),makeWaitEvent('log file sync','Commit',22,100000,10),makeWaitEvent('buffer busy waits','Concurrency',15,80000,8),makeWaitEvent('DB CPU','CPU',12),makeWaitEvent('enq: FB - contention','Other',8,15000,12)],
    sql2:[makeSql('bulk_load01',28,{sqlText:'INSERT INTO staging_table SELECT * FROM ext_feed WHERE batch_id = :1',tableName:'STAGING_TABLE'})],
    _expect:{ topRule:'CONCURRENT_DML_BOTTLENECK',
        _custom:(ev,evaln)=>{
            const r=evaln.matches.find(m=>m.rule.id==='REDO_COMMIT');
            if(r)return{pass:false,note:'REDO_COMMIT fired despite freeBufPct=30>=20 — log file sync is a symptom'};
            return{pass:true,note:'REDO_COMMIT correctly suppressed'};
        }
    }
}));

// S13: Library Cache Pressure
SCENARIOS.push(buildScenario('S13: Library Cache', {
    cpus:8, dbTimeMin1:25, dbTimeMin2:70,
    lp2:[makeLP('DB Time(s/s)',70),makeLP('DB CPU(s/s)',2.0),makeLP('Redo size',3000000),makeLP('Logical reads',150000),makeLP('Block changes',3000),makeLP('Physical reads',8000),makeLP('Physical writes',1500),makeLP('User calls',3000),makeLP('Parses',2500),makeLP('Hard parses',2000),makeLP('Sorts',100),makeLP('Logons',5),makeLP('Executes',5000),makeLP('Transactions',200),makeLP('User Commits',200),makeLP('User Rollbacks',2)],
    waits2:[makeWaitEvent('library cache: mutex X','Concurrency',22,150000,8),makeWaitEvent('cursor: pin S wait on X','Concurrency',15,80000,5),makeWaitEvent('latch: shared pool','Concurrency',12,60000,3),makeWaitEvent('DB CPU','CPU',30),makeWaitEvent('db file sequential read','User I/O',10,20000,5)],
    eff2:{soft_parse_pct:20,library_cache_hit_pct:85},
    sql2:[makeSql('literal_sql',12,{sqlText:"SELECT * FROM users WHERE user_id = 12345"})],
    _expect:{ topRule:'LIBRARY_CACHE_PRESSURE', pTier:'P2', rationale_must_contain:['library cache','shared-pool'] }
}));

// S14: Concurrency — CBC latch
SCENARIOS.push(buildScenario('S14: Concurrency CBC', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:50,
    waits2:[makeWaitEvent('latch: cache buffers chains','Concurrency',18,200000,1),makeWaitEvent('cursor: pin S','Concurrency',5,30000,2),makeWaitEvent('DB CPU','CPU',45),makeWaitEvent('db file sequential read','User I/O',15,30000,5),makeWaitEvent('log file sync','Commit',4,8000,1),makeWaitEvent('free buffer waits','Configuration',3,2000,5)],
    sql2:[makeSql('hot_block01',18,{sqlText:'SELECT acct_balance FROM accounts WHERE acct_id = :1',bufGets:8000000})],
    _expect:{ topRule:'CONCURRENCY', dbTimeReduction_range:[10,16], rationale_must_contain:['cache-buffers-chains','cursor'] }
}));

// S15: Undo Segment
SCENARIOS.push(buildScenario('S15: Undo Segment', {
    cpus:8, dbTimeMin1:25, dbTimeMin2:55,
    waits2:[makeWaitEvent('enq: US - contention','Configuration',22,50000,20),makeWaitEvent('DB CPU','CPU',35),makeWaitEvent('db file sequential read','User I/O',18,40000,5),makeWaitEvent('log file sync','Commit',8,15000,2)],
    sql2:[makeSql('undo_query01',15,{sqlText:'UPDATE inventory SET qty = qty - :1 WHERE sku = :2'})],
    _expect:{ topRule:'UNDO_SEGMENT_EXTENSION', dbTimeReduction_range:[15,20], rationale_must_contain:['undo','US'] }
}));

// S16: Generic Load
SCENARIOS.push(buildScenario('S16: Generic Load', {
    cpus:16, dbTimeMin1:30, dbTimeMin2:75,
    waits2:[makeWaitEvent('DB CPU','CPU',40),makeWaitEvent('db file sequential read','User I/O',22,80000,6),makeWaitEvent('log file sync','Commit',8,20000,2),makeWaitEvent('db file scattered read','User I/O',6,10000,10)],
    sql2:[makeSql('mixed01',12,{sqlText:'SELECT * FROM orders WHERE status = :1'}),makeSql('mixed02',10,{sqlText:'SELECT * FROM products WHERE cat_id = :1'})],
    _expect:{ topRule:'GENERIC_LOAD_INCREASE', pTier:'P2', dbTimeReduction_range:[8,15], rationale_must_contain:['150','investigation'] }
}));

// S17: Generic Load — 5000% surge
SCENARIOS.push(buildScenario('S17: Generic 5000% surge', {
    cpus:8, dbTimeMin1:5, dbTimeMin2:255,
    waits2:[makeWaitEvent('DB CPU','CPU',35),makeWaitEvent('db file sequential read','User I/O',25,200000,8),makeWaitEvent('log file sync','Commit',8,30000,3),makeWaitEvent('latch: cache buffers chains','Concurrency',6,80000,1),makeWaitEvent('direct path read','User I/O',5,10000,12)],
    sql2:[makeSql('surge01',12,{sqlText:'SELECT * FROM reporting_vw'})],
    _expect:{
        _custom:(ev,evaln)=>{
            const r=evaln.matches.find(m=>m.rule.id==='GENERIC_LOAD_INCREASE');
            if(!r)return{pass:false,note:'GENERIC did not fire for 5000% delta'};
            const p=r.rule.project(ev);
            if(p.dbTimeReductionPct<20)return{pass:false,note:`Only ${p.dbTimeReductionPct.toFixed(1)}% for 5000% — should be ~25%`};
            return{pass:true,note:`5000% → ${p.dbTimeReductionPct.toFixed(1)}% recovery`};
        }
    }
}));

// S18: SQL Dominant
SCENARIOS.push(buildScenario('S18: SQL Dominant', {
    cpus:8, dbTimeMin1:25, dbTimeMin2:60,
    waits2:[makeWaitEvent('DB CPU','CPU',55),makeWaitEvent('db file sequential read','User I/O',18,60000,5),makeWaitEvent('log file sync','Commit',5,8000,1)],
    sql2:[makeSql('expensive01',42,{sqlText:'SELECT /*+ FULL(t) */ * FROM large_table t WHERE UPPER(name) LIKE :1',bufGets:15000000,diskReads:200000})],
    sqlAttrib:[{id:'expensive01',sql_id:'expensive01',pctDb:42,pct_db_time:42,epe1:0.5,epe2:2.0,isNew:false,is_new:false,isPlanChg:false,is_plan_change:false,isRegressed:true,is_regressed:true}],
    _expect:{ topRule:'SQL_DOMINANT', dbTimeReduction_range:[20,30], rationale_must_contain:['expensive01','per-execution'] }
}));

// S19: SQL Dominant suppressed — wait-dominated
SCENARIOS.push(buildScenario('S19: SQL suppressed by wait', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:80,
    waits2:[makeWaitEvent('enq: HW - contention','Configuration',45,200000,20),makeWaitEvent('DB CPU','CPU',18),makeWaitEvent('buffer busy waits','Concurrency',12,50000,8),makeWaitEvent('log file sync','Commit',8,15000,3)],
    sql2:[makeSql('symptom_sql01',35,{sqlText:'INSERT INTO hot_table VALUES (:1,:2,:3,:4)',tableName:'HOT_TABLE'})],
    sqlAttrib:[{id:'symptom_sql01',sql_id:'symptom_sql01',pctDb:35,pct_db_time:35,epe1:0.1,epe2:0.5,isNew:false,is_new:false,isPlanChg:false,is_plan_change:false}],
    _expect:{ topRule:'HW_ENQUEUE_CONTENTION',
        _custom:(ev,evaln)=>{
            const r=evaln.matches.find(m=>m.rule.id==='SQL_DOMINANT');
            if(r)return{pass:false,note:'SQL_DOMINANT fired despite wait-dominated pattern (HW=45%,CPU=18%)'};
            return{pass:true,note:'SQL_DOMINANT suppressed — SQL is symptom carrier'};
        }
    }
}));

// S20: TX Index Contention
SCENARIOS.push(buildScenario('S20: TX Index', {
    cpus:8, dbTimeMin1:25, dbTimeMin2:55,
    waits2:[makeWaitEvent('enq: TX - index contention','Concurrency',25,80000,15),makeWaitEvent('buffer busy waits','Concurrency',10,40000,5),makeWaitEvent('DB CPU','CPU',32),makeWaitEvent('db file sequential read','User I/O',15,30000,4),makeWaitEvent('log file sync','Commit',6,10000,2)],
    sql2:[makeSql('idx_insert01',20,{sqlText:'INSERT INTO transactions (txn_id, created_dt, amount) VALUES (seq_txn.NEXTVAL, SYSDATE, :1)'})],
    _expect:{ topRule:'TX_INDEX_CONTENTION', dbTimeReduction_range:[22,32], rationale_must_contain:['index','leaf block'] }
}));

// S21: Edge — Empty waits
SCENARIOS.push(buildScenario('S21: Edge — Empty waits', {
    cpus:4, dbTimeMin1:20, dbTimeMin2:25, waits2:[],
    sql2:[makeSql('edge01',15,{sqlText:'SELECT 1 FROM DUAL'})],
    _expect:{ pTier:'P3' }
}));

// S22: Edge — Zero CPUs
SCENARIOS.push(buildScenario('S22: Edge — Zero CPUs', {
    cpus:0, dbTimeMin1:30, dbTimeMin2:60,
    waits2:[makeWaitEvent('DB CPU','CPU',50),makeWaitEvent('db file sequential read','User I/O',30,50000,5)],
    sql2:[makeSql('edge02',20,{sqlText:'SELECT 1 FROM DUAL'})],
    _expect:{
        _custom:(ev,evaln)=>{
            const p=evaln.projection;
            if(p&&(isNaN(p.dbTimeReductionPct)||!isFinite(p.dbTimeReductionPct)))return{pass:false,note:'NaN/Inf in projection with 0 CPUs'};
            if(isNaN(ev.aasRatio)||!isFinite(ev.aasRatio))return{pass:false,note:`aasRatio=${ev.aasRatio} with 0 CPUs`};
            return{pass:true,note:`0 CPUs handled: aasRatio=${ev.aasRatio}, cpuUtilPct=${ev.cpuUtilPct}`};
        }
    }
}));

// S23: Edge — DB Time improved
SCENARIOS.push(buildScenario('S23: Edge — DB Time improved', {
    cpus:8, dbTimeMin1:60, dbTimeMin2:25,
    waits2:[makeWaitEvent('DB CPU','CPU',55),makeWaitEvent('db file sequential read','User I/O',20,30000,4),makeWaitEvent('log file sync','Commit',5,8000,1)],
    sql2:[makeSql('improved01',12,{sqlText:'SELECT * FROM optimized_view'})],
    _expect:{ pTier:'P3',
        _custom:(ev,evaln)=>{
            if(ev.dbTimeDelta>=0)return{pass:false,note:`Expected negative delta, got ${ev.dbTimeDelta.toFixed(1)}%`};
            const g=evaln.matches.find(m=>m.rule.id==='GENERIC_LOAD_INCREASE');
            if(g)return{pass:false,note:'GENERIC fired on improvement'};
            return{pass:true,note:`Delta=${ev.dbTimeDelta.toFixed(1)}% — correct improvement`};
        }
    }
}));

// S24: Double-count test — concPct vs latchPct (Bug #4 regression)
SCENARIOS.push(buildScenario('S24: Double-count latch/libcache', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:55,
    waits2:[makeWaitEvent('latch: cache buffers chains','Concurrency',10,100000,1),makeWaitEvent('cursor: pin S wait on X','Concurrency',5,30000,3),makeWaitEvent('latch: shared pool','Concurrency',12,60000,2),makeWaitEvent('latch: row cache objects','Concurrency',4,20000,1),makeWaitEvent('library cache: mutex X','Concurrency',8,40000,3),makeWaitEvent('DB CPU','CPU',35),makeWaitEvent('db file sequential read','User I/O',10,20000,4)],
    sql2:[makeSql('parse_test01',10,{sqlText:'SELECT 1 FROM DUAL'})],
    _expect:{
        _custom:(ev,evaln)=>{
            const errs=[];
            // latchPct = CBC(10)+cursor:pin(5)+shared pool(12)+row cache(4) = 31
            // sharedPoolLatchPct = shared pool(12)+row cache(4) = 16
            // concPct = max(0, 31-16) = 15
            if(Math.abs(ev.concPct-15)>1.5)errs.push(`concPct=${ev.concPct.toFixed(1)}, expected ~15`);
            if(Math.abs(ev.sharedPoolLatchPct-16)>1.5)errs.push(`sharedPoolLatchPct=${ev.sharedPoolLatchPct.toFixed(1)}, expected ~16`);
            const cr=evaln.matches.find(m=>m.rule.id==='CONCURRENCY');
            if(cr){
                const p=cr.rule.project(ev);
                if(p.dbTimeReductionPct>12)errs.push(`CONCURRENCY uses inflated value (${p.dbTimeReductionPct.toFixed(1)}%), expected ~9.0%`);
            }
            const lr=evaln.matches.find(m=>m.rule.id==='LIBRARY_CACHE_PRESSURE');
            if(!lr)errs.push('LIBRARY_CACHE_PRESSURE did not fire (libCachePct+sharedPoolLatchPct≈29%)');
            return errs.length?{pass:false,note:errs.join('; ')}:{pass:true,note:`Double-count OK: concPct=${ev.concPct.toFixed(1)}`};
        }
    }
}));

// S25: Buffer Cache below threshold (noise)
SCENARIOS.push(buildScenario('S25: Buffer below threshold', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:40,
    waits2:[makeWaitEvent('free buffer waits','Configuration',9,8000,10),makeWaitEvent('buffer busy waits','Concurrency',6,5000,5),makeWaitEvent('DB CPU','CPU',45),makeWaitEvent('db file sequential read','User I/O',22,40000,5),makeWaitEvent('log file sync','Commit',5,8000,1)],
    sql2:[makeSql('noise01',10,{sqlText:'SELECT * FROM small_table WHERE id = :1'})],
    _expect:{
        _custom:(ev,evaln)=>{
            const r=evaln.matches.find(m=>m.rule.id==='BUFFER_CACHE_WRITE_PRESSURE');
            if(r)return{pass:false,note:`BUFFER_CACHE fired at freeBuf=${ev.freeBufPct}%,bufBusy=${ev.bufBusyPct}% — below threshold`};
            return{pass:true,note:`Correctly rejected noise: freeBuf=${ev.freeBufPct}%, bufBusy=${ev.bufBusyPct}%`};
        }
    }
}));

// S26: Session Risk — WAIT-SATURATED
SCENARIOS.push(buildScenario('S26: Session WAIT-SATURATED', {
    cpus:4, dbTimeMin1:20, dbTimeMin2:80,
    lp2:[makeLP('DB Time(s/s)',80),makeLP('DB CPU(s/s)',0.5),makeLP('Redo size',5000000),makeLP('Logical reads',200000),makeLP('Block changes',5000),makeLP('Physical reads',10000),makeLP('Physical writes',2000),makeLP('User calls',500),makeLP('Parses',200),makeLP('Hard parses',5),makeLP('Sorts',50),makeLP('Logons',2),makeLP('Executes',3000),makeLP('Transactions',100),makeLP('User Commits',100),makeLP('User Rollbacks',1)],
    waits2:[makeWaitEvent('enq: TX - row lock contention','Application',55,200000,50),makeWaitEvent('DB CPU','CPU',12),makeWaitEvent('db file sequential read','User I/O',15,30000,5),makeWaitEvent('log file sync','Commit',5,10000,2)],
    sql2:[makeSql('wait_sat01',18,{sqlText:'UPDATE accts SET balance=:1 WHERE id=:2'})],
    _expect:{ sessionRisk:/WAIT-SATURATED|WAIT-BOUND/,
        _custom:(ev,evaln)=>{
            if(/CPU-BOUND|SATURATED NOW/.test(evaln.sessionRisk.label)&&ev.cpuUtilPct<30)
                return{pass:false,note:`"${evaln.sessionRisk.label}" but CPU only ${ev.cpuUtilPct.toFixed(0)}%`};
            return{pass:true,note:`Session risk: "${evaln.sessionRisk.label}" with CPU ${ev.cpuUtilPct.toFixed(0)}%`};
        }
    }
}));

// S27: Multi-Rule — Competing bottlenecks
SCENARIOS.push(buildScenario('S27: Multi-Rule', {
    cpus:8, dbTimeMin1:30, dbTimeMin2:90,
    waits2:[makeWaitEvent('enq: HW - contention','Configuration',20,80000,15),makeWaitEvent('enq: TX - row lock contention','Application',15,40000,30),makeWaitEvent('DB CPU','CPU',22),makeWaitEvent('db file sequential read','User I/O',18,40000,6),makeWaitEvent('log file sync','Commit',8,15000,3),makeWaitEvent('free buffer waits','Configuration',4,3000,8)],
    sql2:[makeSql('multi01',12,{sqlText:'INSERT INTO events VALUES (:1,:2,:3,:4)',tableName:'EVENTS'})],
    _expect:{ topRule:'HW_ENQUEUE_CONTENTION',
        _custom:(ev,evaln)=>{
            const errs=[];
            if(evaln.matches.length<3)errs.push(`Only ${evaln.matches.length} rules — expected ≥3`);
            if(evaln.confidence<70)errs.push(`Confidence ${evaln.confidence}% too low for multi-rule`);
            return errs.length?{pass:false,note:errs.join('; ')}:{pass:true,note:`${evaln.matches.length} rules, conf=${evaln.confidence}%`};
        }
    }
}));


// ── Step 5: Run all tests ─────────────────────────────────────────────────
let pass = 0, fail = 0, warn = 0;
const RESULTS = [];

console.log('╔══════════════════════════════════════════════════════════════╗');
console.log('║          PEEngine COMPREHENSIVE EXAM — 27 SCENARIOS         ║');
console.log('╚══════════════════════════════════════════════════════════════╝\n');

SCENARIOS.forEach((scenario, idx) => {
    const result = { name: scenario.name, checks: [], pass: true };
    try {
        const ctx = buildFn(scenario.data);
        ctx.sqlAttribution = scenario.sqlAttrib;
        const ev = PEEngine.extract(ctx);
        const evaln = PEEngine.evaluate(ev);
        const expect = scenario._config._expect || {};

        // Render checks (crash test only)
        try { PEEngine.renderScorecard(ev, evaln); } catch(e) { result.checks.push({pass:false,msg:'RENDER CRASH: scorecard: '+e.message}); result.pass=false; }
        try { PEEngine.renderImpactSimulator(ev, evaln); } catch(e) { result.checks.push({pass:false,msg:'RENDER CRASH: simulator: '+e.message}); result.pass=false; }

        // Top rule
        if (expect.topRule !== undefined) {
            const actual = evaln.top ? evaln.top.rule.id : null;
            if (actual !== expect.topRule) { result.checks.push({pass:false,msg:`TOP RULE: expected "${expect.topRule}", got "${actual}"`}); result.pass=false; }
            else result.checks.push({pass:true,msg:`TOP RULE: "${actual}" ✓`});
        }

        // P-tier
        if (expect.pTier) {
            if (evaln.pTier !== expect.pTier) { result.checks.push({pass:false,msg:`P-TIER: expected ${expect.pTier}, got ${evaln.pTier} (delta=${ev.dbTimeDelta.toFixed(0)}%)`}); result.pass=false; }
            else result.checks.push({pass:true,msg:`P-TIER: ${evaln.pTier} ✓`});
        }

        // Session risk
        if (expect.sessionRisk) {
            const lbl = evaln.sessionRisk.label;
            if (expect.sessionRisk instanceof RegExp) {
                if (!expect.sessionRisk.test(lbl)) { result.checks.push({pass:false,msg:`SESSION RISK: expected /${expect.sessionRisk.source}/, got "${lbl}"`}); result.pass=false; }
                else result.checks.push({pass:true,msg:`SESSION RISK: "${lbl}" ✓`});
            }
        }

        // Delta range
        if (expect.dbTimeDelta_range) {
            const [lo,hi] = expect.dbTimeDelta_range;
            if (ev.dbTimeDelta<lo||ev.dbTimeDelta>hi) { result.checks.push({pass:false,msg:`DELTA: ${ev.dbTimeDelta.toFixed(1)}% outside [${lo},${hi}]`}); result.pass=false; }
            else result.checks.push({pass:true,msg:`DELTA: ${ev.dbTimeDelta.toFixed(1)}% ✓`});
        }

        // Recovery range
        if (expect.dbTimeReduction_range && evaln.projection) {
            const [lo,hi] = expect.dbTimeReduction_range;
            const actual = evaln.projection.dbTimeReductionPct;
            if (actual<lo||actual>hi) { result.checks.push({pass:false,msg:`RECOVERY: ${actual.toFixed(1)}% outside [${lo},${hi}]`}); result.pass=false; }
            else result.checks.push({pass:true,msg:`RECOVERY: ${actual.toFixed(1)}% ✓`});
        }

        // sessionsFreed ≤ aasB
        if (evaln.projection && evaln.projection.sessionsFreed > ev.aasB * 1.01) {
            result.checks.push({pass:false,msg:`PHYSICS: sessionsFreed(${evaln.projection.sessionsFreed.toFixed(2)}) > aasB(${ev.aasB.toFixed(2)})`});
            result.pass = false;
        }

        // No NaN/Infinity
        const evKeys = ['cpus','aasG','aasB','aasRatio','cpuUtilPct','dbTimeDelta','ioPct','cpuPct','commitPct','freeBufPct','bufBusyPct','hwEnqPct','txEnqPct','txRowPct','txIdxPct','concPct','latchPct','libCachePct','sharedPoolLatchPct'];
        evKeys.forEach(k => {
            if (ev[k]===undefined||isNaN(ev[k])||!isFinite(ev[k])) {
                result.checks.push({pass:false,msg:`NaN: ev.${k}=${ev[k]}`}); result.pass=false;
            }
        });
        if (evaln.projection) {
            ['dbTimeReductionPct','sessionsFreed'].forEach(k => {
                if (evaln.projection[k]===undefined||isNaN(evaln.projection[k])||!isFinite(evaln.projection[k])) {
                    result.checks.push({pass:false,msg:`NaN: projection.${k}=${evaln.projection[k]}`}); result.pass=false;
                }
            });
            if (evaln.projection.dbTimeReductionPct < 0) { result.checks.push({pass:false,msg:`NEGATIVE recovery: ${evaln.projection.dbTimeReductionPct}`}); result.pass=false; }
        }

        // Rationale keywords
        if (expect.rationale_must_contain && evaln.projection) {
            const rat = (evaln.projection.rationale||'').toLowerCase();
            expect.rationale_must_contain.forEach(kw => {
                if (!rat.includes(kw.toLowerCase())) { result.checks.push({pass:false,msg:`RATIONALE missing "${kw}"`}); result.pass=false; }
            });
        }

        // Custom check
        if (expect._custom) {
            const cr = expect._custom(ev, evaln);
            result.checks.push({pass:cr.pass,msg:`CUSTOM: ${cr.note}`});
            if (!cr.pass) result.pass = false;
        }

        result.ev = { delta:ev.dbTimeDelta.toFixed(1)+'%', aasR:ev.aasRatio.toFixed(2), cpu:ev.cpuUtilPct.toFixed(0)+'%',
            io:ev.ioPct.toFixed(1)+'%', commit:ev.commitPct.toFixed(1)+'%', freeBuf:ev.freeBufPct.toFixed(1)+'%',
            hw:ev.hwEnqPct.toFixed(1)+'%', txRow:ev.txRowPct.toFixed(1)+'%', conc:ev.concPct.toFixed(1)+'%',
            lib:ev.libCachePct.toFixed(1)+'%', shPool:ev.sharedPoolLatchPct.toFixed(1)+'%',
            domSql:ev.domSqlPct.toFixed(1)+'%',
            rules:evaln.matches.map(m=>`${m.rule.id}(${m.weight.toFixed(2)})`).join(', '),
            pTier:evaln.pTier, conf:evaln.confidence+'%', risk:evaln.sessionRisk.label };

    } catch(e) {
        result.checks.push({pass:false,msg:`EXCEPTION: ${e.message}\n${e.stack}`});
        result.pass = false;
    }

    if (result.pass) pass++; else fail++;
    RESULTS.push(result);
});

// ── Step 6: Report ────────────────────────────────────────────────────────
console.log('\n' + '═'.repeat(70));
console.log('EXAM RESULTS');
console.log('═'.repeat(70));

RESULTS.forEach(r => {
    const icon = r.pass ? '✅' : '❌';
    console.log(`\n${icon} ${r.name}`);
    r.checks.forEach(c => console.log(`   ${c.pass?'  ✓':'  ✗'} ${c.msg}`));
    if (!r.pass && r.ev) {
        console.log('   📊', JSON.stringify(r.ev));
    }
});

console.log('\n' + '═'.repeat(70));
console.log(`FINAL: ${pass}/${SCENARIOS.length} PASSED  |  ${fail} FAILED  |  ${warn} WARNINGS`);
console.log('═'.repeat(70));

if (fail > 0) {
    console.log('\n🔴 FAILURES:');
    RESULTS.filter(r => !r.pass).forEach(r => {
        console.log(`   • ${r.name}`);
        r.checks.filter(c => !c.pass).forEach(c => console.log(`     → ${c.msg}`));
    });
}

// ── Step 7: Structural audit ──────────────────────────────────────────────
console.log('\n\n' + '═'.repeat(70));
console.log('STRUCTURAL AUDIT');
console.log('═'.repeat(70));

const issues = [];
PEEngine.RULES.forEach((r, i) => {
    if (!r.id) issues.push(`Rule[${i}] missing .id`);
    if (!r.label) issues.push(`Rule[${i}] missing .label`);
    if (typeof r.match !== 'function') issues.push(`Rule[${i}] .match not a function`);
    if (typeof r.weight !== 'function') issues.push(`Rule[${i}] .weight not a function`);
    if (typeof r.project !== 'function') issues.push(`Rule[${i}] .project not a function`);
});
const ids = PEEngine.RULES.map(r => r.id);
const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
if (dupes.length) issues.push(`Duplicate IDs: ${dupes.join(', ')}`);

// Weight range check with extreme ev
const testEv = {cpus:8,aasG:2,aasB:10,aasRatio:1.25,cpuUtilPct:50,domSqlId:'t',domSqlPct:50,domEpe1:1,domEpe2:10,domIsNew:true,domPlanChange:true,domIsRegressed:true,domSqlVerb:'INSERT',domIsDML:true,domTable:'T',topWaitName:'DB CPU',topWaitPct:50,topWaitClass:'CPU',ioPct:50,cpuPct:50,commitPct:50,concPct:30,freeBufPct:50,bufBusyPct:20,fbEnqPct:10,usEnqPct:20,txEnqPct:50,logBufPct:5,latchPct:30,hwEnqPct:50,txIdxPct:20,txRowPct:25,txItlPct:5,tmEnqPct:5,sqEnqPct:5,libCachePct:20,sharedPoolLatchPct:10,txnDelta:100,blockChgDelta:100,physWriteDelta:100,redoDelta:100,dbTimeDelta:200,dbT1:100,dbT2:300,bufferHitDrop:5,isParallel:false,bottleneckType:'',lblG:'Good',lblB:'Bad',dbName:'TEST'};

PEEngine.RULES.forEach(r => {
    try {
        if (r.match(testEv)) {
            const w = r.weight(testEv);
            if (w < 0 || w > 1.001) issues.push(`${r.id} weight=${w} out of [0,1]`);
            const p = r.project(testEv);
            if (p.dbTimeReductionPct < 0) issues.push(`${r.id} negative recovery`);
            if (p.dbTimeReductionPct > 100) issues.push(`${r.id} >100% recovery`);
            if (p.sessionsFreed < 0) issues.push(`${r.id} negative sessionsFreed`);
        }
    } catch(e) { issues.push(`${r.id} threw: ${e.message}`); }
});

if (issues.length) { console.log('🔴 Issues:'); issues.forEach(i => console.log(`   • ${i}`)); }
else console.log('✅ All rules structurally valid');

// Rule coverage
const fired = new Set();
RESULTS.forEach(r => { if(r.ev&&r.ev.rules) r.ev.rules.split(', ').forEach(rm => { const id=rm.split('(')[0]; if(id)fired.add(id); }); });
const unfired = ids.filter(id => !fired.has(id));
if (unfired.length) console.log(`⚠️  UNTESTED: ${unfired.join(', ')}`);
else console.log('✅ All rules tested — every rule fired in ≥1 scenario');

console.log('\n═══ EXAM COMPLETE ═══\n');
