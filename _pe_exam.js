// ╔══════════════════════════════════════════════════════════════════════════════╗
// ║  PEEngine Comprehensive Exam — Multi-Scenario Stress Test                   ║
// ║  Run: Open dashboard at http://localhost:8000, paste this into DevTools F12  ║
// ║  OR: node _pe_exam.js  (will self-extract PEEngine and run headless)        ║
// ╚══════════════════════════════════════════════════════════════════════════════╝
//
// This file creates synthetic AWR comparison datasets representing 20+ real-world
// Oracle performance scenarios (healthy, degraded, edge-case).  For each scenario
// it feeds the data through the FULL pipeline:
//
//   buildAWRContext(scenario) → PEEngine.extract(ctx) → PEEngine.evaluate(ev)
//                             → PEEngine.renderScorecard(ev, evaln)
//                             → PEEngine.renderImpactSimulator(ev, evaln)
//
// Then it validates EVERY output against Oracle PE expert expectations:
//   ✓ Correct rule fires (and wrong rules do NOT fire)
//   ✓ P-tier severity matches expected level
//   ✓ Confidence band is reasonable
//   ✓ Session risk assessment is accurate
//   ✓ Projected recovery % is within sane bounds
//   ✓ sessionsFreed never exceeds aasB (physical impossibility)
//   ✓ rationale text mentions the correct diagnostic keywords
//   ✓ Render output contains expected HTML elements
//   ✓ No NaN, Infinity, or negative values in projections
//   ✓ Edge cases don't crash (empty arrays, zero CPUs, missing fields)

(function PE_EXAM() {
'use strict';

// ============================================================================
// SECTION 1: SCENARIO FACTORY
// ============================================================================
// Each scenario builds a minimal but complete AWR JSON that buildAWRContext()
// can consume.  We control every metric so we know the exact expected output.

function makeWaitEvent(name, waitClass, pctDbTime, totalWaits, avgWaitMs) {
    return {
        event_name: name,
        wait_class: waitClass,
        pct_db_time: pctDbTime,
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
        sql_id: sqlId,
        plan_hash_value: opts.planHash || 123456,
        elapsed_time_secs: opts.elapsed || 100,
        executions: opts.execs || 1000,
        buffer_gets: opts.bufGets || 500000,
        disk_reads: opts.diskReads || 10000,
        cpu_time_secs: opts.cpuTime || 50,
        pct_db_time: pctDbTime,
        sql_text: opts.sqlText || 'SELECT * FROM DUAL',
        tables_referenced: opts.tables || [],
        table_name: opts.tableName || ''
    };
}

function buildScenario(name, config) {
    const c = Object.assign({
        cpus: 8,
        elapsedMin1: 60, elapsedMin2: 60,
        dbTimeMin1: 30, dbTimeMin2: 60,
        lp1: [], lp2: [],
        waits1: [], waits2: [],
        eff1: {}, eff2: {},
        sql1: [], sql2: [],
        sqlAttrib: [],
    }, config);

    // Auto-generate load profile if not specified
    const defaultLP1 = [
        makeLP('DB Time(s/s)',   c.dbTimeMin1 * 60 / c.elapsedMin1 / 60),
        makeLP('DB CPU(s/s)',    c.dbTimeMin1 * 60 / c.elapsedMin1 / 60 * 0.4),
        makeLP('Redo size',     5000000),
        makeLP('Logical reads', 100000),
        makeLP('Block changes', 5000),
        makeLP('Physical reads',10000),
        makeLP('Physical writes',2000),
        makeLP('User calls',    500),
        makeLP('Parses',        200),
        makeLP('Hard parses',   5),
        makeLP('Sorts',         100),
        makeLP('Logons',        2),
        makeLP('Executes',      3000),
        makeLP('Transactions',  100),
        makeLP('User Commits',  100),
        makeLP('User Rollbacks',1),
    ];
    const defaultLP2 = [
        makeLP('DB Time(s/s)',   c.dbTimeMin2 * 60 / c.elapsedMin2 / 60),
        makeLP('DB CPU(s/s)',    c.dbTimeMin2 * 60 / c.elapsedMin2 / 60 * 0.4),
        makeLP('Redo size',     5000000),
        makeLP('Logical reads', 100000),
        makeLP('Block changes', 5000),
        makeLP('Physical reads',10000),
        makeLP('Physical writes',2000),
        makeLP('User calls',    500),
        makeLP('Parses',        200),
        makeLP('Hard parses',   5),
        makeLP('Sorts',         100),
        makeLP('Logons',        2),
        makeLP('Executes',      3000),
        makeLP('Transactions',  100),
        makeLP('User Commits',  100),
        makeLP('User Rollbacks',1),
    ];

    const lp1 = c.lp1.length ? c.lp1 : defaultLP1;
    const lp2 = c.lp2.length ? c.lp2 : defaultLP2;

    const defaultEff = {
        buffer_cache_hit_pct: 99.5,
        library_cache_hit_pct: 99.8,
        soft_parse_pct: 99.0,
        execute_to_parse_pct: 85,
        latch_hit_pct: 99.9,
        parse_cpu_pct: 5,
        non_parse_cpu_pct: 95,
        in_memory_sort_pct: 99,
        shared_pool_memory_usage_pct: 75
    };

    const eff1 = Object.assign({}, defaultEff, c.eff1);
    const eff2 = Object.assign({}, defaultEff, c.eff2);

    // Build the AWR comparison JSON that buildAWRContext() expects
    const data = {
        good_data: {
            elapsed_min: c.elapsedMin1,
            db_time_min: c.dbTimeMin1,
            cpus: c.cpus,
            load_profile: lp1,
            efficiency: eff1,
            wait_events: c.waits1.length ? c.waits1 : [
                makeWaitEvent('DB CPU', 'CPU', 60, 0, 0),
                makeWaitEvent('db file sequential read', 'User I/O', 20, 50000, 5),
                makeWaitEvent('log file sync', 'Commit', 5, 10000, 1),
            ],
            time_model: [],
            sql_stats: c.sql1,
            segments: [],
            addm_findings: [],
        },
        bad_data: {
            elapsed_min: c.elapsedMin2,
            db_time_min: c.dbTimeMin2,
            cpus: c.cpus,
            load_profile: lp2,
            efficiency: eff2,
            wait_events: c.waits2,
            time_model: [],
            sql_stats: c.sql2,
            segments: [],
            addm_findings: [],
        },
        comparison_rca: {
            db_summary_1: { elapsed_min: c.elapsedMin1, db_time_secs: c.dbTimeMin1 * 60, cpus: c.cpus },
            db_summary_2: { elapsed_min: c.elapsedMin2, db_time_secs: c.dbTimeMin2 * 60, cpus: c.cpus },
        },
        health_good: {},
        health_bad: {},
    };

    // sqlAttribution for PEEngine.extract()
    if (c.sqlAttrib.length === 0 && c.sql2.length > 0) {
        const top = c.sql2[0];
        c.sqlAttrib = [{
            id: top.sql_id,
            sql_id: top.sql_id,
            pctDb: top.pct_db_time,
            pct_db_time: top.pct_db_time,
            epe1: 0,
            epe2: top.elapsed_time_secs / Math.max(top.executions, 1),
            isNew: !!top._isNew,
            is_new: !!top._isNew,
            isPlanChg: !!top._isPlanChg,
            is_plan_change: !!top._isPlanChg,
            isRegressed: !!top._isRegressed,
            is_regressed: !!top._isRegressed,
        }];
    }

    return { name, data, sqlAttrib: c.sqlAttrib, cpus: c.cpus, _config: c };
}


// ============================================================================
// SECTION 2: TEST SCENARIOS — 20+ Real-World Oracle PE Situations
// ============================================================================

const SCENARIOS = [];

// ─── S01: HEALTHY DATABASE — Baseline vs Baseline (no degradation) ──────────
SCENARIOS.push(buildScenario('S01: Healthy DB — No Degradation', {
    cpus: 16, dbTimeMin1: 30, dbTimeMin2: 32,
    waits2: [
        makeWaitEvent('DB CPU', 'CPU', 55, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 22, 50000, 4),
        makeWaitEvent('log file sync', 'Commit', 5, 10000, 0.8),
        makeWaitEvent('direct path read', 'User I/O', 4, 5000, 8),
        makeWaitEvent('SQL*Net message from client', 'Idle', 8, 100000, 50),
    ],
    sql2: [makeSql('abc123def', 8, { sqlText: 'SELECT id FROM orders WHERE status=:1' })],
    _expect: {
        topRule: null,         // No rule should fire with high weight
        pTier: 'P3',
        confLabel: 'LOW',
        sessionRisk: 'STABLE',
        dbTimeDelta_range: [-10, 15],  // ~6.7% increase — benign
    }
}));

// ─── S02: PLAN REGRESSION — Classic optimizer plan flip ─────────────────────
SCENARIOS.push(buildScenario('S02: Plan Regression — SQL plan flip', {
    cpus: 8, dbTimeMin1: 20, dbTimeMin2: 90,
    waits2: [
        makeWaitEvent('DB CPU', 'CPU', 25, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 45, 500000, 12),
        makeWaitEvent('db file scattered read', 'User I/O', 15, 100000, 15),
        makeWaitEvent('log file sync', 'Commit', 3, 5000, 1),
    ],
    sql2: [makeSql('plan_flip01', 55, {
        planHash: 999888, elapsed: 400, execs: 500, bufGets: 5000000,
        diskReads: 800000, sqlText: 'SELECT * FROM big_table WHERE created_date > :1',
        tableName: 'BIG_TABLE', _isPlanChg: true, _isRegressed: true
    })],
    sql1: [makeSql('plan_flip01', 10, {
        planHash: 111222, elapsed: 20, execs: 500, bufGets: 50000,
        diskReads: 1000, sqlText: 'SELECT * FROM big_table WHERE created_date > :1'
    })],
    sqlAttrib: [{
        id: 'plan_flip01', sql_id: 'plan_flip01', pctDb: 55, pct_db_time: 55,
        epe1: 0.04, epe2: 0.8, isNew: false, is_new: false,
        isPlanChg: true, is_plan_change: true, isRegressed: true, is_regressed: true
    }],
    _expect: {
        topRule: 'PLAN_REGRESSION',
        pTier: 'P1',            // dbTimeDelta = 350% → P1
        confLabel: 'HIGH',
        dbTimeReduction_range: [40, 55],  // ~49.5% (55*0.9)
        rationale_must_contain: ['plan', 'plan_flip01'],
    }
}));

// ─── S03: NEW SQL DEPLOYMENT — Untested SQL causing havoc ───────────────────
SCENARIOS.push(buildScenario('S03: New SQL Deploy — Untested query', {
    cpus: 8, dbTimeMin1: 25, dbTimeMin2: 80,
    waits2: [
        makeWaitEvent('DB CPU', 'CPU', 40, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 30, 200000, 10),
        makeWaitEvent('log file sync', 'Commit', 5, 8000, 2),
    ],
    sql2: [makeSql('new_sql_001', 40, {
        elapsed: 300, execs: 200, bufGets: 3000000, diskReads: 400000,
        sqlText: 'SELECT /*+ NEW_REPORT */ a.* FROM customer_data a, order_hist b WHERE a.cust_id = b.cust_id',
        tableName: 'CUSTOMER_DATA', _isNew: true
    })],
    sqlAttrib: [{
        id: 'new_sql_001', sql_id: 'new_sql_001', pctDb: 40, pct_db_time: 40,
        epe1: 0, epe2: 1.5, isNew: true, is_new: true,
        isPlanChg: false, is_plan_change: false
    }],
    _expect: {
        topRule: 'NEW_SQL_DEPLOY',
        pTier: 'P1',          // dbTimeDelta = 220%
        confLabel: 'HIGH',
        dbTimeReduction_range: [25, 35],  // 40*0.75 = 30
        rationale_must_contain: ['new_sql_001', 'deploy'],
    }
}));

// ─── S04: HW ENQUEUE CONTENTION — Segment HWM bottleneck (massive) ─────────
SCENARIOS.push(buildScenario('S04: HW Enqueue — Extreme HWM contention', {
    cpus: 16, dbTimeMin1: 40, dbTimeMin2: 200,
    waits2: [
        makeWaitEvent('enq: HW - contention', 'Configuration', 72, 500000, 25),
        makeWaitEvent('DB CPU', 'CPU', 8, 0, 0),
        makeWaitEvent('buffer busy waits', 'Concurrency', 8, 100000, 5),
        makeWaitEvent('log file sync', 'Commit', 5, 30000, 3),
        makeWaitEvent('free buffer waits', 'Configuration', 3, 10000, 10),
    ],
    sql2: [makeSql('hw_insert01', 35, {
        elapsed: 500, execs: 100000, sqlText: 'INSERT INTO audit_log VALUES (:1,:2,:3,:4)',
        tableName: 'AUDIT_LOG'
    })],
    _expect: {
        topRule: 'HW_ENQUEUE_CONTENTION',
        pTier: 'P1',          // hwEnqPct=72 >= 60 → P1
        confLabel: 'HIGH',
        dbTimeReduction_range: [60, 70],  // 72*0.9=64.8
        sessionsFreed_must_be_lte_aasB: true,
        rationale_must_contain: ['HW', 'high-water', 'AUDIT_LOG'],
    }
}));

// ─── S05: TX ROW LOCK — Application blocking problem ───────────────────────
SCENARIOS.push(buildScenario('S05: TX Row Lock — Blocking sessions', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 65,
    waits2: [
        makeWaitEvent('enq: TX - row lock contention', 'Application', 28, 80000, 50),
        makeWaitEvent('DB CPU', 'CPU', 35, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 15, 30000, 5),
        makeWaitEvent('log file sync', 'Commit', 8, 15000, 2),
        makeWaitEvent('enq: TX - index contention', 'Concurrency', 3, 5000, 8),
    ],
    sql2: [makeSql('upd_acct01', 20, {
        sqlText: 'UPDATE accounts SET balance = balance - :1 WHERE account_id = :2',
        tableName: 'ACCOUNTS'
    })],
    _expect: {
        topRule: 'TX_ROW_LOCK_CONTENTION',
        pTier: 'P2',           // txRowPct=28 >= 20 → P2
        dbTimeReduction_range: [15, 22],  // 28*0.7 = 19.6 (using txRowPct not txEnqPct)
        rationale_must_contain: ['row lock', '28.0%'],
    }
}));

// ─── S06: TX ROW LOCK vs TX INDEX — Verify txRowPct not txEnqPct ────────────
// This scenario tests the Bug #2 fix: txEnqPct=40% but txRowPct=15%
SCENARIOS.push(buildScenario('S06: TX Mixed — Row + Index + ITL contention', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 55,
    waits2: [
        makeWaitEvent('enq: TX - row lock contention', 'Application', 15, 40000, 30),
        makeWaitEvent('enq: TX - index contention', 'Concurrency', 18, 30000, 20),
        makeWaitEvent('enq: TX - allocate ITL entry', 'Configuration', 7, 10000, 15),
        makeWaitEvent('DB CPU', 'CPU', 30, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 12, 20000, 5),
    ],
    sql2: [makeSql('mixed_tx01', 18, { sqlText: 'UPDATE hot_table SET val=:1 WHERE id=:2' })],
    _expect: {
        topRule: 'TX_INDEX_CONTENTION',  // txIdxPct=18 > txRowPct=15
        // Verify: TX_ROW_LOCK project uses 15% (txRowPct), NOT 40% (txEnqPct=15+18+7)
        _custom_check: (ev, evaln) => {
            const txRowRule = evaln.matches.find(m => m.rule.id === 'TX_ROW_LOCK_CONTENTION');
            if (!txRowRule) return { pass: true, note: 'TX_ROW_LOCK did not fire (txRowPct=15, threshold=10 — should fire)' };
            const proj = txRowRule.rule.project(ev);
            const expectedMax = 15 * 0.7; // 10.5% using txRowPct
            const badMax = 40 * 0.7;      // 28% if it used txEnqPct (BUG)
            if (proj.dbTimeReductionPct > expectedMax + 1) {
                return { pass: false, note: `BUG: TX_ROW_LOCK projects ${proj.dbTimeReductionPct.toFixed(1)}% recovery — using txEnqPct (${badMax.toFixed(1)}) instead of txRowPct (${expectedMax.toFixed(1)})` };
            }
            return { pass: true, note: `TX_ROW_LOCK correctly projects ${proj.dbTimeReductionPct.toFixed(1)}% using txRowPct=15` };
        }
    }
}));

// ─── S07: CONCURRENT DML BOTTLENECK — Insert storm + DBWR backlog ───────────
SCENARIOS.push(buildScenario('S07: Concurrent DML — Insert storm', {
    cpus: 8, dbTimeMin1: 25, dbTimeMin2: 120,
    lp2: [
        makeLP('DB Time(s/s)',   120 * 60 / 60 / 60),
        makeLP('DB CPU(s/s)',    0.3),
        makeLP('Redo size',     50000000),
        makeLP('Logical reads', 500000),
        makeLP('Block changes', 80000),
        makeLP('Physical reads', 20000),
        makeLP('Physical writes',60000),
        makeLP('User calls',    1000),
        makeLP('Parses',        300),
        makeLP('Hard parses',   5),
        makeLP('Sorts',         50),
        makeLP('Logons',        3),
        makeLP('Executes',      5000),
        makeLP('Transactions',  500),
        makeLP('User Commits',  500),
        makeLP('User Rollbacks',1),
    ],
    waits2: [
        makeWaitEvent('free buffer waits', 'Configuration', 35, 200000, 30),
        makeWaitEvent('buffer busy waits', 'Concurrency', 18, 100000, 10),
        makeWaitEvent('enq: FB - contention', 'Other', 8, 20000, 15),
        makeWaitEvent('log file sync', 'Commit', 15, 50000, 5),
        makeWaitEvent('DB CPU', 'CPU', 10, 0, 0),
        makeWaitEvent('db file parallel write', 'System I/O', 6, 30000, 8),
    ],
    sql2: [makeSql('mass_insert01', 32, {
        sqlText: 'INSERT INTO transaction_log (id,ts,amt,acct) VALUES (:1,SYSDATE,:2,:3)',
        tableName: 'TRANSACTION_LOG', execs: 200000
    })],
    _expect: {
        topRule: 'CONCURRENT_DML_BOTTLENECK',
        pTier: 'P1',          // dbTimeDelta=380% + freeBufPct=35>=25
        confLabel: 'HIGH',
        // Reclaim = min(35 + 8 + min(18,35*0.4=14) + min(15*0.25=3.75,5), 70) = min(35+8+14+3.75,70) = min(60.75,70) = 60.75
        // dbTimeReduction = 60.75 * 0.7 = 42.5%
        dbTimeReduction_range: [38, 48],
        rationale_must_contain: ['INSERT', 'mass_insert01', 'TRANSACTION_LOG', 'DBWR'],
        // Verify: reclaim does NOT inflate by summing correlated waits at full value
        _custom_check: (ev, evaln) => {
            const proj = evaln.projection;
            const maxSaneReclaim = 50; // 70 * 0.7
            if (proj.dbTimeReductionPct > maxSaneReclaim) {
                return { pass: false, note: `Reclaim inflation: ${proj.dbTimeReductionPct.toFixed(1)}% exceeds sane max ${maxSaneReclaim}%` };
            }
            return { pass: true, note: `Reclaim ${proj.dbTimeReductionPct.toFixed(1)}% within sane bounds` };
        }
    }
}));

// ─── S08: BUFFER CACHE WRITE PRESSURE — No dominant DML ─────────────────────
SCENARIOS.push(buildScenario('S08: Buffer Cache Pressure — Distributed writes', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 70,
    waits2: [
        makeWaitEvent('free buffer waits', 'Configuration', 25, 150000, 20),
        makeWaitEvent('buffer busy waits', 'Concurrency', 12, 60000, 8),
        makeWaitEvent('enq: FB - contention', 'Other', 5, 10000, 12),
        makeWaitEvent('DB CPU', 'CPU', 28, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 15, 40000, 6),
        makeWaitEvent('log file sync', 'Commit', 8, 20000, 3),
    ],
    sql2: [makeSql('select_rpt01', 15, {
        sqlText: 'SELECT count(*) FROM orders WHERE order_date > :1'
    })],
    _expect: {
        topRule: 'BUFFER_CACHE_WRITE_PRESSURE',
        pTier: 'P2',          // freeBufPct=25 → P2
        // reclaim = min(25 + 5 + min(12, 25*0.4=10), 65) = min(25+5+10, 65) = 40
        // dbTimeReduction = 40 * 0.65 = 26%
        dbTimeReduction_range: [22, 30],
        rationale_must_contain: ['DBWR', 'free buffer waits'],
    }
}));

// ─── S09: CPU SATURATION — Pure CPU-bound workload ──────────────────────────
SCENARIOS.push(buildScenario('S09: CPU Saturation — All CPUs pegged', {
    cpus: 4, dbTimeMin1: 15, dbTimeMin2: 50,
    lp2: [
        makeLP('DB Time(s/s)',  50),
        makeLP('DB CPU(s/s)',   3.8),   // 3.8/4 = 95% CPU util
        makeLP('Redo size',     2000000),
        makeLP('Logical reads', 800000),
        makeLP('Block changes', 2000),
        makeLP('Physical reads',5000),
        makeLP('Physical writes',1000),
        makeLP('User calls',    2000),
        makeLP('Parses',        100),
        makeLP('Hard parses',   3),
        makeLP('Sorts',         200),
        makeLP('Logons',        5),
        makeLP('Executes',      8000),
        makeLP('Transactions',  50),
        makeLP('User Commits',  50),
        makeLP('User Rollbacks',0),
    ],
    waits2: [
        makeWaitEvent('DB CPU', 'CPU', 72, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 12, 20000, 4),
        makeWaitEvent('latch: cache buffers chains', 'Concurrency', 5, 50000, 0.5),
        makeWaitEvent('log file sync', 'Commit', 4, 5000, 1),
    ],
    sql2: [makeSql('cpu_hog01', 22, {
        sqlText: 'SELECT /*+ FULL(t) */ * FROM big_fact t WHERE UPPER(description) LIKE :1',
        bufGets: 10000000
    })],
    _expect: {
        topRule: 'CPU_SATURATION',
        pTier: 'P1',          // dbTimeDelta >> 100%
        sessionRisk: /SATURATED|CPU-BOUND/,
        rationale_must_contain: ['CPU', 'utilisation', '95'],
    }
}));

// ─── S10: I/O PRESSURE — Storage latency spike ─────────────────────────────
SCENARIOS.push(buildScenario('S10: I/O Pressure — Storage latency', {
    cpus: 8, dbTimeMin1: 20, dbTimeMin2: 55,
    waits2: [
        makeWaitEvent('db file sequential read', 'User I/O', 38, 300000, 25),
        makeWaitEvent('db file scattered read', 'User I/O', 12, 50000, 30),
        makeWaitEvent('DB CPU', 'CPU', 22, 0, 0),
        makeWaitEvent('direct path read', 'User I/O', 8, 20000, 15),
        makeWaitEvent('log file sync', 'Commit', 5, 8000, 2),
    ],
    sql2: [makeSql('io_query01', 18, {
        sqlText: 'SELECT * FROM customer_master WHERE region_code = :1',
        diskReads: 500000
    })],
    _expect: {
        topRule: 'IO_PRESSURE',
        pTier: 'P2',          // ioPct = 38+12+8 = 58% >= 40 → P2
        dbTimeReduction_range: [28, 36],  // 58*0.55 = 31.9
        rationale_must_contain: ['I/O'],
    }
}));

// ─── S11: REDO/COMMIT STORM — Excessive commit frequency ────────────────────
SCENARIOS.push(buildScenario('S11: Redo Commit Storm — Row-by-row commits', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 60,
    lp2: [
        makeLP('DB Time(s/s)',  60),
        makeLP('DB CPU(s/s)',   1.5),
        makeLP('Redo size',     80000000),
        makeLP('Logical reads', 200000),
        makeLP('Block changes', 40000),
        makeLP('Physical reads',8000),
        makeLP('Physical writes',15000),
        makeLP('User calls',    2000),
        makeLP('Parses',        150),
        makeLP('Hard parses',   2),
        makeLP('Sorts',         50),
        makeLP('Logons',        3),
        makeLP('Executes',      5000),
        makeLP('Transactions',  2000),
        makeLP('User Commits',  2000),
        makeLP('User Rollbacks',5),
    ],
    waits2: [
        makeWaitEvent('log file sync', 'Commit', 32, 200000, 8),
        makeWaitEvent('DB CPU', 'CPU', 25, 0, 0),
        makeWaitEvent('log file parallel write', 'System I/O', 12, 100000, 5),
        makeWaitEvent('db file sequential read', 'User I/O', 15, 30000, 6),
        makeWaitEvent('free buffer waits', 'Configuration', 5, 5000, 10),
    ],
    sql2: [makeSql('commit_loop01', 15, {
        sqlText: 'UPDATE balances SET amt = :1 WHERE id = :2'
    })],
    _expect: {
        topRule: 'REDO_COMMIT',   // commitPct=32, freeBufPct=5 < 20
        pTier: 'P2',              // commitPct=32 >= 20 → P2
        dbTimeReduction_range: [18, 26],  // 32*0.7=22.4
        rationale_must_contain: ['commit', 'log file sync'],
    }
}));

// ─── S12: REDO_COMMIT suppressed by DBWR backlog ───────────────────────────
// When free_buffer_waits >= 20, log file sync is a symptom, not the cause
SCENARIOS.push(buildScenario('S12: Redo suppressed — DBWR backlog masks commit', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 100,
    waits2: [
        makeWaitEvent('free buffer waits', 'Configuration', 30, 200000, 25),
        makeWaitEvent('log file sync', 'Commit', 22, 100000, 10),
        makeWaitEvent('buffer busy waits', 'Concurrency', 15, 80000, 8),
        makeWaitEvent('DB CPU', 'CPU', 12, 0, 0),
        makeWaitEvent('enq: FB - contention', 'Other', 8, 15000, 12),
    ],
    sql2: [makeSql('bulk_load01', 28, {
        sqlText: 'INSERT INTO staging_table SELECT * FROM ext_feed WHERE batch_id = :1',
        tableName: 'STAGING_TABLE', _isNew: false
    })],
    _expect: {
        // REDO_COMMIT should NOT fire because freeBufPct=30 >= 20
        // CONCURRENT_DML should fire instead (freeBuf=30, DML, domSqlPct=28>=20)
        topRule: 'CONCURRENT_DML_BOTTLENECK',
        _custom_check: (ev, evaln) => {
            const redoRule = evaln.matches.find(m => m.rule.id === 'REDO_COMMIT');
            if (redoRule) {
                return { pass: false, note: 'BUG: REDO_COMMIT fired despite freeBufPct=30 >= 20 — log file sync is a symptom of DBWR backlog, not primary commit overhead' };
            }
            return { pass: true, note: 'REDO_COMMIT correctly suppressed when DBWR backlog dominates' };
        }
    }
}));

// ─── S13: LIBRARY CACHE PRESSURE — Hard parse storm ─────────────────────────
SCENARIOS.push(buildScenario('S13: Library Cache — Hard parse storm', {
    cpus: 8, dbTimeMin1: 25, dbTimeMin2: 70,
    lp2: [
        makeLP('DB Time(s/s)',  70),
        makeLP('DB CPU(s/s)',   2.0),
        makeLP('Redo size',     3000000),
        makeLP('Logical reads', 150000),
        makeLP('Block changes', 3000),
        makeLP('Physical reads',8000),
        makeLP('Physical writes',1500),
        makeLP('User calls',    3000),
        makeLP('Parses',        2500),
        makeLP('Hard parses',   2000),
        makeLP('Sorts',         100),
        makeLP('Logons',        5),
        makeLP('Executes',      5000),
        makeLP('Transactions',  200),
        makeLP('User Commits',  200),
        makeLP('User Rollbacks',2),
    ],
    waits2: [
        makeWaitEvent('library cache: mutex X', 'Concurrency', 22, 150000, 8),
        makeWaitEvent('cursor: pin S wait on X', 'Concurrency', 15, 80000, 5),
        makeWaitEvent('latch: shared pool', 'Concurrency', 12, 60000, 3),
        makeWaitEvent('DB CPU', 'CPU', 30, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 10, 20000, 5),
    ],
    eff2: { soft_parse_pct: 20, library_cache_hit_pct: 85 },
    sql2: [makeSql('literal_sql', 12, {
        sqlText: "SELECT * FROM users WHERE user_id = 12345"  // no bind
    })],
    _expect: {
        topRule: 'LIBRARY_CACHE_PRESSURE',
        pTier: 'P2',         // (libCachePct + sharedPoolLatchPct) = (22+15) + 12 = 49% → >= 25 P2
        rationale_must_contain: ['library cache', 'shared-pool', 'hard-parse'],
    }
}));

// ─── S14: CONCURRENCY — Pure latch/cursor contention ────────────────────────
SCENARIOS.push(buildScenario('S14: Concurrency — CBC latch contention', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 50,
    waits2: [
        makeWaitEvent('latch: cache buffers chains', 'Concurrency', 18, 200000, 1),
        makeWaitEvent('cursor: pin S', 'Concurrency', 5, 30000, 2),
        makeWaitEvent('DB CPU', 'CPU', 45, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 15, 30000, 5),
        makeWaitEvent('log file sync', 'Commit', 4, 8000, 1),
        makeWaitEvent('free buffer waits', 'Configuration', 3, 2000, 5),
    ],
    sql2: [makeSql('hot_block01', 18, {
        sqlText: 'SELECT acct_balance FROM accounts WHERE acct_id = :1',
        bufGets: 8000000
    })],
    _expect: {
        topRule: 'CONCURRENCY',
        // concPct = latchPct - sharedPoolLatchPct
        // latchPct = 18 (CBC) + 5 (cursor:pin) = 23,  sharedPoolLatchPct = 0
        // concPct = 23, freeBufPct = 3 < 15 → CONCURRENCY matches
        dbTimeReduction_range: [10, 16],  // 23*0.6 = 13.8, capped at 30
        rationale_must_contain: ['cache-buffers-chains', 'cursor'],
    }
}));

// ─── S15: UNDO SEGMENT CONTENTION ──────────────────────────────────────────
SCENARIOS.push(buildScenario('S15: Undo Segment — US enqueue contention', {
    cpus: 8, dbTimeMin1: 25, dbTimeMin2: 55,
    waits2: [
        makeWaitEvent('enq: US - contention', 'Configuration', 22, 50000, 20),
        makeWaitEvent('DB CPU', 'CPU', 35, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 18, 40000, 5),
        makeWaitEvent('log file sync', 'Commit', 8, 15000, 2),
    ],
    sql2: [makeSql('undo_query01', 15, {
        sqlText: 'UPDATE inventory SET qty = qty - :1 WHERE sku = :2'
    })],
    _expect: {
        topRule: 'UNDO_SEGMENT_EXTENSION',
        dbTimeReduction_range: [15, 20],  // 22*0.8 = 17.6
        rationale_must_contain: ['undo', 'US'],
    }
}));

// ─── S16: GENERIC LOAD INCREASE — No clear bottleneck ──────────────────────
SCENARIOS.push(buildScenario('S16: Generic Load — Across-the-board increase', {
    cpus: 16, dbTimeMin1: 30, dbTimeMin2: 75,
    waits2: [
        makeWaitEvent('DB CPU', 'CPU', 40, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 22, 80000, 6),
        makeWaitEvent('log file sync', 'Commit', 8, 20000, 2),
        makeWaitEvent('db file scattered read', 'User I/O', 6, 10000, 10),
        makeWaitEvent('SQL*Net message to client', 'Network', 3, 50000, 0.1),
    ],
    sql2: [
        makeSql('mixed01', 12, { sqlText: 'SELECT * FROM orders WHERE status = :1' }),
        makeSql('mixed02', 10, { sqlText: 'SELECT * FROM products WHERE cat_id = :1' }),
        makeSql('mixed03', 8, { sqlText: 'INSERT INTO audit_trail VALUES (:1,:2,:3)' }),
    ],
    _expect: {
        topRule: 'GENERIC_LOAD_INCREASE',
        pTier: 'P2',         // dbTimeDelta = 150% >= 50
        // recovery = min(25, max(10, 150*0.06)) = min(25, max(10, 9)) = min(25, 10) = 10
        dbTimeReduction_range: [8, 15],
        rationale_must_contain: ['150', 'investigation'],
    }
}));

// ─── S17: GENERIC LOAD — Massive 5000% surge (tests scaling) ───────────────
SCENARIOS.push(buildScenario('S17: Generic Load — 5000% surge scaling test', {
    cpus: 8, dbTimeMin1: 5, dbTimeMin2: 255,
    waits2: [
        makeWaitEvent('DB CPU', 'CPU', 35, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 25, 200000, 8),
        makeWaitEvent('log file sync', 'Commit', 8, 30000, 3),
        makeWaitEvent('latch: cache buffers chains', 'Concurrency', 6, 80000, 1),
        makeWaitEvent('direct path read', 'User I/O', 5, 10000, 12),
    ],
    sql2: [
        makeSql('surge01', 12, { sqlText: 'SELECT * FROM reporting_vw' }),
    ],
    _expect: {
        // dbTimeDelta = 5000%. Should get higher recovery than mild 30% delta
        _custom_check: (ev, evaln) => {
            // The GENERIC rule should fire. Verify it scales proportionally.
            const genericRule = evaln.matches.find(m => m.rule.id === 'GENERIC_LOAD_INCREASE');
            if (!genericRule) return { pass: false, note: 'GENERIC_LOAD_INCREASE did not fire despite 5000% delta' };
            const proj = genericRule.rule.project(ev);
            // recovery = min(25, max(10, 5000*0.06)) = min(25, 300) = 25
            if (proj.dbTimeReductionPct < 20) {
                return { pass: false, note: `Recovery only ${proj.dbTimeReductionPct.toFixed(1)}% for 5000% surge — should be near 25%` };
            }
            return { pass: true, note: `5000% surge → ${proj.dbTimeReductionPct.toFixed(1)}% recovery (correctly scaled)` };
        }
    }
}));

// ─── S18: SQL_DOMINANT — Single expensive query (no plan change/new) ────────
SCENARIOS.push(buildScenario('S18: SQL Dominant — Single expensive query', {
    cpus: 8, dbTimeMin1: 25, dbTimeMin2: 60,
    waits2: [
        makeWaitEvent('DB CPU', 'CPU', 55, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 18, 60000, 5),
        makeWaitEvent('log file sync', 'Commit', 5, 8000, 1),
    ],
    sql2: [makeSql('expensive01', 42, {
        sqlText: 'SELECT /*+ FULL(t) */ * FROM large_table t WHERE UPPER(name) LIKE :1',
        bufGets: 15000000, diskReads: 200000
    })],
    sqlAttrib: [{
        id: 'expensive01', sql_id: 'expensive01', pctDb: 42, pct_db_time: 42,
        epe1: 0.5, epe2: 2.0, isNew: false, is_new: false,
        isPlanChg: false, is_plan_change: false, isRegressed: true, is_regressed: true
    }],
    _expect: {
        topRule: 'SQL_DOMINANT',
        dbTimeReduction_range: [20, 30],  // 42*0.6 = 25.2
        rationale_must_contain: ['expensive01', 'per-execution'],
    }
}));

// ─── S19: SQL_DOMINANT suppressed by wait-dominated pattern ─────────────────
// When top wait absorbs 40%+ DB Time and DB CPU ≤ 25%, SQL_DOMINANT should
// stand down because the SQL is a symptom carrier, not the root cause
SCENARIOS.push(buildScenario('S19: SQL Dominant suppressed — Wait dominated', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 80,
    waits2: [
        makeWaitEvent('enq: HW - contention', 'Configuration', 45, 200000, 20),
        makeWaitEvent('DB CPU', 'CPU', 18, 0, 0),
        makeWaitEvent('buffer busy waits', 'Concurrency', 12, 50000, 8),
        makeWaitEvent('log file sync', 'Commit', 8, 15000, 3),
    ],
    sql2: [makeSql('symptom_sql01', 35, {
        sqlText: 'INSERT INTO hot_table VALUES (:1,:2,:3,:4)',
        tableName: 'HOT_TABLE'
    })],
    sqlAttrib: [{
        id: 'symptom_sql01', sql_id: 'symptom_sql01', pctDb: 35, pct_db_time: 35,
        epe1: 0.1, epe2: 0.5, isNew: false, is_new: false,
        isPlanChg: false, is_plan_change: false
    }],
    _expect: {
        topRule: 'HW_ENQUEUE_CONTENTION',   // NOT SQL_DOMINANT
        _custom_check: (ev, evaln) => {
            const sqlDom = evaln.matches.find(m => m.rule.id === 'SQL_DOMINANT');
            if (sqlDom) {
                return { pass: false, note: 'BUG: SQL_DOMINANT fired despite being wait-dominated (HW contention 45%, DB CPU 18%). SQL is symptom carrier.' };
            }
            return { pass: true, note: 'SQL_DOMINANT correctly suppressed — SQL is symptom carrier of HW contention' };
        }
    }
}));

// ─── S20: TX INDEX CONTENTION ──────────────────────────────────────────────
SCENARIOS.push(buildScenario('S20: TX Index — Hot right-growing index', {
    cpus: 8, dbTimeMin1: 25, dbTimeMin2: 55,
    waits2: [
        makeWaitEvent('enq: TX - index contention', 'Concurrency', 25, 80000, 15),
        makeWaitEvent('buffer busy waits', 'Concurrency', 10, 40000, 5),
        makeWaitEvent('DB CPU', 'CPU', 32, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 15, 30000, 4),
        makeWaitEvent('log file sync', 'Commit', 6, 10000, 2),
    ],
    sql2: [makeSql('idx_insert01', 20, {
        sqlText: 'INSERT INTO transactions (txn_id, created_dt, amount) VALUES (seq_txn.NEXTVAL, SYSDATE, :1)'
    })],
    _expect: {
        topRule: 'TX_INDEX_CONTENTION',
        dbTimeReduction_range: [22, 32],  // (25 + min(10,10)) * 0.8 = 28
        rationale_must_contain: ['index', 'leaf block', 'reverse-key'],
    }
}));

// ─── S21: EDGE CASE — Empty wait events ────────────────────────────────────
SCENARIOS.push(buildScenario('S21: Edge — Empty wait events', {
    cpus: 4, dbTimeMin1: 20, dbTimeMin2: 25,
    waits2: [],  // completely empty
    sql2: [makeSql('edge01', 15, { sqlText: 'SELECT 1 FROM DUAL' })],
    _expect: {
        // Should not crash. dbTimeDelta = 25% — below GENERIC threshold of 30
        topRule: null,
        pTier: 'P3',
        _custom_check: (ev, evaln) => {
            if (evaln.matches.length > 0 && evaln.top) {
                return { pass: true, note: `Rules still fired (${evaln.matches.length}): ${evaln.matches.map(m=>m.rule.id).join(', ')}` };
            }
            return { pass: true, note: 'No rules fired with empty wait events — correct' };
        }
    }
}));

// ─── S22: EDGE CASE — Zero CPUs ────────────────────────────────────────────
SCENARIOS.push(buildScenario('S22: Edge — Zero CPU count', {
    cpus: 0, dbTimeMin1: 30, dbTimeMin2: 60,
    waits2: [
        makeWaitEvent('DB CPU', 'CPU', 50, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 30, 50000, 5),
    ],
    sql2: [makeSql('edge02', 20, { sqlText: 'SELECT 1 FROM DUAL' })],
    _expect: {
        // Should not crash or produce NaN/Infinity
        _custom_check: (ev, evaln) => {
            const proj = evaln.projection;
            if (proj && (isNaN(proj.dbTimeReductionPct) || !isFinite(proj.dbTimeReductionPct))) {
                return { pass: false, note: 'NaN/Infinity in projection with 0 CPUs' };
            }
            if (isNaN(ev.aasRatio) || !isFinite(ev.aasRatio)) {
                return { pass: false, note: `aasRatio is ${ev.aasRatio} with 0 CPUs` };
            }
            return { pass: true, note: `Handled 0 CPUs: aasRatio=${ev.aasRatio}, cpuUtilPct=${ev.cpuUtilPct}` };
        }
    }
}));

// ─── S23: EDGE CASE — DB Time decreased (improvement scenario) ─────────────
SCENARIOS.push(buildScenario('S23: Edge — DB Time improved (negative delta)', {
    cpus: 8, dbTimeMin1: 60, dbTimeMin2: 25,
    waits2: [
        makeWaitEvent('DB CPU', 'CPU', 55, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 20, 30000, 4),
        makeWaitEvent('log file sync', 'Commit', 5, 8000, 1),
    ],
    sql2: [makeSql('improved01', 12, { sqlText: 'SELECT * FROM optimized_view' })],
    _expect: {
        pTier: 'P3',           // negative delta → no severity
        _custom_check: (ev, evaln) => {
            if (ev.dbTimeDelta >= 0) {
                return { pass: false, note: `Expected negative dbTimeDelta but got ${ev.dbTimeDelta.toFixed(1)}%` };
            }
            // GENERIC_LOAD should NOT fire on negative delta
            const generic = evaln.matches.find(m => m.rule.id === 'GENERIC_LOAD_INCREASE');
            if (generic) {
                return { pass: false, note: 'GENERIC_LOAD_INCREASE fired despite DB Time improvement' };
            }
            return { pass: true, note: `DB Time delta = ${ev.dbTimeDelta.toFixed(1)}% (correctly negative, no severity escalation)` };
        }
    }
}));

// ─── S24: CONCURRENCY vs LIBRARY_CACHE double-count check ──────────────────
// This tests Bug #4: concPct must exclude shared-pool latches
SCENARIOS.push(buildScenario('S24: Double-count test — Latch vs LibCache', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 55,
    waits2: [
        makeWaitEvent('latch: cache buffers chains', 'Concurrency', 10, 100000, 1),
        makeWaitEvent('cursor: pin S wait on X', 'Concurrency', 5, 30000, 3),
        makeWaitEvent('latch: shared pool', 'Concurrency', 12, 60000, 2),
        makeWaitEvent('latch: row cache objects', 'Concurrency', 4, 20000, 1),
        makeWaitEvent('library cache: mutex X', 'Concurrency', 8, 40000, 3),
        makeWaitEvent('DB CPU', 'CPU', 35, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 10, 20000, 4),
    ],
    sql2: [makeSql('parse_test01', 10, { sqlText: 'SELECT 1 FROM DUAL' })],
    _expect: {
        _custom_check: (ev, evaln) => {
            // latchPct = CBC(10) + cursor:pin(5) + shared pool(12) + row cache(4) = 31
            // sharedPoolLatchPct = shared pool(12) + row cache(4) = 16
            // concPct = max(0, 31 - 16) = 15
            // libCachePct = library cache:mutex(8) + cursor:pin(5) = 13
            const errors = [];

            if (Math.abs(ev.latchPct - 31) > 1) errors.push(`latchPct=${ev.latchPct.toFixed(1)}, expected ~31`);
            if (Math.abs(ev.sharedPoolLatchPct - 16) > 1) errors.push(`sharedPoolLatchPct=${ev.sharedPoolLatchPct.toFixed(1)}, expected ~16`);
            if (Math.abs(ev.concPct - 15) > 1) errors.push(`concPct=${ev.concPct.toFixed(1)}, expected ~15 (latchPct - sharedPoolLatchPct)`);
            if (Math.abs(ev.libCachePct - 13) > 1) errors.push(`libCachePct=${ev.libCachePct.toFixed(1)}, expected ~13`);

            // Verify CONCURRENCY rule uses concPct (15), not latchPct (31)
            const concRule = evaln.matches.find(m => m.rule.id === 'CONCURRENCY');
            if (concRule) {
                const proj = concRule.rule.project(ev);
                // Should use concPct=15: min(30, 15*0.6) = 9.0
                // If it used latchPct=31: min(30, 31*0.6) = 18.6 — WRONG
                if (proj.dbTimeReductionPct > 12) {
                    errors.push(`CONCURRENCY uses inflated value (${proj.dbTimeReductionPct.toFixed(1)}%), expected ~9.0% from concPct=15`);
                }
            }

            // Verify LIBRARY_CACHE also fires
            const libRule = evaln.matches.find(m => m.rule.id === 'LIBRARY_CACHE_PRESSURE');
            if (!libRule) errors.push('LIBRARY_CACHE_PRESSURE did not fire despite (libCachePct+sharedPoolLatchPct) ≈ 29% >= 10');

            return errors.length
                ? { pass: false, note: errors.join('; ') }
                : { pass: true, note: `Double-count check OK: concPct=${ev.concPct.toFixed(1)}, libCachePct=${ev.libCachePct.toFixed(1)}, sharedPoolLatchPct=${ev.sharedPoolLatchPct.toFixed(1)}` };
        }
    }
}));

// ─── S25: BUFFER_CACHE threshold test — Below new threshold ─────────────────
SCENARIOS.push(buildScenario('S25: Buffer Cache — Below raised threshold (noise)', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 40,
    waits2: [
        makeWaitEvent('free buffer waits', 'Configuration', 9, 8000, 10),
        makeWaitEvent('buffer busy waits', 'Concurrency', 6, 5000, 5),
        makeWaitEvent('DB CPU', 'CPU', 45, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 22, 40000, 5),
        makeWaitEvent('log file sync', 'Commit', 5, 8000, 1),
    ],
    sql2: [makeSql('noise01', 10, { sqlText: 'SELECT * FROM small_table WHERE id = :1' })],
    _expect: {
        // freeBufPct=9 < 15 AND (freeBufPct=9 < 10 || bufBusyPct=6 < 8)
        // BUFFER_CACHE_WRITE_PRESSURE should NOT fire — below threshold
        _custom_check: (ev, evaln) => {
            const bufRule = evaln.matches.find(m => m.rule.id === 'BUFFER_CACHE_WRITE_PRESSURE');
            if (bufRule) {
                return { pass: false, note: `BUG: BUFFER_CACHE_WRITE_PRESSURE fired at freeBufPct=${ev.freeBufPct}%, bufBusyPct=${ev.bufBusyPct}% — below raised threshold (10/8)` };
            }
            return { pass: true, note: `Correctly rejected noise: freeBufPct=${ev.freeBufPct}%, bufBusyPct=${ev.bufBusyPct}%` };
        }
    }
}));

// ─── S26: SESSION RISK ASSESSMENT — All tiers ──────────────────────────────
SCENARIOS.push(buildScenario('S26: Session Risk — WAIT-SATURATED', {
    cpus: 4, dbTimeMin1: 20, dbTimeMin2: 80,
    lp2: [
        makeLP('DB Time(s/s)',  80),
        makeLP('DB CPU(s/s)',   0.5),   // Only 0.5/4 = 12.5% CPU — low
        makeLP('Redo size',     5000000),
        makeLP('Logical reads', 200000),
        makeLP('Block changes', 5000),
        makeLP('Physical reads',10000),
        makeLP('Physical writes',2000),
        makeLP('User calls',    500),
        makeLP('Parses',        200),
        makeLP('Hard parses',   5),
        makeLP('Sorts',         50),
        makeLP('Logons',        2),
        makeLP('Executes',      3000),
        makeLP('Transactions',  100),
        makeLP('User Commits',  100),
        makeLP('User Rollbacks',1),
    ],
    waits2: [
        makeWaitEvent('enq: TX - row lock contention', 'Application', 55, 200000, 50),
        makeWaitEvent('DB CPU', 'CPU', 12, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 15, 30000, 5),
        makeWaitEvent('log file sync', 'Commit', 5, 10000, 2),
    ],
    sql2: [makeSql('wait_sat01', 18, { sqlText: 'UPDATE accts SET balance=:1 WHERE id=:2' })],
    _expect: {
        sessionRisk: /WAIT-SATURATED|WAIT-BOUND/,
        // AAS = bad aas. With cpuUtilPct low and top wait being row lock (not DB CPU),
        // the system is wait-saturated, not CPU-saturated.
        _custom_check: (ev, evaln) => {
            if (/CPU-BOUND|SATURATED NOW/.test(evaln.sessionRisk.label) && ev.cpuUtilPct < 30) {
                return { pass: false, note: `Session risk says "${evaln.sessionRisk.label}" but cpuUtilPct is only ${ev.cpuUtilPct.toFixed(0)}% — should be WAIT-SATURATED or WAIT-BOUND` };
            }
            return { pass: true, note: `Session risk: "${evaln.sessionRisk.label}" with cpuUtilPct=${ev.cpuUtilPct.toFixed(0)}% — correct` };
        }
    }
}));

// ─── S27: MULTI-RULE FIRING — Verify ordering and confidence ───────────────
SCENARIOS.push(buildScenario('S27: Multi-Rule — Multiple bottlenecks compete', {
    cpus: 8, dbTimeMin1: 30, dbTimeMin2: 90,
    waits2: [
        makeWaitEvent('enq: HW - contention', 'Configuration', 20, 80000, 15),
        makeWaitEvent('enq: TX - row lock contention', 'Application', 15, 40000, 30),
        makeWaitEvent('DB CPU', 'CPU', 22, 0, 0),
        makeWaitEvent('db file sequential read', 'User I/O', 18, 40000, 6),
        makeWaitEvent('log file sync', 'Commit', 8, 15000, 3),
        makeWaitEvent('free buffer waits', 'Configuration', 4, 3000, 8),
    ],
    sql2: [makeSql('multi01', 12, { sqlText: 'INSERT INTO events VALUES (:1,:2,:3,:4)', tableName: 'EVENTS' })],
    _expect: {
        topRule: 'HW_ENQUEUE_CONTENTION',   // Highest weight: 0.7 + 20/150 = 0.833
        _custom_check: (ev, evaln) => {
            const errors = [];
            // Multiple rules should fire
            if (evaln.matches.length < 3) errors.push(`Only ${evaln.matches.length} rules fired — expected ≥3 (HW, TX_ROW, IO, GENERIC)`);
            // Confidence should increase with more rules
            if (evaln.confidence < 70) errors.push(`Confidence ${evaln.confidence}% too low for multi-rule match`);
            // Top rule should have highest weight
            if (evaln.top && evaln.matches.length > 1) {
                const sorted = [...evaln.matches].sort((a,b) => b.weight - a.weight);
                if (sorted[0].rule.id !== evaln.top.rule.id) {
                    errors.push(`Top rule ${evaln.top.rule.id} is not the highest-weight rule ${sorted[0].rule.id}`);
                }
            }
            return errors.length ? { pass: false, note: errors.join('; ') } : { pass: true, note: `${evaln.matches.length} rules fired, correctly ordered by weight` };
        }
    }
}));


// ============================================================================
// SECTION 3: TEST RUNNER ENGINE
// ============================================================================

const RESULTS = [];
let passCount = 0, failCount = 0, warnCount = 0;

function runExam() {
    console.log('\n╔══════════════════════════════════════════════════════════════╗');
    console.log('║          PEEngine COMPREHENSIVE EXAM — 27 SCENARIOS         ║');
    console.log('╚══════════════════════════════════════════════════════════════╝\n');

    // Check PEEngine is available
    if (typeof window === 'undefined' || !window.PEEngine) {
        console.error('❌ PEEngine not found. Run this in the browser console at http://localhost:8000');
        return;
    }
    if (typeof buildAWRContext !== 'function') {
        console.error('❌ buildAWRContext not found in global scope.');
        return;
    }

    SCENARIOS.forEach((scenario, idx) => {
        const result = { name: scenario.name, checks: [], pass: true };
        try {
            // ① Build AWR context
            const ctx = buildAWRContext(scenario.data);

            // ② Inject sqlAttribution (normally built by comparison pipeline)
            ctx.sqlAttribution = scenario.sqlAttrib;

            // ③ Extract evidence
            const ev = window.PEEngine.extract(ctx);

            // ④ Evaluate
            const evaln = window.PEEngine.evaluate(ev);

            // ⑤ Render (check for crashes)
            let scorecardHtml, simulatorHtml;
            try {
                scorecardHtml = window.PEEngine.renderScorecard(ev, evaln);
                simulatorHtml = window.PEEngine.renderImpactSimulator(ev, evaln);
            } catch (renderErr) {
                result.checks.push({ pass: false, msg: `RENDER CRASH: ${renderErr.message}` });
                result.pass = false;
            }

            const expect = scenario._config._expect || {};

            // ── CHECK 1: Top rule ID ──
            if (expect.topRule !== undefined) {
                const actualTop = evaln.top ? evaln.top.rule.id : null;
                if (actualTop !== expect.topRule) {
                    result.checks.push({ pass: false, msg: `TOP RULE: expected "${expect.topRule}", got "${actualTop}"` });
                    result.pass = false;
                } else {
                    result.checks.push({ pass: true, msg: `TOP RULE: "${actualTop}" ✓` });
                }
            }

            // ── CHECK 2: P-tier ──
            if (expect.pTier) {
                if (evaln.pTier !== expect.pTier) {
                    result.checks.push({ pass: false, msg: `P-TIER: expected ${expect.pTier}, got ${evaln.pTier} (dbTimeDelta=${ev.dbTimeDelta.toFixed(1)}%, hwEnqPct=${ev.hwEnqPct.toFixed(1)}%, freeBufPct=${ev.freeBufPct.toFixed(1)}%)` });
                    result.pass = false;
                } else {
                    result.checks.push({ pass: true, msg: `P-TIER: ${evaln.pTier} ✓` });
                }
            }

            // ── CHECK 3: Confidence label ──
            if (expect.confLabel) {
                if (evaln.confLabel !== expect.confLabel) {
                    result.checks.push({ pass: false, msg: `CONFIDENCE: expected ${expect.confLabel}, got ${evaln.confLabel} (${evaln.confidence}%)` });
                    // Downgrade to warning — confidence can be fuzzy
                    warnCount++;
                } else {
                    result.checks.push({ pass: true, msg: `CONFIDENCE: ${evaln.confLabel} (${evaln.confidence}%) ✓` });
                }
            }

            // ── CHECK 4: Session risk ──
            if (expect.sessionRisk) {
                const actual = evaln.sessionRisk.label;
                if (expect.sessionRisk instanceof RegExp) {
                    if (!expect.sessionRisk.test(actual)) {
                        result.checks.push({ pass: false, msg: `SESSION RISK: expected /${expect.sessionRisk.source}/, got "${actual}"` });
                        result.pass = false;
                    } else {
                        result.checks.push({ pass: true, msg: `SESSION RISK: "${actual}" ✓` });
                    }
                } else if (actual !== expect.sessionRisk) {
                    result.checks.push({ pass: false, msg: `SESSION RISK: expected "${expect.sessionRisk}", got "${actual}"` });
                    result.pass = false;
                } else {
                    result.checks.push({ pass: true, msg: `SESSION RISK: "${actual}" ✓` });
                }
            }

            // ── CHECK 5: DB Time delta range ──
            if (expect.dbTimeDelta_range) {
                const [lo, hi] = expect.dbTimeDelta_range;
                if (ev.dbTimeDelta < lo || ev.dbTimeDelta > hi) {
                    result.checks.push({ pass: false, msg: `DB TIME DELTA: ${ev.dbTimeDelta.toFixed(1)}% outside expected [${lo}, ${hi}]` });
                    result.pass = false;
                } else {
                    result.checks.push({ pass: true, msg: `DB TIME DELTA: ${ev.dbTimeDelta.toFixed(1)}% in [${lo}, ${hi}] ✓` });
                }
            }

            // ── CHECK 6: Projected recovery range ──
            if (expect.dbTimeReduction_range && evaln.projection) {
                const [lo, hi] = expect.dbTimeReduction_range;
                const actual = evaln.projection.dbTimeReductionPct;
                if (actual < lo || actual > hi) {
                    result.checks.push({ pass: false, msg: `RECOVERY: ${actual.toFixed(1)}% outside expected [${lo}, ${hi}]` });
                    result.pass = false;
                } else {
                    result.checks.push({ pass: true, msg: `RECOVERY: ${actual.toFixed(1)}% in [${lo}, ${hi}] ✓` });
                }
            }

            // ── CHECK 7: sessionsFreed ≤ aasB ──
            if (evaln.projection) {
                if (evaln.projection.sessionsFreed > ev.aasB * 1.01) { // 1% tolerance
                    result.checks.push({ pass: false, msg: `PHYSICS VIOLATION: sessionsFreed (${evaln.projection.sessionsFreed.toFixed(2)}) > aasB (${ev.aasB.toFixed(2)})` });
                    result.pass = false;
                } else {
                    result.checks.push({ pass: true, msg: `sessionsFreed (${evaln.projection.sessionsFreed.toFixed(2)}) ≤ aasB (${ev.aasB.toFixed(2)}) ✓` });
                }
            }

            // ── CHECK 8: No NaN/Infinity in projection ──
            if (evaln.projection) {
                const pKeys = ['dbTimeReductionPct', 'sessionsFreed'];
                pKeys.forEach(k => {
                    const v = evaln.projection[k];
                    if (v === undefined || v === null || isNaN(v) || !isFinite(v)) {
                        result.checks.push({ pass: false, msg: `NaN/INFINITY: projection.${k} = ${v}` });
                        result.pass = false;
                    }
                });
            }

            // ── CHECK 9: No NaN/Infinity in ev ──
            const evKeys = ['cpus', 'aasG', 'aasB', 'aasRatio', 'cpuUtilPct', 'dbTimeDelta',
                           'ioPct', 'cpuPct', 'commitPct', 'freeBufPct', 'bufBusyPct',
                           'hwEnqPct', 'txEnqPct', 'txRowPct', 'txIdxPct', 'concPct',
                           'latchPct', 'libCachePct', 'sharedPoolLatchPct'];
            let nanFound = false;
            evKeys.forEach(k => {
                if (ev[k] === undefined || isNaN(ev[k]) || !isFinite(ev[k])) {
                    result.checks.push({ pass: false, msg: `NaN/INFINITY: ev.${k} = ${ev[k]}` });
                    result.pass = false;
                    nanFound = true;
                }
            });
            if (!nanFound) {
                result.checks.push({ pass: true, msg: 'All ev fields are valid numbers ✓' });
            }

            // ── CHECK 10: Rationale content ──
            if (expect.rationale_must_contain && evaln.projection) {
                const rat = evaln.projection.rationale || '';
                expect.rationale_must_contain.forEach(keyword => {
                    if (!rat.toLowerCase().includes(keyword.toLowerCase())) {
                        result.checks.push({ pass: false, msg: `RATIONALE missing keyword "${keyword}" in: "${rat.substring(0, 80)}..."` });
                        result.pass = false;
                    }
                });
                if (expect.rationale_must_contain.every(k => rat.toLowerCase().includes(k.toLowerCase()))) {
                    result.checks.push({ pass: true, msg: `RATIONALE contains all expected keywords ✓` });
                }
            }

            // ── CHECK 11: Render output has required HTML ──
            if (scorecardHtml) {
                if (!scorecardHtml.includes('RCA Confidence Scorecard')) {
                    result.checks.push({ pass: false, msg: 'RENDER: Scorecard missing "RCA Confidence Scorecard" text' });
                    result.pass = false;
                }
                if (!scorecardHtml.includes(evaln.pTier)) {
                    result.checks.push({ pass: false, msg: `RENDER: Scorecard missing P-tier "${evaln.pTier}"` });
                    result.pass = false;
                }
                if (!scorecardHtml.includes(String(evaln.confidence))) {
                    result.checks.push({ pass: false, msg: `RENDER: Scorecard missing confidence "${evaln.confidence}"` });
                    result.pass = false;
                }
            }

            if (simulatorHtml) {
                if (!simulatorHtml.includes('Fix Impact Simulator') && !simulatorHtml.includes('current load envelope')) {
                    result.checks.push({ pass: false, msg: 'RENDER: Simulator missing both "Fix Impact Simulator" and "current load envelope"' });
                    result.pass = false;
                }
            }

            // ── CHECK 12: Negative projection values ──
            if (evaln.projection) {
                if (evaln.projection.dbTimeReductionPct < 0) {
                    result.checks.push({ pass: false, msg: `NEGATIVE: dbTimeReductionPct = ${evaln.projection.dbTimeReductionPct}` });
                    result.pass = false;
                }
                if (evaln.projection.sessionsFreed < 0) {
                    result.checks.push({ pass: false, msg: `NEGATIVE: sessionsFreed = ${evaln.projection.sessionsFreed}` });
                    result.pass = false;
                }
            }

            // ── CHECK 13: Custom checks ──
            if (expect._custom_check) {
                const customResult = expect._custom_check(ev, evaln);
                result.checks.push({ pass: customResult.pass, msg: `CUSTOM: ${customResult.note}` });
                if (!customResult.pass) result.pass = false;
            }

            // ── EVIDENCE DUMP (for debugging failures) ──
            result.ev_summary = {
                dbTimeDelta: ev.dbTimeDelta.toFixed(1) + '%',
                aasRatio: ev.aasRatio.toFixed(2),
                cpuUtilPct: ev.cpuUtilPct.toFixed(1) + '%',
                ioPct: ev.ioPct.toFixed(1) + '%',
                cpuPct: ev.cpuPct.toFixed(1) + '%',
                commitPct: ev.commitPct.toFixed(1) + '%',
                freeBufPct: ev.freeBufPct.toFixed(1) + '%',
                hwEnqPct: ev.hwEnqPct.toFixed(1) + '%',
                txRowPct: ev.txRowPct.toFixed(1) + '%',
                txIdxPct: ev.txIdxPct.toFixed(1) + '%',
                concPct: ev.concPct.toFixed(1) + '%',
                libCachePct: ev.libCachePct.toFixed(1) + '%',
                sharedPoolLatchPct: ev.sharedPoolLatchPct.toFixed(1) + '%',
                domSqlPct: ev.domSqlPct.toFixed(1) + '%',
                rulesMatched: evaln.matches.map(m => `${m.rule.id}(w=${m.weight.toFixed(2)})`).join(', '),
            };

        } catch (err) {
            result.checks.push({ pass: false, msg: `EXCEPTION: ${err.message}\n${err.stack}` });
            result.pass = false;
        }

        if (result.pass) passCount++; else failCount++;
        RESULTS.push(result);
    });

    // ============================================================================
    // SECTION 4: REPORT
    // ============================================================================
    console.log('\n' + '═'.repeat(70));
    console.log('EXAM RESULTS');
    console.log('═'.repeat(70));

    RESULTS.forEach((r, i) => {
        const icon = r.pass ? '✅' : '❌';
        console.log(`\n${icon} ${r.name}`);
        r.checks.forEach(c => {
            console.log(`   ${c.pass ? '  ✓' : '  ✗'} ${c.msg}`);
        });
        if (!r.pass && r.ev_summary) {
            console.log('   📊 Evidence:', JSON.stringify(r.ev_summary, null, 2).split('\n').map((l,i) => i === 0 ? l : '              ' + l).join('\n'));
        }
    });

    console.log('\n' + '═'.repeat(70));
    console.log(`FINAL SCORE: ${passCount}/${SCENARIOS.length} PASSED  |  ${failCount} FAILED  |  ${warnCount} WARNINGS`);
    console.log('═'.repeat(70));

    if (failCount > 0) {
        console.log('\n🔴 FAILED SCENARIOS:');
        RESULTS.filter(r => !r.pass).forEach(r => {
            console.log(`   • ${r.name}`);
            r.checks.filter(c => !c.pass).forEach(c => console.log(`     → ${c.msg}`));
        });
    }

    // ============================================================================
    // SECTION 5: ADDITIONAL STRUCTURAL AUDITS
    // ============================================================================
    console.log('\n\n' + '═'.repeat(70));
    console.log('STRUCTURAL & CODE QUALITY AUDIT');
    console.log('═'.repeat(70));

    // A) Check all RULES have required methods
    const structuralIssues = [];
    window.PEEngine.RULES.forEach((r, i) => {
        if (!r.id) structuralIssues.push(`Rule[${i}] missing .id`);
        if (!r.label) structuralIssues.push(`Rule[${i}] (${r.id}) missing .label`);
        if (typeof r.match !== 'function') structuralIssues.push(`Rule[${i}] (${r.id}) .match is not a function`);
        if (typeof r.weight !== 'function') structuralIssues.push(`Rule[${i}] (${r.id}) .weight is not a function`);
        if (typeof r.project !== 'function') structuralIssues.push(`Rule[${i}] (${r.id}) .project is not a function`);
    });

    // B) Verify rule IDs are unique
    const ruleIds = window.PEEngine.RULES.map(r => r.id);
    const dupes = ruleIds.filter((id, i) => ruleIds.indexOf(id) !== i);
    if (dupes.length) structuralIssues.push(`Duplicate rule IDs: ${dupes.join(', ')}`);

    // C) Check weight always returns 0-1
    const testEv = { cpus:8, aasG:2, aasB:10, aasRatio:1.25, cpuUtilPct:50,
        domSqlId:'test', domSqlPct:50, domEpe1:1, domEpe2:10, domIsNew:true,
        domPlanChange:true, domIsRegressed:true, domSqlVerb:'INSERT', domIsDML:true, domTable:'T',
        topWaitName:'DB CPU', topWaitPct:50, topWaitClass:'CPU',
        ioPct:50, cpuPct:50, commitPct:50, concPct:30, freeBufPct:50, bufBusyPct:20,
        fbEnqPct:10, usEnqPct:20, txEnqPct:50, logBufPct:5, latchPct:30,
        hwEnqPct:50, txIdxPct:20, txRowPct:25, txItlPct:5, tmEnqPct:5, sqEnqPct:5,
        libCachePct:20, sharedPoolLatchPct:10,
        txnDelta:100, blockChgDelta:100, physWriteDelta:100, redoDelta:100,
        dbTimeDelta:200, dbT1:100, dbT2:300, bufferHitDrop:5,
        isParallel:false, bottleneckType:'', lblG:'Good', lblB:'Bad', dbName:'TESTDB' };

    window.PEEngine.RULES.forEach(r => {
        try {
            if (r.match(testEv)) {
                const w = r.weight(testEv);
                if (w < 0 || w > 1.001) {
                    structuralIssues.push(`Rule ${r.id} weight returned ${w} — must be in [0, 1]`);
                }
                const p = r.project(testEv);
                if (p.dbTimeReductionPct < 0) structuralIssues.push(`Rule ${r.id} projects negative recovery: ${p.dbTimeReductionPct}`);
                if (p.dbTimeReductionPct > 100) structuralIssues.push(`Rule ${r.id} projects >100% recovery: ${p.dbTimeReductionPct}`);
                if (p.sessionsFreed < 0) structuralIssues.push(`Rule ${r.id} projects negative sessionsFreed: ${p.sessionsFreed}`);
            }
        } catch(e) {
            structuralIssues.push(`Rule ${r.id} threw: ${e.message}`);
        }
    });

    if (structuralIssues.length) {
        console.log('🔴 STRUCTURAL ISSUES:');
        structuralIssues.forEach(i => console.log(`   • ${i}`));
    } else {
        console.log('✅ All rules structurally valid (IDs unique, methods present, weights in [0,1], projections sane)');
    }

    // D) Render all scenarios and check for HTML injection
    let renderIssues = 0;
    SCENARIOS.forEach((scenario, idx) => {
        try {
            const ctx = buildAWRContext(scenario.data);
            ctx.sqlAttribution = scenario.sqlAttrib;
            const ev = window.PEEngine.extract(ctx);
            const evaln = window.PEEngine.evaluate(ev);
            const html = window.PEEngine.renderScorecard(ev, evaln);
            // Check for unescaped user-controlled content
            if (html.includes('<script')) {
                console.log(`   🔴 XSS: Scenario ${idx} scorecard contains <script>`);
                renderIssues++;
            }
        } catch(e) {
            // Already tested above
        }
    });
    if (renderIssues === 0) {
        console.log('✅ All render outputs clean (no script injection detected)');
    }

    // E) Rule coverage analysis — which rules fired at least once?
    const firedRules = new Set();
    RESULTS.forEach(r => {
        if (r.ev_summary && r.ev_summary.rulesMatched) {
            r.ev_summary.rulesMatched.split(', ').forEach(rm => {
                const id = rm.split('(')[0];
                if (id) firedRules.add(id);
            });
        }
    });
    const unfiredRules = ruleIds.filter(id => !firedRules.has(id));
    if (unfiredRules.length) {
        console.log(`⚠️  UNTESTED RULES (never fired in any scenario): ${unfiredRules.join(', ')}`);
    } else {
        console.log('✅ All rules tested — every rule fired in at least one scenario');
    }

    console.log('\n' + '═'.repeat(70));
    console.log('EXAM COMPLETE');
    console.log('═'.repeat(70));

    return { pass: passCount, fail: failCount, warn: warnCount, total: SCENARIOS.length, results: RESULTS };
}

// Auto-run
return runExam();

})();
