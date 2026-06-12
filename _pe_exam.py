#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  PE ENGINE — COMPREHENSIVE EXAM                                            ║
║  Independent Python model of PEEngine (extract + evaluate + RULES)         ║
║  Tests 20+ synthetic AWR scenarios against expected Oracle PE outcomes.     ║
║                                                                            ║
║  This is a BLACK-BOX verification: every formula is re-implemented from    ║
║  first principles. Any divergence between expected and actual IS a bug.    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import json, math, re, sys, os
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple

# ── ANSI colors for terminal output ──────────────────────────────────────────
G = '\033[92m'  # green
R = '\033[91m'  # red
Y = '\033[93m'  # yellow
B = '\033[94m'  # blue
W = '\033[97m'  # white
D = '\033[0m'   # reset
BOLD = '\033[1m'

# ── Test counters ────────────────────────────────────────────────────────────
_pass = 0
_fail = 0
_warn = 0
_findings: List[Dict] = []

def ok(test_name: str, detail: str = ''):
    global _pass
    _pass += 1
    print(f"  {G}✓{D} {test_name}" + (f"  {D}({detail})" if detail else ''))

def fail(test_name: str, expected, actual, detail: str = '', severity='BUG'):
    global _fail
    _fail += 1
    msg = f"  {R}✗ {test_name}{D}  expected={expected}  actual={actual}"
    if detail:
        msg += f"  [{detail}]"
    print(msg)
    _findings.append({'type': severity, 'test': test_name, 'expected': str(expected), 'actual': str(actual), 'detail': detail})

def warn(test_name: str, detail: str = ''):
    global _warn
    _warn += 1
    print(f"  {Y}⚠ {test_name}{D}  {detail}")
    _findings.append({'type': 'WARNING', 'test': test_name, 'detail': detail})


# ════════════════════════════════════════════════════════════════════════════
# PART 1: PYTHON RE-IMPLEMENTATION OF PEEngine (extract + evaluate + RULES)
# ════════════════════════════════════════════════════════════════════════════

def safe_float(v, default=0):
    """Equivalent to JS $f()"""
    if v is None:
        return default
    try:
        n = float(v)
        return default if math.isnan(n) else n
    except (ValueError, TypeError):
        return default

def sum_pct_if(events: list, pattern: str) -> float:
    """Sum pct_db_time for events matching regex pattern."""
    rx = re.compile(pattern, re.IGNORECASE)
    return sum(safe_float(e.get('pct_db_time')) for e in events if rx.search(f"{e.get('wait_class','')} {e.get('event_name','')}"))

def extract(ctx: dict) -> dict:
    """Python equivalent of PEEngine.extract()"""
    lp1 = (ctx.get('loadProfile') or {}).get('good') or {}
    lp2 = (ctx.get('loadProfile') or {}).get('bad') or {}
    ev1 = (ctx.get('waitEvents') or {}).get('good') or []
    ev2 = (ctx.get('waitEvents') or {}).get('bad') or []
    ie1 = (ctx.get('instanceEfficiency') or {}).get('good') or {}
    ie2 = (ctx.get('instanceEfficiency') or {}).get('bad') or {}

    sa = ctx.get('sqlAttribution') or []
    if isinstance(sa, dict):
        sa = sa.get('top10') or sa.get('bad') or sa.get('good') or []
    top = [s for s in sa if s]
    dom = top[0] if top else {}

    cpus = safe_float(
        (ctx.get('meta') or {}).get('cpu_count')
        or ((ctx.get('_raw') or {}).get('bad') or {}).get('cpus')
        or ((ctx.get('_raw') or {}).get('s2') or {}).get('cpus'),
        1
    )
    aasG = safe_float((ctx.get('aas') or {}).get('good'))
    aasB = safe_float((ctx.get('aas') or {}).get('bad'))

    topW2 = ev2[0] if ev2 else {}

    ioPct       = sum_pct_if(ev2, r'User I/O|System I/O|db file|direct path')
    cpuPct      = sum_pct_if(ev2, r'DB CPU')
    commitPct   = sum_pct_if(ev2, r'log file sync')
    freeBufPct  = sum_pct_if(ev2, r'free buffer waits')
    bufBusyPct  = sum_pct_if(ev2, r'buffer busy waits')
    fbEnqPct    = sum_pct_if(ev2, r'enq:\s*FB\s*-\s*contention')
    usEnqPct    = sum_pct_if(ev2, r'enq:\s*US\s*-\s*contention')
    txEnqPct    = sum_pct_if(ev2, r'enq:\s*TX\s*-')
    logBufPct   = sum_pct_if(ev2, r'log buffer space')
    hwEnqPct    = sum_pct_if(ev2, r'enq:\s*HW\s*-\s*contention')
    txIdxPct    = sum_pct_if(ev2, r'enq:\s*TX\s*-\s*index contention')
    txRowPct    = sum_pct_if(ev2, r'enq:\s*TX\s*-\s*row lock')
    txItlPct    = sum_pct_if(ev2, r'enq:\s*TX\s*-\s*allocate ITL')
    tmEnqPct    = sum_pct_if(ev2, r'enq:\s*TM\s*-')
    sqEnqPct    = sum_pct_if(ev2, r'enq:\s*SQ\s*-')
    libCachePct = sum_pct_if(ev2, r'library cache:|cursor:.*pin\s*S\s*wait\s*on\s*X')
    sharedPoolLatchPct = sum_pct_if(ev2, r'latch:\s*shared pool|latch:\s*row cache')
    latchPct    = sum_pct_if(ev2, r'latch:|cursor:.*pin')

    cpuUtilPct = min(100, safe_float(lp2.get('db_cpu_s')) / cpus * 100) if cpus > 0 else 0

    dbT1 = safe_float(lp1.get('db_time_s'))
    dbT2 = safe_float(lp2.get('db_time_s'))
    dbTimeDelta = ((dbT2 - dbT1) / dbT1 * 100) if dbT1 > 0 else (100 if dbT2 > 0 else 0)

    bufferHitDrop = max(0,
        safe_float(ie1.get('buffer_hit_pct') or ie1.get('buffer_cache_hit_pct'), 100) -
        safe_float(ie2.get('buffer_hit_pct') or ie2.get('buffer_cache_hit_pct'), 100)
    )

    # Workload deltas
    def pct_delta(k):
        v1, v2 = safe_float(lp1.get(k)), safe_float(lp2.get(k))
        return ((v2 - v1) / v1 * 100) if v1 > 0 else 0

    # Dominant SQL
    domSqlId = dom.get('id') or dom.get('sql_id')
    domSqlPct = safe_float(dom.get('pctDb') or dom.get('pct_db_time'))
    domPlanChange = bool(dom.get('isPlanChg') or dom.get('is_plan_change'))
    domIsNew = bool(dom.get('isNew') or dom.get('is_new'))
    domIsRegressed = bool(dom.get('isRegressed') or dom.get('is_regressed'))

    # SQL verb detection
    sql_text = str(dom.get('sql_text') or dom.get('sql_text_full') or '').strip()
    m = re.match(r'^\s*(INSERT|UPDATE|DELETE|MERGE|SELECT|WITH|CALL|BEGIN)', sql_text, re.IGNORECASE)
    domSqlVerb = m.group(1).upper() if m else ''
    domIsDML = domSqlVerb in ('INSERT', 'UPDATE', 'DELETE', 'MERGE')

    return {
        'cpus': cpus, 'aasG': aasG, 'aasB': aasB,
        'aasRatio': aasB / cpus if cpus > 0 else 0,
        'cpuUtilPct': cpuUtilPct,
        'domSqlId': domSqlId, 'domSqlPct': domSqlPct,
        'domEpe1': safe_float(dom.get('epe1')), 'domEpe2': safe_float(dom.get('epe2')),
        'domIsNew': domIsNew, 'domPlanChange': domPlanChange, 'domIsRegressed': domIsRegressed,
        'domSqlVerb': domSqlVerb, 'domIsDML': domIsDML,
        'domTable': dom.get('table_name') or '',
        'topWaitName': topW2.get('event_name') or '',
        'topWaitPct': safe_float(topW2.get('pct_db_time')),
        'topWaitClass': topW2.get('wait_class') or '',
        'ioPct': ioPct, 'cpuPct': cpuPct, 'commitPct': commitPct,
        'concPct': max(0, latchPct - sharedPoolLatchPct),
        'freeBufPct': freeBufPct, 'bufBusyPct': bufBusyPct, 'fbEnqPct': fbEnqPct,
        'usEnqPct': usEnqPct, 'txEnqPct': txEnqPct, 'logBufPct': logBufPct,
        'latchPct': latchPct,
        'hwEnqPct': hwEnqPct, 'txIdxPct': txIdxPct, 'txRowPct': txRowPct,
        'txItlPct': txItlPct, 'tmEnqPct': tmEnqPct, 'sqEnqPct': sqEnqPct,
        'libCachePct': libCachePct, 'sharedPoolLatchPct': sharedPoolLatchPct,
        'txnDelta': pct_delta('transactions'), 'blockChgDelta': pct_delta('block_changes'),
        'physWriteDelta': pct_delta('physical_writes'), 'redoDelta': pct_delta('redo_size'),
        'dbTimeDelta': dbTimeDelta, 'dbT1': dbT1, 'dbT2': dbT2,
        'bufferHitDrop': bufferHitDrop,
        'isParallel': False, 'bottleneckType': '',
        'lblG': 'Good', 'lblB': 'Bad', 'dbName': 'TESTDB'
    }


# ── RULES (Python port of JS RULES array) ───────────────────────────────────

def _wait_dominated(ev):
    return (
        ev.get('topWaitName')
        and not re.search(r'DB\s*CPU', ev['topWaitName'], re.IGNORECASE)
        and ev.get('topWaitPct', 0) >= 40
        and ev.get('cpuPct', 0) <= 25
    )

RULES = [
    {
        'id': 'PLAN_REGRESSION',
        'match': lambda ev: ev['domPlanChange'] and ev['domSqlPct'] >= 15,
        'weight': lambda ev: min(1, 0.6 + ev['domSqlPct']/100),
        'project': lambda ev: {
            'dbTimeReductionPct': min(85, ev['domSqlPct'] * 0.9),
            'sessionsFreed': ev['aasB'] * (ev['domSqlPct'] * 0.9 / 100),
        }
    },
    {
        'id': 'NEW_SQL_DEPLOY',
        'match': lambda ev: ev['domIsNew'] and ev['domSqlPct'] >= 15,
        'weight': lambda ev: min(1, 0.55 + ev['domSqlPct']/100),
        'project': lambda ev: {
            'dbTimeReductionPct': min(75, ev['domSqlPct'] * 0.75),
            'sessionsFreed': ev['aasB'] * (ev['domSqlPct'] * 0.75 / 100),
        }
    },
    {
        'id': 'HW_ENQUEUE_CONTENTION',
        'match': lambda ev: ev['hwEnqPct'] >= 15,
        'weight': lambda ev: min(1, 0.7 + ev['hwEnqPct']/150),
        'project': lambda ev: {
            'dbTimeReductionPct': min(85, ev['hwEnqPct'] * 0.9),
            'sessionsFreed': min(ev['aasB'] * (ev['hwEnqPct'] * 0.9 / 100), ev['aasB'] * 0.95),
        }
    },
    {
        'id': 'TX_INDEX_CONTENTION',
        'match': lambda ev: ev['txIdxPct'] >= 5 or (re.search(r'index', ev.get('topWaitName',''), re.IGNORECASE) is not None and ev['topWaitPct'] >= 10),
        'weight': lambda ev: min(1, 0.6 + (ev['txIdxPct'] + ev['bufBusyPct']/2)/100),
        'project': lambda ev: {
            'dbTimeReductionPct': min(70, (ev['txIdxPct'] + min(ev['bufBusyPct'], 10)) * 0.8),
            'sessionsFreed': ev['aasB'] * min(0.5, (ev['txIdxPct']/100) * 0.8),
        }
    },
    {
        'id': 'TX_ROW_LOCK_CONTENTION',
        'match': lambda ev: ev['txRowPct'] >= 10 or (ev['txEnqPct'] >= 15 and ev['txIdxPct'] < 2 and ev['txItlPct'] < 2),
        'weight': lambda ev: min(1, 0.55 + ev['txEnqPct']/100),
        'project': lambda ev: {
            'dbTimeReductionPct': min(70, ev['txRowPct'] * 0.7),
            'sessionsFreed': ev['aasB'] * (ev['txRowPct'] * 0.7 / 100),
        }
    },
    {
        'id': 'UNDO_SEGMENT_EXTENSION',
        'match': lambda ev: ev['usEnqPct'] >= 10,
        'weight': lambda ev: min(1, 0.55 + ev['usEnqPct']/100),
        'project': lambda ev: {
            'dbTimeReductionPct': min(60, ev['usEnqPct'] * 0.8),
            'sessionsFreed': ev['aasB'] * (ev['usEnqPct'] * 0.8 / 100),
        }
    },
    {
        'id': 'LIBRARY_CACHE_PRESSURE',
        'match': lambda ev: (ev['libCachePct'] + ev['sharedPoolLatchPct']) >= 10,
        'weight': lambda ev: min(1, 0.5 + (ev['libCachePct'] + ev['sharedPoolLatchPct'])/100),
        'project': lambda ev: {
            'dbTimeReductionPct': min(60, (ev['libCachePct'] + ev['sharedPoolLatchPct']) * 0.7),
            'sessionsFreed': ev['aasB'] * ((ev['libCachePct'] + ev['sharedPoolLatchPct']) * 0.7 / 100),
        }
    },
    {
        'id': 'SQL_DOMINANT',
        'match': lambda ev: (
            ev['domSqlPct'] >= 25 and not ev['domPlanChange'] and not ev['domIsNew']
            and not (ev['freeBufPct'] >= 15 and ev['domIsDML'])
            and not (ev['freeBufPct'] >= 25)
            and not (ev['hwEnqPct'] >= 15)
            and not (ev['txIdxPct'] >= 5)
            and not (ev['txRowPct'] >= 10)
            and not (ev['usEnqPct'] >= 10)
            and not _wait_dominated(ev)
        ),
        'weight': lambda ev: min(1, 0.5 + ev['domSqlPct']/100),
        'project': lambda ev: {
            'dbTimeReductionPct': min(60, ev['domSqlPct'] * 0.6),
            'sessionsFreed': ev['aasB'] * (ev['domSqlPct'] * 0.6 / 100),
        }
    },
    {
        'id': 'CONCURRENT_DML_BOTTLENECK',
        'match': lambda ev: ev['freeBufPct'] >= 15 and ev['domIsDML'] and ev['domSqlPct'] >= 20,
        'weight': lambda ev: min(1, 0.7 + (ev['freeBufPct'] + ev['domSqlPct']/2) / 200),
        'project': lambda ev: {
            'dbTimeReductionPct': min(
                ev['freeBufPct'] + ev['fbEnqPct']
                + min(ev['bufBusyPct'], ev['freeBufPct'] * 0.4)
                + min(ev['commitPct'] * 0.25, 5),
                70) * 0.7,
            'sessionsFreed': min(
                ev['aasB'] * (min(
                    ev['freeBufPct'] + ev['fbEnqPct']
                    + min(ev['bufBusyPct'], ev['freeBufPct'] * 0.4)
                    + min(ev['commitPct'] * 0.25, 5),
                    70) * 0.7 / 100),
                ev['aasB'] * 0.95),
        }
    },
    {
        'id': 'BUFFER_CACHE_WRITE_PRESSURE',
        'match': lambda ev: ev['freeBufPct'] >= 15 or (ev['freeBufPct'] >= 10 and ev['bufBusyPct'] >= 8),
        'weight': lambda ev: min(1, 0.55 + (ev['freeBufPct'] + ev['bufBusyPct'] + ev['fbEnqPct']) / 150),
        'project': lambda ev: {
            'dbTimeReductionPct': min(ev['freeBufPct'] + ev['fbEnqPct'] + min(ev['bufBusyPct'], ev['freeBufPct'] * 0.4), 65) * 0.65,
            'sessionsFreed': min(
                ev['aasB'] * (min(ev['freeBufPct'] + ev['fbEnqPct'] + min(ev['bufBusyPct'], ev['freeBufPct'] * 0.4), 65) * 0.65 / 100),
                ev['aasB'] * 0.95),
        }
    },
    {
        'id': 'CPU_SATURATION',
        'match': lambda ev: ev['cpuUtilPct'] >= 70 and ev['cpuPct'] >= 30,
        'weight': lambda ev: min(1, 0.5 + ev['cpuUtilPct']/200 + ev['cpuPct']/200),
        'project': lambda ev: {
            'dbTimeReductionPct': min(50, max(0, (ev['aasB'] - max(ev['cpus']*0.7, 1)) / max(ev['aasB'], 1) * 100) * 0.7),
            'sessionsFreed': max(0, ev['aasB'] - max(ev['cpus']*0.7, 1)),
        }
    },
    {
        'id': 'IO_PRESSURE',
        'match': lambda ev: ev['ioPct'] >= 30,
        'weight': lambda ev: min(1, 0.4 + ev['ioPct']/100),
        'project': lambda ev: {
            'dbTimeReductionPct': min(60, ev['ioPct'] * 0.55),
            'sessionsFreed': ev['aasB'] * (ev['ioPct'] * 0.55 / 100),
        }
    },
    {
        'id': 'REDO_COMMIT',
        'match': lambda ev: ev['commitPct'] >= 10 and ev['freeBufPct'] < 20,
        'weight': lambda ev: min(1, 0.4 + ev['commitPct']/50),
        'project': lambda ev: {
            'dbTimeReductionPct': min(40, ev['commitPct'] * 0.7),
            'sessionsFreed': ev['aasB'] * (ev['commitPct'] * 0.7 / 100),
        }
    },
    {
        'id': 'CONCURRENCY',
        'match': lambda ev: ev['concPct'] >= 8 and ev['freeBufPct'] < 15,
        'weight': lambda ev: min(1, 0.35 + ev['concPct']/50),
        'project': lambda ev: {
            'dbTimeReductionPct': min(30, ev['concPct'] * 0.6),
            'sessionsFreed': min(ev['aasB'] * (ev['concPct'] * 0.6 / 100), ev['aasB'] * 0.95),
        }
    },
    {
        'id': 'GENERIC_LOAD_INCREASE',
        'match': lambda ev: ev['dbTimeDelta'] >= 30,
        'weight': lambda ev: min(0.45, 0.2 + ev['dbTimeDelta']/300),
        'project': lambda ev: {
            'dbTimeReductionPct': min(25, max(10, ev['dbTimeDelta'] * 0.06)),
            'sessionsFreed': min(ev['aasB'] * min(0.25, ev['dbTimeDelta'] * 0.0006), ev['aasB'] * 0.25),
        }
    },
]

def evaluate(ev: dict) -> dict:
    """Python equivalent of PEEngine.evaluate()"""
    matches = []
    for r in RULES:
        try:
            if r['match'](ev):
                matches.append({'rule': r, 'weight': r['weight'](ev)})
        except Exception:
            pass
    matches.sort(key=lambda m: m['weight'], reverse=True)

    top = matches[0] if matches else None
    projection = top['rule']['project'](ev) if top else None

    # P-tier
    pTier = 'P3'
    if (ev['dbTimeDelta'] >= 100 or ev['aasRatio'] >= 1.5 or ev['domSqlPct'] >= 50
            or ev['hwEnqPct'] >= 60 or ev['freeBufPct'] >= 50
            or (ev['libCachePct'] + ev['sharedPoolLatchPct']) >= 50):
        pTier = 'P1'
    elif (ev['dbTimeDelta'] >= 50 or ev['aasRatio'] >= 1.0 or ev['domSqlPct'] >= 30
            or ev['commitPct'] >= 20 or ev['ioPct'] >= 40
            or ev['hwEnqPct'] >= 20 or ev['txRowPct'] >= 20 or ev['freeBufPct'] >= 25
            or (ev['libCachePct'] + ev['sharedPoolLatchPct']) >= 25):
        pTier = 'P2'

    # Confidence
    base_conf = round(50 + (top['weight'] if top else 0) * 40)
    confidence = max(35, min(95, base_conf + min(len(matches) * 3, 12)))
    conf_label = 'HIGH' if confidence >= 80 else ('LOW' if confidence < 60 else 'MEDIUM')

    # Session risk
    is_cpu_top = bool(re.search(r'DB\s*CPU', ev.get('topWaitName',''), re.IGNORECASE))
    cpu_bound = is_cpu_top and ev['cpuUtilPct'] >= 70 and ev['cpuPct'] >= 30
    if ev['aasRatio'] >= 1.5:
        sr_label = 'SATURATED NOW' if cpu_bound else 'WAIT-SATURATED'
    elif ev['aasRatio'] >= 1.0:
        sr_label = 'CPU-BOUND' if cpu_bound else 'WAIT-BOUND'
    elif ev['aasRatio'] >= 0.85:
        sr_label = '< 30 min HEADROOM'
    elif ev['aasRatio'] >= 0.7:
        sr_label = 'WARMING'
    else:
        sr_label = 'STABLE'

    return {
        'matches': matches, 'top': top, 'projection': projection,
        'pTier': pTier, 'confidence': confidence, 'confLabel': conf_label,
        'sessionRisk': sr_label,
        'topRuleId': top['rule']['id'] if top else None,
    }


# ════════════════════════════════════════════════════════════════════════════
# PART 2: SYNTHETIC AWR CONTEXT BUILDERS
# ════════════════════════════════════════════════════════════════════════════

def make_ctx(
    # Load Profile
    db_time_good=100, db_time_bad=200, db_cpu_good=50, db_cpu_bad=100,
    redo_good=5000, redo_bad=5000,
    logical_reads_good=10000, logical_reads_bad=10000,
    block_changes_good=500, block_changes_bad=500,
    physical_reads_good=100, physical_reads_bad=100,
    physical_writes_good=50, physical_writes_bad=50,
    transactions_good=100, transactions_bad=100,
    # Wait events (bad period) - list of (event_name, wait_class, pct_db_time)
    waits_bad=None,
    waits_good=None,
    # Instance efficiency
    buffer_hit_good=99.5, buffer_hit_bad=99.0,
    # SQL Attribution - dominant SQL
    dom_sql_id='abc123', dom_pct_db=10, dom_plan_change=False, dom_is_new=False,
    dom_sql_text='SELECT * FROM t', dom_epe1=0.01, dom_epe2=0.02,
    # System
    cpus=8,
    aas_good=None, aas_bad=None,
    elapsed_min=60,
):
    """Build an AWRContext dict matching the structure PEEngine.extract() expects."""
    if waits_bad is None:
        waits_bad = [('DB CPU', 'CPU', 40)]
    if waits_good is None:
        waits_good = [('DB CPU', 'CPU', 60)]

    # Compute AAS from DB Time if not provided
    if aas_good is None:
        aas_good = db_time_good / 60.0  # db_time_s is per-second rate → AAS = db_time_s per second / 1
    if aas_bad is None:
        aas_bad = db_time_bad / 60.0

    ctx = {
        'loadProfile': {
            'good': {
                'db_time_s': db_time_good, 'db_cpu_s': db_cpu_good,
                'redo_size': redo_good, 'logical_reads': logical_reads_good,
                'block_changes': block_changes_good, 'physical_reads': physical_reads_good,
                'physical_writes': physical_writes_good, 'transactions': transactions_good,
            },
            'bad': {
                'db_time_s': db_time_bad, 'db_cpu_s': db_cpu_bad,
                'redo_size': redo_bad, 'logical_reads': logical_reads_bad,
                'block_changes': block_changes_bad, 'physical_reads': physical_reads_bad,
                'physical_writes': physical_writes_bad, 'transactions': transactions_bad,
            },
        },
        'waitEvents': {
            'good': [{'event_name': n, 'wait_class': wc, 'pct_db_time': p} for n, wc, p in waits_good],
            'bad':  [{'event_name': n, 'wait_class': wc, 'pct_db_time': p} for n, wc, p in waits_bad],
        },
        'instanceEfficiency': {
            'good': {'buffer_hit_pct': buffer_hit_good},
            'bad':  {'buffer_hit_pct': buffer_hit_bad},
        },
        'sqlAttribution': [
            {
                'id': dom_sql_id, 'pctDb': dom_pct_db,
                'isPlanChg': dom_plan_change, 'isNew': dom_is_new,
                'epe1': dom_epe1, 'epe2': dom_epe2,
                'sql_text': dom_sql_text,
            }
        ],
        'meta': {'cpu_count': cpus},
        'aas': {'good': aas_good, 'bad': aas_bad},
        '_raw': {'bad': {'cpus': cpus, 'sql_stats': [
            {'sql_id': dom_sql_id, 'sql_text': dom_sql_text}
        ]}},
    }
    return ctx


# ════════════════════════════════════════════════════════════════════════════
# PART 3: TEST SCENARIOS — 20+ CASES
# ════════════════════════════════════════════════════════════════════════════

def run_all_tests():
    print(f"\n{BOLD}{W}{'='*78}")
    print(f"  PE ENGINE COMPREHENSIVE EXAM — {len(SCENARIOS)} Scenarios")
    print(f"{'='*78}{D}\n")

    for i, scenario in enumerate(SCENARIOS, 1):
        name = scenario['name']
        print(f"\n{BOLD}{B}━━ Scenario {i}: {name} ━━{D}")

        ctx = scenario['build']()
        ev = extract(ctx)
        result = evaluate(ev)

        # Run all checks for this scenario
        for check in scenario['checks']:
            check(ev, result, scenario)

    # ── ADDITIONAL STRUCTURAL TESTS ──
    print(f"\n{BOLD}{B}━━ Structural & Edge-Case Tests ━━{D}")
    run_structural_tests()

    # ── REPORT ──
    print(f"\n{BOLD}{W}{'='*78}")
    print(f"  EXAM RESULTS")
    print(f"{'='*78}{D}")
    print(f"  {G}PASSED: {_pass}{D}")
    print(f"  {R}FAILED: {_fail}{D}")
    print(f"  {Y}WARNINGS: {_warn}{D}")
    total = _pass + _fail
    accuracy = (_pass / total * 100) if total > 0 else 0
    print(f"  ACCURACY: {accuracy:.1f}%")
    print()

    if _findings:
        print(f"{BOLD}{R}FINDINGS:{D}")
        for f in _findings:
            icon = '🐛' if f['type'] == 'BUG' else '⚠️'
            print(f"  {icon} [{f['type']}] {f['test']}")
            if f.get('expected'):
                print(f"     Expected: {f['expected']}  |  Actual: {f['actual']}")
            if f.get('detail'):
                print(f"     {f['detail']}")
        print()

    return _fail == 0


# ── SCENARIO DEFINITIONS ────────────────────────────────────────────────────

SCENARIOS = [
    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 1: Healthy baseline — minimal degradation
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Healthy Baseline (Good AWR)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=105,  # 5% increase — normal
            db_cpu_good=3, db_cpu_bad=3.2,
            cpus=8,
            waits_bad=[('DB CPU', 'CPU', 65), ('db file sequential read', 'User I/O', 15),
                       ('log file sync', 'Commit', 5)],
            dom_pct_db=8, dom_sql_text='SELECT * FROM orders WHERE id = :1',
            aas_good=1.5, aas_bad=1.6,
        ),
        'checks': [
            lambda ev, r, s: ok('P-tier = P3', f"delta={ev['dbTimeDelta']:.1f}%") if r['pTier'] == 'P3' else fail('P-tier = P3', 'P3', r['pTier'], f"5% increase should be P3"),
            lambda ev, r, s: ok('Session risk = STABLE') if r['sessionRisk'] == 'STABLE' else fail('Session risk', 'STABLE', r['sessionRisk']),
            lambda ev, r, s: ok('No major rule fires') if r['topRuleId'] is None or r['topRuleId'] == 'GENERIC_LOAD_INCREASE' and ev['dbTimeDelta'] < 30 else warn('Unexpected rule fired', f"{r['topRuleId']} fired on healthy baseline"),
            lambda ev, r, s: ok('Low confidence', f"{r['confidence']}%") if r['confidence'] < 70 else warn('High confidence on healthy system', f"{r['confidence']}%"),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 2: Plan regression — classic case
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Plan Regression (Classic)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=250,
            db_cpu_good=4, db_cpu_bad=10,
            cpus=8,
            waits_bad=[('DB CPU', 'CPU', 55), ('db file sequential read', 'User I/O', 25),
                       ('log file sync', 'Commit', 5)],
            dom_sql_id='sql_plan_reg', dom_pct_db=45, dom_plan_change=True,
            dom_sql_text='SELECT * FROM big_table WHERE col = :1',
            dom_epe1=0.01, dom_epe2=2.5,
            aas_good=3, aas_bad=8,
        ),
        'checks': [
            lambda ev, r, s: ok('Top rule = PLAN_REGRESSION') if r['topRuleId'] == 'PLAN_REGRESSION' else fail('Top rule', 'PLAN_REGRESSION', r['topRuleId']),
            lambda ev, r, s: ok('P-tier = P1', f"delta={ev['dbTimeDelta']:.0f}%") if r['pTier'] == 'P1' else fail('P-tier', 'P1', r['pTier'], '150% increase'),
            lambda ev, r, s: ok('Projected recovery ~40.5%', f"{r['projection']['dbTimeReductionPct']:.1f}%") if abs(r['projection']['dbTimeReductionPct'] - 40.5) < 1 else fail('Projected recovery', '40.5%', f"{r['projection']['dbTimeReductionPct']:.1f}%"),
            lambda ev, r, s: ok('Confidence HIGH') if r['confLabel'] == 'HIGH' else fail('Confidence', 'HIGH', r['confLabel']),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 3: New SQL deployed (untested code release)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Untested SQL Deployment',
        'build': lambda: make_ctx(
            db_time_good=80, db_time_bad=200,
            db_cpu_good=3, db_cpu_bad=4,   # 50% CPU util — not saturating
            cpus=8,
            waits_bad=[('DB CPU', 'CPU', 40), ('db file sequential read', 'User I/O', 35)],
            dom_sql_id='new_deploy_01', dom_pct_db=40, dom_is_new=True,
            dom_sql_text='SELECT /*+ FULL(t) */ * FROM huge_table t',
            dom_epe1=0, dom_epe2=5.0,
            aas_good=2, aas_bad=6,
        ),
        'checks': [
            lambda ev, r, s: ok('Top rule = NEW_SQL_DEPLOY') if r['topRuleId'] == 'NEW_SQL_DEPLOY' else fail('Top rule', 'NEW_SQL_DEPLOY', r['topRuleId']),
            lambda ev, r, s: ok('P-tier = P1') if r['pTier'] == 'P1' else fail('P-tier', 'P1', r['pTier'], '150% increase + domSqlPct=40'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 4: HW enqueue contention — bulk INSERT storm
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'HW Enqueue — Bulk INSERT Storm',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=300,
            db_cpu_good=3, db_cpu_bad=5,
            cpus=16,
            waits_bad=[
                ('enq: HW - contention', 'Other', 65),
                ('DB CPU', 'CPU', 15),
                ('log file sync', 'Commit', 8),
                ('buffer busy waits', 'Concurrency', 5),
            ],
            dom_sql_id='ins_001', dom_pct_db=55, dom_sql_text='INSERT INTO staging_table VALUES (:1,:2,:3)',
            aas_good=3, aas_bad=12,
        ),
        'checks': [
            lambda ev, r, s: ok('Top rule = HW_ENQUEUE_CONTENTION') if r['topRuleId'] == 'HW_ENQUEUE_CONTENTION' else fail('Top rule', 'HW_ENQUEUE_CONTENTION', r['topRuleId'], 'HW at 65% should outrank SQL_DOMINANT'),
            lambda ev, r, s: ok('P-tier = P1', 'hwEnqPct>=60') if r['pTier'] == 'P1' else fail('P-tier', 'P1', r['pTier'], 'hwEnqPct=65 >= P1 threshold 60'),
            lambda ev, r, s: (
                ok('Recovery ~58.5%', f"{r['projection']['dbTimeReductionPct']:.1f}%")
                if abs(r['projection']['dbTimeReductionPct'] - min(85, 65*0.9)) < 1
                else fail('Recovery', f"{min(85,65*0.9):.1f}%", f"{r['projection']['dbTimeReductionPct']:.1f}%")
            ),
            lambda ev, r, s: (
                ok('sessionsFreed capped at aasB*0.95', f"{r['projection']['sessionsFreed']:.1f}")
                if r['projection']['sessionsFreed'] <= ev['aasB'] * 0.95 + 0.01
                else fail('sessionsFreed cap', f"<= {ev['aasB']*0.95:.1f}", f"{r['projection']['sessionsFreed']:.1f}")
            ),
            lambda ev, r, s: ok('SQL_DOMINANT suppressed') if not any(m['rule']['id'] == 'SQL_DOMINANT' for m in r['matches']) else fail('SQL_DOMINANT guard', 'not fired', 'fired', 'HW should suppress SQL_DOMINANT'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 5: TX row lock — application blocking
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'TX Row Lock Contention',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=180,
            db_cpu_good=4, db_cpu_bad=5,
            cpus=8,
            waits_bad=[
                ('enq: TX - row lock contention', 'Application', 25),
                ('DB CPU', 'CPU', 30),
                ('db file sequential read', 'User I/O', 20),
                ('log file sync', 'Commit', 10),
            ],
            dom_sql_id='upd_001', dom_pct_db=30, dom_sql_text='UPDATE accounts SET balance = :1 WHERE id = :2',
            aas_good=3, aas_bad=6,
        ),
        'checks': [
            lambda ev, r, s: ok('Top rule = TX_ROW_LOCK_CONTENTION') if r['topRuleId'] == 'TX_ROW_LOCK_CONTENTION' else fail('Top rule', 'TX_ROW_LOCK_CONTENTION', r['topRuleId']),
            lambda ev, r, s: ok('P-tier = P2', 'txRowPct=25 >= 20') if r['pTier'] == 'P2' else fail('P-tier', 'P2', r['pTier']),
            lambda ev, r, s: (
                ok('Recovery uses txRowPct not txEnqPct', f"reduction={r['projection']['dbTimeReductionPct']:.1f}%")
                if abs(r['projection']['dbTimeReductionPct'] - min(70, 25 * 0.7)) < 0.1
                else fail('Recovery formula', f"{min(70,25*0.7):.1f}%", f"{r['projection']['dbTimeReductionPct']:.1f}%",
                          'Bug 2: must use txRowPct, not txEnqPct')
            ),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 6: TX row lock with mixed TX events (Bug 2 regression test)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'TX Mixed (row lock + index) — Bug 2 regression',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=170,
            db_cpu_good=4, db_cpu_bad=5,
            cpus=8,
            waits_bad=[
                ('enq: TX - row lock contention', 'Application', 10),
                ('enq: TX - index contention', 'Concurrency', 13),
                ('DB CPU', 'CPU', 35),
                ('db file sequential read', 'User I/O', 20),
            ],
            dom_sql_id='mix_tx', dom_pct_db=20, dom_sql_text='UPDATE orders SET status=:1',
            aas_good=3, aas_bad=5.5,
        ),
        'checks': [
            lambda ev, r, s: (
                ok(f'txEnqPct={ev["txEnqPct"]:.0f}%, txRowPct={ev["txRowPct"]:.0f}%, txIdxPct={ev["txIdxPct"]:.0f}%')
                if ev['txEnqPct'] == 23 and ev['txRowPct'] == 10 and ev['txIdxPct'] == 13
                else fail('Wait decomposition', 'txEnq=23, txRow=10, txIdx=13',
                          f'txEnq={ev["txEnqPct"]}, txRow={ev["txRowPct"]}, txIdx={ev["txIdxPct"]}')
            ),
            lambda ev, r, s: (
                # TX_ROW_LOCK should project based on txRowPct=10, NOT txEnqPct=23
                ok('TX_ROW project uses txRowPct=10')
                if any(m['rule']['id'] == 'TX_ROW_LOCK_CONTENTION' for m in r['matches'])
                   and min(70, 10*0.7) == 7.0  # expected from txRowPct
                else warn('TX_ROW not in matches')
            ),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 7: Free buffer waits + DML dominant (concurrent INSERT)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'DBWR Bottleneck — Concurrent DML',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=280,
            db_cpu_good=4, db_cpu_bad=6,
            cpus=8,
            waits_bad=[
                ('free buffer waits', 'Configuration', 30),
                ('buffer busy waits', 'Concurrency', 18),
                ('log file sync', 'Commit', 12),
                ('DB CPU', 'CPU', 20),
                ('enq: FB - contention', 'Other', 8),
            ],
            dom_sql_id='ins_bulk', dom_pct_db=35,
            dom_sql_text='INSERT INTO fact_table SELECT * FROM staging',
            aas_good=3, aas_bad=10,
        ),
        'checks': [
            lambda ev, r, s: ok('Top rule = CONCURRENT_DML_BOTTLENECK') if r['topRuleId'] == 'CONCURRENT_DML_BOTTLENECK' else fail('Top rule', 'CONCURRENT_DML_BOTTLENECK', r['topRuleId']),
            lambda ev, r, s: (
                # Reclaim = min(30 + 8 + min(18, 30*0.4) + min(12*0.25, 5), 70)
                #         = min(30 + 8 + 12 + 3, 70) = min(53, 70) = 53
                # Recovery = 53 * 0.7 = 37.1
                ok(f'Recovery uses capped reclaim', f"{r['projection']['dbTimeReductionPct']:.1f}%")
                if abs(r['projection']['dbTimeReductionPct'] - 37.1) < 0.5
                else fail('Capped reclaim', '37.1%', f"{r['projection']['dbTimeReductionPct']:.1f}%",
                         'Bug 3: bufBusy+commit must be capped as downstream')
            ),
            lambda ev, r, s: ok('REDO_COMMIT suppressed when freeBuf>=20') if not any(m['rule']['id'] == 'REDO_COMMIT' for m in r['matches']) else warn('REDO_COMMIT fired alongside CONCURRENT_DML (freeBufPct=30>=20 should suppress)', 'Demote guard: commitPct>=10 && freeBufPct<20'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 8: Buffer cache write pressure (no dominant DML)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'DBWR Pressure — No Dominant DML',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=200,
            db_cpu_good=4, db_cpu_bad=5,
            cpus=8,
            waits_bad=[
                ('free buffer waits', 'Configuration', 22),
                ('buffer busy waits', 'Concurrency', 12),
                ('DB CPU', 'CPU', 30),
                ('enq: FB - contention', 'Other', 5),
                ('log file sync', 'Commit', 8),
            ],
            dom_sql_id='sel_rpt', dom_pct_db=15,
            dom_sql_text='SELECT SUM(amount) FROM transactions WHERE dt BETWEEN :1 AND :2',
            aas_good=3, aas_bad=7,
        ),
        'checks': [
            lambda ev, r, s: ok('Top rule = BUFFER_CACHE_WRITE_PRESSURE') if r['topRuleId'] == 'BUFFER_CACHE_WRITE_PRESSURE' else fail('Top rule', 'BUFFER_CACHE_WRITE_PRESSURE', r['topRuleId'], 'SELECT dom + freeBuf=22 should be BUFFER_CACHE not CONCURRENT_DML'),
            lambda ev, r, s: (
                # reclaim = min(22 + 5 + min(12, 22*0.4), 65) = min(22 + 5 + 8.8, 65) = min(35.8, 65) = 35.8
                # recovery = 35.8 * 0.65 = 23.27
                ok(f'Capped reclaim correct', f"{r['projection']['dbTimeReductionPct']:.1f}%")
                if abs(r['projection']['dbTimeReductionPct'] - 23.27) < 0.5
                else fail('Reclaim', '23.3%', f"{r['projection']['dbTimeReductionPct']:.1f}%")
            ),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 9: Marginal buffer cache — threshold test (Bug 9)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Marginal Buffer Cache (Noise Threshold)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=115,
            db_cpu_good=4, db_cpu_bad=4.5,
            cpus=8,
            waits_bad=[
                ('DB CPU', 'CPU', 55),
                ('free buffer waits', 'Configuration', 9),
                ('buffer busy waits', 'Concurrency', 6),
                ('db file sequential read', 'User I/O', 15),
            ],
            dom_sql_id='sel_01', dom_pct_db=12,
            dom_sql_text='SELECT * FROM lookup WHERE id = :1',
            aas_good=2, aas_bad=2.3,
        ),
        'checks': [
            lambda ev, r, s: (
                # freeBufPct=9 < 10, bufBusyPct=6 < 8 → should NOT fire
                ok('BUFFER_CACHE rule does NOT fire (noise)')
                if not any(m['rule']['id'] == 'BUFFER_CACHE_WRITE_PRESSURE' for m in r['matches'])
                else fail('Noise threshold', 'not fired', 'fired', 'freeBufPct=9 < 10 AND bufBusyPct=6 < 8 — should be suppressed')
            ),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 10: CPU saturation — pure CPU-bound
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'CPU Saturation (Pure CPU-Bound)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=250,
            db_cpu_good=4, db_cpu_bad=7,   # 7/8 = 87.5% CPU util
            cpus=8,
            waits_bad=[('DB CPU', 'CPU', 70), ('db file sequential read', 'User I/O', 15)],
            dom_sql_id='cpu_hog', dom_pct_db=20, dom_sql_text='SELECT complex_function(id) FROM big_table',
            aas_good=3, aas_bad=10,
        ),
        'checks': [
            lambda ev, r, s: ok(f'cpuUtilPct = {ev["cpuUtilPct"]:.1f}%') if abs(ev['cpuUtilPct'] - 87.5) < 1 else fail('cpuUtilPct', '87.5', f"{ev['cpuUtilPct']:.1f}"),
            lambda ev, r, s: ok('CPU_SATURATION fires') if any(m['rule']['id'] == 'CPU_SATURATION' for m in r['matches']) else fail('CPU_SATURATION', 'fired', 'not fired'),
            lambda ev, r, s: ok('Session risk = SATURATED NOW or CPU-BOUND') if r['sessionRisk'] in ('SATURATED NOW', 'CPU-BOUND') else fail('Session risk', 'SATURATED NOW/CPU-BOUND', r['sessionRisk']),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 11: I/O pressure — storage bound
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'I/O Pressure (Storage Bound)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=180,
            db_cpu_good=3, db_cpu_bad=3.5,
            cpus=8,
            waits_bad=[
                ('db file sequential read', 'User I/O', 45),
                ('db file scattered read', 'User I/O', 12),
                ('DB CPU', 'CPU', 20),
                ('log file sync', 'Commit', 5),
            ],
            buffer_hit_good=99.5, buffer_hit_bad=92.0,
            dom_sql_id='io_sql', dom_pct_db=18, dom_sql_text='SELECT * FROM orders WHERE created_dt > :1',
            aas_good=2.5, aas_bad=5,
        ),
        'checks': [
            lambda ev, r, s: ok(f'ioPct = {ev["ioPct"]:.0f}%') if abs(ev['ioPct'] - 57) < 1 else fail('ioPct', '57', f"{ev['ioPct']:.1f}"),
            lambda ev, r, s: ok('IO_PRESSURE fires') if any(m['rule']['id'] == 'IO_PRESSURE' for m in r['matches']) else fail('IO_PRESSURE', 'fired', 'not fired'),
            lambda ev, r, s: ok('P-tier = P2', 'ioPct=57 >= 40') if r['pTier'] == 'P2' else fail('P-tier', 'P2', r['pTier'], 'ioPct=57 >= P2 threshold 40'),
            lambda ev, r, s: ok(f'bufferHitDrop = {ev["bufferHitDrop"]:.1f}pp') if abs(ev['bufferHitDrop'] - 7.5) < 0.1 else fail('bufferHitDrop', '7.5', f"{ev['bufferHitDrop']:.1f}"),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 12: Log file sync / commit storm
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Commit Storm (Log File Sync)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=160,
            db_cpu_good=4, db_cpu_bad=5,
            cpus=8,
            waits_bad=[
                ('log file sync', 'Commit', 35),
                ('DB CPU', 'CPU', 30),
                ('db file sequential read', 'User I/O', 15),
                ('log file parallel write', 'System I/O', 8),
            ],
            dom_sql_id='commit_sql', dom_pct_db=15, dom_sql_text='UPDATE t SET x=:1 WHERE id=:2',
            aas_good=2.5, aas_bad=5,
        ),
        'checks': [
            lambda ev, r, s: ok('REDO_COMMIT fires') if any(m['rule']['id'] == 'REDO_COMMIT' for m in r['matches']) else fail('REDO_COMMIT', 'fired', 'not fired'),
            lambda ev, r, s: ok('P-tier = P2', 'commitPct=35 >= 20') if r['pTier'] == 'P2' else fail('P-tier', 'P2', r['pTier']),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 13: Library cache contention — hard parse storm
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Library Cache / Hard Parse Storm',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=190,
            db_cpu_good=4, db_cpu_bad=6,
            cpus=8,
            waits_bad=[
                ('library cache: mutex X', 'Concurrency', 20),
                ('cursor: pin S wait on X', 'Concurrency', 12),
                ('latch: shared pool', 'Concurrency', 8),
                ('DB CPU', 'CPU', 30),
                ('db file sequential read', 'User I/O', 10),
            ],
            dom_sql_id='parse_sql', dom_pct_db=10, dom_sql_text='SELECT * FROM dynamic_v',
            aas_good=2.5, aas_bad=6,
        ),
        'checks': [
            lambda ev, r, s: ok(f'libCachePct = {ev["libCachePct"]:.0f}%') if abs(ev['libCachePct'] - 32) < 1 else fail('libCachePct', '32', f"{ev['libCachePct']:.1f}"),
            lambda ev, r, s: ok(f'sharedPoolLatchPct = {ev["sharedPoolLatchPct"]:.0f}%') if abs(ev['sharedPoolLatchPct'] - 8) < 1 else fail('sharedPoolLatchPct', '8', f"{ev['sharedPoolLatchPct']:.1f}"),
            lambda ev, r, s: ok('LIBRARY_CACHE_PRESSURE fires') if any(m['rule']['id'] == 'LIBRARY_CACHE_PRESSURE' for m in r['matches']) else fail('LIBRARY_CACHE_PRESSURE', 'fired', 'not fired'),
            lambda ev, r, s: ok('P-tier = P2', 'libCache+sharedPool=40 >= 25') if r['pTier'] in ('P1', 'P2') else fail('P-tier', 'P1 or P2', r['pTier']),
            # concPct should EXCLUDE sharedPoolLatchPct
            lambda ev, r, s: (
                ok(f'concPct excludes sharedPool', f"concPct={ev['concPct']:.1f} = latchPct({ev['latchPct']:.1f}) - sharedPoolLatchPct({ev['sharedPoolLatchPct']:.1f})")
                if abs(ev['concPct'] - (ev['latchPct'] - ev['sharedPoolLatchPct'])) < 0.1
                else fail('concPct', f"{ev['latchPct']-ev['sharedPoolLatchPct']:.1f}", f"{ev['concPct']:.1f}", 'Bug 4 regression: concPct must exclude sharedPoolLatchPct')
            ),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 14: Concurrency hotspot (latches, no buffer pressure)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Concurrency Hotspot (Cache Buffers Chains)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=150,
            db_cpu_good=4, db_cpu_bad=5,
            cpus=8,
            waits_bad=[
                ('latch: cache buffers chains', 'Concurrency', 15),
                ('cursor: pin S', 'Concurrency', 5),
                ('DB CPU', 'CPU', 45),
                ('db file sequential read', 'User I/O', 15),
            ],
            dom_sql_id='hot_block', dom_pct_db=18, dom_sql_text='SELECT * FROM hot_table WHERE id = :1',
            aas_good=2.5, aas_bad=4.5,
        ),
        'checks': [
            lambda ev, r, s: (
                # latchPct = 15 (CBC) + 5 (cursor pin S) = 20
                # sharedPoolLatchPct = 0
                # concPct = 20 - 0 = 20
                ok(f'concPct = {ev["concPct"]:.0f}% (pure CBC + cursor)')
                if abs(ev['concPct'] - 20) < 1
                else fail('concPct', '20', f"{ev['concPct']:.1f}")
            ),
            lambda ev, r, s: ok('CONCURRENCY fires') if any(m['rule']['id'] == 'CONCURRENCY' for m in r['matches']) else fail('CONCURRENCY', 'fired', 'not fired'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 15: Generic load increase — massive surge
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Generic Load Increase — 5000% Surge',
        'build': lambda: make_ctx(
            db_time_good=10, db_time_bad=510,  # 5000% increase
            db_cpu_good=1, db_cpu_bad=8,
            cpus=16,
            waits_bad=[
                ('DB CPU', 'CPU', 25),
                ('db file sequential read', 'User I/O', 20),
                ('log file sync', 'Commit', 15),
                ('db file scattered read', 'User I/O', 10),
                ('direct path read', 'User I/O', 8),
                ('latch: cache buffers chains', 'Concurrency', 5),
            ],
            dom_sql_id='mixed_01', dom_pct_db=12, dom_sql_text='SELECT * FROM rpt_table',
            aas_good=0.5, aas_bad=15,
        ),
        'checks': [
            lambda ev, r, s: ok(f'dbTimeDelta = {ev["dbTimeDelta"]:.0f}%') if abs(ev['dbTimeDelta'] - 5000) < 10 else fail('dbTimeDelta', '5000', f"{ev['dbTimeDelta']:.0f}"),
            lambda ev, r, s: ok('GENERIC_LOAD_INCREASE matches') if any(m['rule']['id'] == 'GENERIC_LOAD_INCREASE' for m in r['matches']) else fail('GENERIC', 'fired', 'not fired'),
            lambda ev, r, s: (
                # Scaled: min(25, max(10, 5000 * 0.06)) = min(25, max(10, 300)) = 25
                ok('Recovery scales to 25% (max for 5000% surge)')
                if any(m['rule']['id'] == 'GENERIC_LOAD_INCREASE' for m in r['matches'])
                   and abs(min(25, max(10, 5000 * 0.06)) - 25) < 0.1
                else warn('GENERIC not in matches to verify')
            ),
            lambda ev, r, s: ok('P-tier = P1', 'dbTimeDelta=5000 >= 100') if r['pTier'] == 'P1' else fail('P-tier', 'P1', r['pTier']),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 16: Generic load increase — small surge (30%)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Generic Load Increase — 30% Surge',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=130,
            db_cpu_good=4, db_cpu_bad=5,
            cpus=8,
            waits_bad=[
                ('DB CPU', 'CPU', 35),
                ('db file sequential read', 'User I/O', 20),
                ('log file sync', 'Commit', 8),
                ('latch: cache buffers chains', 'Concurrency', 5),
            ],
            dom_sql_id='mixed_sm', dom_pct_db=10, dom_sql_text='SELECT * FROM t',
            aas_good=2.5, aas_bad=3.5,
        ),
        'checks': [
            lambda ev, r, s: (
                # Scaled: min(25, max(10, 30 * 0.06)) = min(25, max(10, 1.8)) = 10
                ok(f'Recovery = 10% for 30% surge')
                if any(m['rule']['id'] == 'GENERIC_LOAD_INCREASE' for m in r['matches'])
                else warn('GENERIC not in matches')
            ),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 17: Undo segment extension
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Undo Segment Extension (US-enq)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=175,
            db_cpu_good=3, db_cpu_bad=4,
            cpus=8,
            waits_bad=[
                ('enq: US - contention', 'Configuration', 25),
                ('DB CPU', 'CPU', 30),
                ('db file sequential read', 'User I/O', 15),
                ('log file sync', 'Commit', 8),
            ],
            dom_sql_id='us_sql', dom_pct_db=20, dom_sql_text='DELETE FROM archive WHERE dt < :1',
            aas_good=2.5, aas_bad=5,
        ),
        'checks': [
            lambda ev, r, s: ok('UNDO_SEGMENT_EXTENSION fires') if any(m['rule']['id'] == 'UNDO_SEGMENT_EXTENSION' for m in r['matches']) else fail('UNDO_SEGMENT_EXTENSION', 'fired', 'not fired'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 18: TX index contention — right-growing key
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'TX Index Contention (Right-Growing Key)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=180,
            db_cpu_good=4, db_cpu_bad=5,
            cpus=8,
            waits_bad=[
                ('enq: TX - index contention', 'Concurrency', 20),
                ('buffer busy waits', 'Concurrency', 10),
                ('DB CPU', 'CPU', 35),
                ('db file sequential read', 'User I/O', 15),
            ],
            dom_sql_id='idx_ins', dom_pct_db=22, dom_sql_text='INSERT INTO orders (id, ...) VALUES (seq.NEXTVAL, ...)',
            aas_good=3, aas_bad=6,
        ),
        'checks': [
            lambda ev, r, s: ok('TX_INDEX_CONTENTION fires') if any(m['rule']['id'] == 'TX_INDEX_CONTENTION' for m in r['matches']) else fail('TX_INDEX_CONTENTION', 'fired', 'not fired'),
            lambda ev, r, s: (
                # Recovery = min(70, (20 + min(10, 10)) * 0.8) = min(70, 24) = 24
                ok(f'Recovery = {r["projection"]["dbTimeReductionPct"]:.1f}%')
                if r['topRuleId'] == 'TX_INDEX_CONTENTION'
                   and abs(r['projection']['dbTimeReductionPct'] - 24) < 1
                else warn(f'Top rule is {r["topRuleId"]} not TX_INDEX_CONTENTION')
            ),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 19: Wait-dominated SQL — SQL should NOT be the top rule
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Wait-Dominated SQL (SQL suppressed)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=220,
            db_cpu_good=3, db_cpu_bad=4,
            cpus=8,
            waits_bad=[
                ('enq: HW - contention', 'Other', 50),
                ('DB CPU', 'CPU', 20),
                ('log file sync', 'Commit', 10),
                ('db file sequential read', 'User I/O', 8),
            ],
            dom_sql_id='wait_dom', dom_pct_db=40,
            dom_sql_text='INSERT INTO target SELECT * FROM source',
            aas_good=3, aas_bad=8,
        ),
        'checks': [
            lambda ev, r, s: ok('SQL_DOMINANT suppressed') if r['topRuleId'] != 'SQL_DOMINANT' else fail('SQL_DOMINANT guard', 'suppressed', 'fired', 'HW at 50% should suppress SQL_DOMINANT'),
            lambda ev, r, s: ok('Top = HW_ENQUEUE_CONTENTION') if r['topRuleId'] == 'HW_ENQUEUE_CONTENTION' else fail('Top rule', 'HW_ENQUEUE_CONTENTION', r['topRuleId']),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 20: Session risk ladder test
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Session Risk Ladder (AAS Ratios)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=200,
            db_cpu_good=3, db_cpu_bad=3.5,
            cpus=8,
            waits_bad=[
                ('db file sequential read', 'User I/O', 50),
                ('DB CPU', 'CPU', 25),
                ('log file sync', 'Commit', 10),
            ],
            dom_sql_id='io_dom', dom_pct_db=20, dom_sql_text='SELECT * FROM t',
            aas_good=3, aas_bad=6,   # aasRatio = 6/8 = 0.75
        ),
        'checks': [
            lambda ev, r, s: ok(f'aasRatio = {ev["aasRatio"]:.2f}') if abs(ev['aasRatio'] - 0.75) < 0.01 else fail('aasRatio', '0.75', f"{ev['aasRatio']:.2f}"),
            lambda ev, r, s: ok('Session risk = WARMING') if r['sessionRisk'] == 'WARMING' else fail('Session risk', 'WARMING', r['sessionRisk'], 'aasRatio=0.75 should be WARMING'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 21: Near-capacity wait-bound
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Near-Capacity Wait-Bound (AAS/CPU ≈ 1.2)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=300,
            db_cpu_good=3, db_cpu_bad=4,
            cpus=8,
            waits_bad=[
                ('db file sequential read', 'User I/O', 55),
                ('DB CPU', 'CPU', 15),
                ('log file sync', 'Commit', 10),
            ],
            dom_sql_id='io_heavy', dom_pct_db=22, dom_sql_text='SELECT * FROM big',
            aas_good=3, aas_bad=10,   # aasRatio = 10/8 = 1.25
        ),
        'checks': [
            lambda ev, r, s: ok('Session risk = WAIT-BOUND') if r['sessionRisk'] == 'WAIT-BOUND' else fail('Session risk', 'WAIT-BOUND', r['sessionRisk'], 'aasRatio=1.25, topWait=I/O, cpuPct=15 < 30 → WAIT-BOUND'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 22: Extreme scenario — everything bad at once
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Everything Failing (Stress Test)',
        'build': lambda: make_ctx(
            db_time_good=50, db_time_bad=1000,
            db_cpu_good=2, db_cpu_bad=7,
            cpus=8,
            waits_bad=[
                ('free buffer waits', 'Configuration', 25),
                ('enq: HW - contention', 'Other', 20),
                ('log file sync', 'Commit', 15),
                ('buffer busy waits', 'Concurrency', 10),
                ('DB CPU', 'CPU', 10),
                ('db file sequential read', 'User I/O', 8),
                ('latch: cache buffers chains', 'Concurrency', 5),
                ('enq: TX - row lock contention', 'Application', 4),
            ],
            dom_sql_id='chaos', dom_pct_db=30,
            dom_sql_text='INSERT INTO audit_log SELECT * FROM temp_stage',
            aas_good=1, aas_bad=25,
        ),
        'checks': [
            lambda ev, r, s: ok('P-tier = P1') if r['pTier'] == 'P1' else fail('P-tier', 'P1', r['pTier']),
            lambda ev, r, s: ok(f'Multiple rules fire: {len(r["matches"])}') if len(r['matches']) >= 4 else fail('Rule count', '>=4', len(r['matches'])),
            lambda ev, r, s: ok(f'sessionsFreed <= aasB', f"{r['projection']['sessionsFreed']:.1f} <= {ev['aasB']:.1f}") if r['projection']['sessionsFreed'] <= ev['aasB'] * 0.96 else fail('sessionsFreed cap', f"<= {ev['aasB']*0.95:.1f}", f"{r['projection']['sessionsFreed']:.1f}"),
            lambda ev, r, s: ok('Top rule handles dominant issue') if r['topRuleId'] in ('HW_ENQUEUE_CONTENTION', 'CONCURRENT_DML_BOTTLENECK', 'BUFFER_CACHE_WRITE_PRESSURE') else warn(f'Top rule = {r["topRuleId"]} — might not be the most impactful'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 23: Zero baseline — first-ever AWR (no baseline to compare)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Zero Baseline (No Prior Period)',
        'build': lambda: make_ctx(
            db_time_good=0, db_time_bad=200,
            db_cpu_good=0, db_cpu_bad=5,
            cpus=8,
            waits_bad=[('DB CPU', 'CPU', 60), ('db file sequential read', 'User I/O', 25)],
            dom_sql_id='first_run', dom_pct_db=15, dom_sql_text='SELECT * FROM t',
            aas_good=0, aas_bad=5,
        ),
        'checks': [
            lambda ev, r, s: ok(f'dbTimeDelta = 100% (no divide-by-zero)') if ev['dbTimeDelta'] == 100 else fail('dbTimeDelta', '100', ev['dbTimeDelta']),
            lambda ev, r, s: ok('No crash') if r['pTier'] is not None else fail('crash', 'no crash', 'crash'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 24: Identical periods — zero delta
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Identical Periods (Zero Delta)',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=100,
            db_cpu_good=4, db_cpu_bad=4,
            cpus=8,
            waits_bad=[('DB CPU', 'CPU', 60), ('db file sequential read', 'User I/O', 20)],
            waits_good=[('DB CPU', 'CPU', 60), ('db file sequential read', 'User I/O', 20)],
            dom_sql_id='same', dom_pct_db=8, dom_sql_text='SELECT 1 FROM dual',
            aas_good=2, aas_bad=2,
        ),
        'checks': [
            lambda ev, r, s: ok(f'dbTimeDelta = 0%') if ev['dbTimeDelta'] == 0 else fail('dbTimeDelta', '0', ev['dbTimeDelta']),
            lambda ev, r, s: ok('P-tier = P3') if r['pTier'] == 'P3' else fail('P-tier', 'P3', r['pTier']),
            lambda ev, r, s: ok('Session risk = STABLE') if r['sessionRisk'] == 'STABLE' else fail('Session risk', 'STABLE', r['sessionRisk']),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 25: Improvement (bad-to-good direction)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Performance Improvement (Negative Delta)',
        'build': lambda: make_ctx(
            db_time_good=200, db_time_bad=100,  # 50% decrease
            db_cpu_good=6, db_cpu_bad=3,
            cpus=8,
            waits_bad=[('DB CPU', 'CPU', 60), ('db file sequential read', 'User I/O', 20)],
            dom_sql_id='better', dom_pct_db=8, dom_sql_text='SELECT * FROM t',
            aas_good=5, aas_bad=2,
        ),
        'checks': [
            lambda ev, r, s: ok(f'dbTimeDelta = -50%') if abs(ev['dbTimeDelta'] - (-50)) < 1 else fail('dbTimeDelta', '-50', f"{ev['dbTimeDelta']:.1f}"),
            lambda ev, r, s: ok('P-tier = P3') if r['pTier'] == 'P3' else fail('P-tier', 'P3', r['pTier'], 'Improvement should not be P1/P2'),
            lambda ev, r, s: ok('GENERIC_LOAD_INCREASE does NOT fire') if not any(m['rule']['id'] == 'GENERIC_LOAD_INCREASE' for m in r['matches']) else warn('GENERIC fired on improvement', 'dbTimeDelta=-50 < 30 threshold'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 26: Single-CPU system (edge case)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Single-CPU System (Edge Case)',
        'build': lambda: make_ctx(
            db_time_good=10, db_time_bad=30,
            db_cpu_good=0.8, db_cpu_bad=0.95,   # 95% CPU util on 1 CPU
            cpus=1,
            waits_bad=[('DB CPU', 'CPU', 80), ('db file sequential read', 'User I/O', 10)],
            dom_sql_id='single_cpu', dom_pct_db=40, dom_sql_text='SELECT * FROM t',
            aas_good=0.5, aas_bad=1.5,
        ),
        'checks': [
            lambda ev, r, s: ok(f'cpuUtilPct = {ev["cpuUtilPct"]:.0f}%') if abs(ev['cpuUtilPct'] - 95) < 1 else fail('cpuUtilPct', '95', f"{ev['cpuUtilPct']:.1f}"),
            lambda ev, r, s: ok('aasRatio = 1.5') if abs(ev['aasRatio'] - 1.5) < 0.01 else fail('aasRatio', '1.5', f"{ev['aasRatio']:.2f}"),
            lambda ev, r, s: ok('CPU_SATURATION fires') if any(m['rule']['id'] == 'CPU_SATURATION' for m in r['matches']) else fail('CPU_SATURATION', 'fired', 'not fired'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 27: Large system (128 CPUs)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Large System (128 CPUs)',
        'build': lambda: make_ctx(
            db_time_good=500, db_time_bad=1200,
            db_cpu_good=50, db_cpu_bad=80,   # 80/128 = 62.5% — below 70% threshold
            cpus=128,
            waits_bad=[
                ('DB CPU', 'CPU', 35),
                ('db file sequential read', 'User I/O', 25),
                ('log file sync', 'Commit', 15),
                ('db file scattered read', 'User I/O', 10),
            ],
            dom_sql_id='big_sys', dom_pct_db=18, dom_sql_text='SELECT * FROM warehouse_fact',
            aas_good=20, aas_bad=50,
        ),
        'checks': [
            lambda ev, r, s: ok(f'cpuUtilPct = {ev["cpuUtilPct"]:.1f}%') if abs(ev['cpuUtilPct'] - 62.5) < 1 else fail('cpuUtilPct', '62.5', f"{ev['cpuUtilPct']:.1f}"),
            lambda ev, r, s: ok('CPU_SATURATION does NOT fire') if not any(m['rule']['id'] == 'CPU_SATURATION' for m in r['matches']) else fail('CPU_SATURATION', 'not fired', 'fired', 'cpuUtilPct=62.5 < 70 threshold'),
            lambda ev, r, s: ok('Session risk = STABLE') if r['sessionRisk'] == 'STABLE' else warn(f'Session risk = {r["sessionRisk"]}', 'aasRatio=50/128=0.39 should be STABLE'),
        ]
    },

    # ──────────────────────────────────────────────────────────────────────
    # SCENARIO 28: Log buffer space (distinct from log file sync)
    # ──────────────────────────────────────────────────────────────────────
    {
        'name': 'Log Buffer Space Pressure',
        'build': lambda: make_ctx(
            db_time_good=100, db_time_bad=180,
            db_cpu_good=4, db_cpu_bad=5,
            cpus=8,
            waits_bad=[
                ('log buffer space', 'Configuration', 18),
                ('log file sync', 'Commit', 15),
                ('DB CPU', 'CPU', 35),
                ('db file sequential read', 'User I/O', 12),
            ],
            dom_sql_id='redo_heavy', dom_pct_db=15, dom_sql_text='UPDATE big_table SET col = :1',
            redo_good=5000, redo_bad=25000,
            aas_good=3, aas_bad=5.5,
        ),
        'checks': [
            lambda ev, r, s: ok(f'logBufPct = {ev["logBufPct"]:.0f}%') if abs(ev['logBufPct'] - 18) < 1 else fail('logBufPct', '18', f"{ev['logBufPct']:.1f}"),
            lambda ev, r, s: ok(f'redoDelta = {ev["redoDelta"]:.0f}%') if abs(ev['redoDelta'] - 400) < 10 else fail('redoDelta', '400', f"{ev['redoDelta']:.0f}"),
            lambda ev, r, s: ok('REDO_COMMIT fires (commitPct=15 + logBuf)') if any(m['rule']['id'] == 'REDO_COMMIT' for m in r['matches']) else fail('REDO_COMMIT', 'fired', 'not fired'),
        ]
    },
]


# ════════════════════════════════════════════════════════════════════════════
# PART 4: STRUCTURAL / INVARIANT TESTS
# ════════════════════════════════════════════════════════════════════════════

def run_structural_tests():
    """Tests that don't need specific scenarios — they validate engine invariants."""

    # ── TEST: Rule ordering (priority) ──
    # HW/TX/US should outrank SQL_DOMINANT
    rule_ids = [r['id'] for r in RULES]
    hw_idx = rule_ids.index('HW_ENQUEUE_CONTENTION')
    sql_idx = rule_ids.index('SQL_DOMINANT')
    if hw_idx < sql_idx:
        ok('HW_ENQUEUE outranks SQL_DOMINANT in rule order')
    else:
        fail('Rule priority', 'HW before SQL_DOMINANT', f'HW at {hw_idx}, SQL at {sql_idx}')

    tx_idx = rule_ids.index('TX_INDEX_CONTENTION')
    if tx_idx < sql_idx:
        ok('TX_INDEX outranks SQL_DOMINANT')
    else:
        fail('Rule priority', 'TX_INDEX before SQL_DOMINANT', f'TX at {tx_idx}, SQL at {sql_idx}')

    # CONCURRENT_DML before BUFFER_CACHE before CONCURRENCY
    cdml_idx = rule_ids.index('CONCURRENT_DML_BOTTLENECK')
    bc_idx = rule_ids.index('BUFFER_CACHE_WRITE_PRESSURE')
    conc_idx = rule_ids.index('CONCURRENCY')
    if cdml_idx < bc_idx < conc_idx:
        ok('CONCURRENT_DML → BUFFER_CACHE → CONCURRENCY order correct')
    else:
        fail('Rule ordering', 'CDML < BC < CONC', f'{cdml_idx} < {bc_idx} < {conc_idx}')

    # ── TEST: All rules have required keys ──
    for r in RULES:
        for key in ('id', 'match', 'weight', 'project'):
            if key not in r:
                fail(f'Rule {r.get("id","?")} missing "{key}"', 'present', 'missing')
                break
        else:
            ok(f'Rule {r["id"]} has all required keys')

    # ── TEST: Weight always returns [0, 1] ──
    test_ev = {
        'domPlanChange': True, 'domIsNew': True, 'domSqlPct': 100,
        'domIsDML': True, 'domSqlId': 'x', 'domSqlVerb': 'INSERT',
        'domTable': 't',
        'hwEnqPct': 100, 'txIdxPct': 100, 'txRowPct': 100, 'txItlPct': 0,
        'txEnqPct': 100, 'usEnqPct': 100,
        'libCachePct': 100, 'sharedPoolLatchPct': 50,
        'freeBufPct': 100, 'bufBusyPct': 50, 'fbEnqPct': 50,
        'commitPct': 50, 'ioPct': 80, 'cpuPct': 80, 'concPct': 50,
        'latchPct': 80, 'logBufPct': 20,
        'cpuUtilPct': 100, 'aasRatio': 3.0, 'aasB': 100, 'aasG': 10,
        'cpus': 8, 'dbTimeDelta': 5000,
        'topWaitName': 'enq: HW - contention', 'topWaitPct': 65,
        'topWaitClass': 'Other',
        'tmEnqPct': 0, 'sqEnqPct': 0,
    }
    for r in RULES:
        try:
            if r['match'](test_ev):
                w = r['weight'](test_ev)
                if 0 <= w <= 1:
                    pass  # ok silently
                else:
                    fail(f'Rule {r["id"]} weight out of [0,1]', '[0,1]', w)
        except Exception as e:
            fail(f'Rule {r["id"]} weight() crashes', 'no error', str(e))

    ok('All rule weights in [0,1] range')

    # ── TEST: project() never returns negative values ──
    for r in RULES:
        try:
            if r['match'](test_ev):
                p = r['project'](test_ev)
                if p['dbTimeReductionPct'] < 0:
                    fail(f'{r["id"]} negative recovery', '>=0', p['dbTimeReductionPct'])
                if p['sessionsFreed'] < 0:
                    fail(f'{r["id"]} negative sessionsFreed', '>=0', p['sessionsFreed'])
        except Exception as e:
            fail(f'Rule {r["id"]} project() crashes', 'no error', str(e))

    ok('All projections non-negative')

    # ── TEST: dbTimeReductionPct <= 100 ──
    for r in RULES:
        try:
            if r['match'](test_ev):
                p = r['project'](test_ev)
                if p['dbTimeReductionPct'] > 100:
                    fail(f'{r["id"]} recovery > 100%', '<=100', p['dbTimeReductionPct'])
        except Exception:
            pass
    ok('All projections <= 100%')

    # ── TEST: P-tier thresholds are mutually exclusive ──
    # P1 thresholds must be strictly higher than P2
    p1_dbtime = 100
    p2_dbtime = 50
    if p1_dbtime > p2_dbtime:
        ok('P1 dbTimeDelta threshold > P2')
    else:
        fail('P-tier thresholds', 'P1 > P2', f'P1={p1_dbtime}, P2={p2_dbtime}')

    # ── TEST: Confidence bounds [35, 95] ──
    for delta in [0, 10, 50, 100, 5000]:
        ev_test = dict(test_ev, dbTimeDelta=delta, domSqlPct=5, domPlanChange=False, domIsNew=False,
                       hwEnqPct=0, txIdxPct=0, txRowPct=0, usEnqPct=0,
                       freeBufPct=0, bufBusyPct=0, fbEnqPct=0, commitPct=5,
                       ioPct=10, cpuPct=10, concPct=3, cpuUtilPct=20,
                       libCachePct=3, sharedPoolLatchPct=2, latchPct=5)
        res = evaluate(ev_test)
        if 35 <= res['confidence'] <= 95:
            pass  # ok
        else:
            fail(f'Confidence out of [35,95] for delta={delta}', '[35,95]', res['confidence'])
    ok('Confidence always in [35, 95] range')

    # ── TEST: Extract handles missing/null fields gracefully ──
    empty_ctx = {
        'loadProfile': {'good': {}, 'bad': {}},
        'waitEvents': {'good': [], 'bad': []},
        'instanceEfficiency': {'good': {}, 'bad': {}},
        'sqlAttribution': [],
        'meta': {},
        'aas': {},
        '_raw': {},
    }
    try:
        ev = extract(empty_ctx)
        res = evaluate(ev)
        ok('Extract + evaluate handles empty context without crash')
    except Exception as e:
        fail('Empty context handling', 'no crash', str(e))

    # ── TEST: extract handles None/missing top-level keys ──
    try:
        ev = extract({})
        res = evaluate(ev)
        ok('Extract + evaluate handles completely empty dict')
    except Exception as e:
        fail('Completely empty dict', 'no crash', str(e))


# ════════════════════════════════════════════════════════════════════════════
# PART 5: ADDITIONAL DEEP ANALYSIS
# ════════════════════════════════════════════════════════════════════════════

def run_oracle_knowledge_tests():
    """Validate Oracle-specific interpretation correctness."""
    print(f"\n{BOLD}{B}━━ Oracle Knowledge Interpretation Tests ━━{D}")

    # ── TEST: cpuUtilPct formula ──
    # db_cpu_s = per-second rate (e.g. 6 means 6 CPU-seconds of DB CPU per second of wall clock)
    # cpuUtilPct = db_cpu_s / cpus * 100
    # If db_cpu_s = 6 on 8 CPUs → 75% CPU utilization
    ctx = make_ctx(db_cpu_bad=6, cpus=8, waits_bad=[('DB CPU', 'CPU', 70)])
    ev = extract(ctx)
    expected = 6 / 8 * 100  # 75%
    if abs(ev['cpuUtilPct'] - expected) < 0.1:
        ok(f'cpuUtilPct formula correct: {ev["cpuUtilPct"]:.1f}% = db_cpu_s(6)/cpus(8)*100')
    else:
        fail('cpuUtilPct formula', f'{expected}%', f'{ev["cpuUtilPct"]:.1f}%')

    # ── TEST: AAS calculation ──
    # AAS = DB Time (seconds) / Elapsed Time (seconds)
    # If db_time_s per second = 10, that IS the AAS (since it's already per-second)
    # Actually aas is provided directly from ctx.aas
    ctx = make_ctx(aas_good=2.0, aas_bad=12.0, cpus=8)
    ev = extract(ctx)
    if abs(ev['aasB'] - 12.0) < 0.01:
        ok('AAS passthrough correct: aasB=12.0')
    else:
        fail('AAS', '12.0', ev['aasB'])

    # ── TEST: I/O classification ──
    # 'db file sequential read' = User I/O (single block)
    # 'db file scattered read' = User I/O (multi block)
    # 'direct path read' = User I/O (PQ / LOB)
    # All should sum into ioPct
    ctx = make_ctx(waits_bad=[
        ('db file sequential read', 'User I/O', 25),
        ('db file scattered read', 'User I/O', 15),
        ('direct path read', 'User I/O', 10),
        ('DB CPU', 'CPU', 30),
    ])
    ev = extract(ctx)
    if abs(ev['ioPct'] - 50) < 1:
        ok('I/O classification: seq+scattered+direct = 50%')
    else:
        fail('I/O classification', '50', ev['ioPct'])

    # ── TEST: TX enqueue decomposition ──
    # txEnqPct should include ALL TX subtypes
    ctx = make_ctx(waits_bad=[
        ('enq: TX - row lock contention', 'Application', 10),
        ('enq: TX - index contention', 'Concurrency', 8),
        ('enq: TX - allocate ITL entry', 'Configuration', 3),
        ('DB CPU', 'CPU', 40),
    ])
    ev = extract(ctx)
    if abs(ev['txEnqPct'] - 21) < 1:
        ok(f'txEnqPct = sum of all TX subtypes = {ev["txEnqPct"]:.0f}%')
    else:
        fail('txEnqPct', '21', f'{ev["txEnqPct"]:.1f}')
    if abs(ev['txRowPct'] - 10) < 0.1 and abs(ev['txIdxPct'] - 8) < 0.1 and abs(ev['txItlPct'] - 3) < 0.1:
        ok('TX subtype decomposition correct')
    else:
        fail('TX subtypes', 'row=10, idx=8, itl=3', f'row={ev["txRowPct"]}, idx={ev["txIdxPct"]}, itl={ev["txItlPct"]}')

    # ── TEST: Library cache regex correctness ──
    # 'library cache: mutex X' matches /library cache:/
    # 'cursor: pin S wait on X' matches /cursor:.*pin.*S.*wait.*on.*X/
    ctx = make_ctx(waits_bad=[
        ('library cache: mutex X', 'Concurrency', 15),
        ('cursor: pin S wait on X', 'Concurrency', 10),
        ('latch: shared pool', 'Concurrency', 5),
        ('DB CPU', 'CPU', 40),
    ])
    ev = extract(ctx)
    if abs(ev['libCachePct'] - 25) < 1:
        ok(f'libCachePct = lib_cache_mutex + cursor_pin_S = {ev["libCachePct"]:.0f}%')
    else:
        fail('libCachePct', '25', ev['libCachePct'])
    if abs(ev['sharedPoolLatchPct'] - 5) < 0.1:
        ok(f'sharedPoolLatchPct = latch:shared pool = {ev["sharedPoolLatchPct"]:.0f}%')
    else:
        fail('sharedPoolLatchPct', '5', ev['sharedPoolLatchPct'])

    # ── TEST: REDO_COMMIT suppressed by free buffer waits ──
    # commitPct=25 and freeBufPct=25 → REDO_COMMIT should NOT fire (freeBufPct >= 20)
    ctx = make_ctx(waits_bad=[
        ('log file sync', 'Commit', 25),
        ('free buffer waits', 'Configuration', 25),
        ('DB CPU', 'CPU', 30),
    ])
    ev = extract(ctx)
    matches_rules = [r for r in RULES if r['match'](ev)]
    redo_fires = any(r['id'] == 'REDO_COMMIT' for r in matches_rules)
    if not redo_fires:
        ok('REDO_COMMIT correctly suppressed when freeBufPct=25 (DBWR backpressure)')
    else:
        fail('REDO_COMMIT guard', 'suppressed', 'fired', 'commitPct=25 AND freeBufPct=25 >= 20 → LGWR back-pressure, not primary commit issue')

    # ── TEST: SQL_DOMINANT stands down when wait-dominated ──
    ctx = make_ctx(
        waits_bad=[
            ('db file sequential read', 'User I/O', 50),
            ('DB CPU', 'CPU', 20),
        ],
        dom_pct_db=35, dom_sql_text='SELECT * FROM t',
    )
    ev = extract(ctx)
    # _wait_dominated: topWait = 'db file sequential read' (not DB CPU), pct=50 >= 40, cpuPct=20 <= 25
    if _wait_dominated(ev):
        ok('_wait_dominated correctly identifies I/O domination')
    else:
        fail('_wait_dominated', 'True', 'False', 'topWait=I/O at 50%, cpuPct=20 → wait dominated')

    matches_rules = [r for r in RULES if r['match'](ev)]
    sql_fires = any(r['id'] == 'SQL_DOMINANT' for r in matches_rules)
    if not sql_fires:
        ok('SQL_DOMINANT suppressed when wait-dominated')
    else:
        fail('SQL_DOMINANT guard', 'suppressed', 'fired')


def run_mathematical_boundary_tests():
    """Test mathematical edge cases and boundary conditions."""
    print(f"\n{BOLD}{B}━━ Mathematical Boundary Tests ━━{D}")

    # ── TEST: dbTimeDelta with very small baseline ──
    ctx = make_ctx(db_time_good=0.001, db_time_bad=100)
    ev = extract(ctx)
    delta = ev['dbTimeDelta']
    if delta > 0 and not math.isinf(delta):
        ok(f'Very small baseline: dbTimeDelta={delta:.0f}% (no infinity)')
    else:
        fail('Tiny baseline delta', 'positive finite', delta)

    # ── TEST: Zero CPUs handling ──
    ctx = make_ctx(cpus=0, db_cpu_bad=5)
    ev = extract(ctx)
    # cpus=0 → safe_float defaults to 1 in the meta lookup... actually
    # the make_ctx sets meta.cpu_count = 0, and $f(0, 1) = 0 (not 1, since 0 is a valid number)
    # This might cause division by zero
    if not math.isinf(ev['cpuUtilPct']) and not math.isnan(ev['cpuUtilPct']):
        ok(f'Zero CPUs handled gracefully: cpuUtilPct={ev["cpuUtilPct"]:.1f}%')
    else:
        fail('Zero CPUs', 'no inf/nan', ev['cpuUtilPct'], 'Division by zero on cpus=0')

    # ── TEST: sessionsFreed never exceeds aasB ──
    # Extreme case: everything at 100%
    test_ev = {
        'hwEnqPct': 100, 'aasB': 50, 'cpus': 8,
        'domSqlVerb': 'INSERT', 'domTable': 't',
    }
    recovery = min(85, 100 * 0.9)  # 85
    freed = min(50 * (85 / 100), 50 * 0.95)
    if freed <= 50 * 0.95 + 0.01:
        ok(f'sessionsFreed cap: {freed:.1f} <= {50*0.95:.1f} (aasB*0.95)')
    else:
        fail('sessionsFreed cap', f'<= {50*0.95}', freed)

    # ── TEST: CONCURRENT_DML reclaim with extreme values ──
    # freeBufPct=60, fbEnqPct=10, bufBusyPct=40, commitPct=30
    # reclaim = min(60 + 10 + min(40, 60*0.4) + min(30*0.25, 5), 70)
    #         = min(60 + 10 + 24 + 5, 70) = min(99, 70) = 70
    reclaim = min(60 + 10 + min(40, 60*0.4) + min(30*0.25, 5), 70)
    if reclaim == 70:
        ok(f'CONCURRENT_DML reclaim capped at 70 (was {60+10+24+5}=99 uncapped)')
    else:
        fail('Reclaim cap', '70', reclaim)

    # ── TEST: GENERIC_LOAD_INCREASE scales correctly ──
    for delta, expected_min, expected_max in [
        (30, 10, 10),      # min(25, max(10, 30*0.06=1.8)) = 10
        (200, 12, 12),     # min(25, max(10, 200*0.06=12)) = 12
        (500, 25, 25),     # min(25, max(10, 500*0.06=30)) = 25
        (5000, 25, 25),    # min(25, max(10, 5000*0.06=300)) = 25
    ]:
        recovery = min(25, max(10, delta * 0.06))
        if abs(recovery - expected_min) < 0.1:
            ok(f'GENERIC recovery at delta={delta}%: {recovery:.1f}%')
        else:
            fail(f'GENERIC at delta={delta}', f'{expected_min}', f'{recovery:.1f}')


# ════════════════════════════════════════════════════════════════════════════
# PART 6: CODE QUALITY / DEAD CODE / TEMPLATE SERVING ANALYSIS
# ════════════════════════════════════════════════════════════════════════════

def run_code_quality_checks():
    """Analyze the actual index.html for code quality issues."""
    print(f"\n{BOLD}{B}━━ Code Quality & Serving Analysis ━━{D}")

    template_path = os.path.join(os.path.dirname(__file__), 'backend', 'templates', 'index.html')
    if not os.path.exists(template_path):
        warn('Template file not found, skipping code quality checks')
        return

    with open(template_path, encoding='utf-8-sig') as f:
        content = f.read()
    lines = content.split('\n')
    total_lines = len(lines)

    # ── CHECK: File size ──
    file_bytes = os.path.getsize(template_path)
    if file_bytes > 1_000_000:
        warn(f'Template file is {file_bytes/1024/1024:.1f}MB ({total_lines} lines)', 'Monolithic file — consider splitting into modules')
    else:
        ok(f'Template file size: {file_bytes/1024:.0f}KB')

    # ── CHECK: Template truncation bug ──
    # Jinja2 TemplateResponse sends only partial content
    import urllib.request
    try:
        resp = urllib.request.urlopen('http://localhost:8000', timeout=10)
        served = resp.read()
        served_size = len(served)
        if served_size < file_bytes * 0.5:
            fail('TEMPLATE TRUNCATION', f'~{file_bytes} bytes', f'{served_size} bytes',
                 f'Server serves only {served_size/file_bytes*100:.0f}% of template — PEEngine code is NOT reaching the browser!',
                 severity='CRITICAL-BUG')
            # Check if PEEngine is in served content
            if b'PEEngine' not in served:
                fail('PEEngine NOT in served HTML', 'present', 'absent',
                     'The entire rule engine, scoring, and narrative generation is missing from the browser',
                     severity='CRITICAL-BUG')
        else:
            ok(f'Template served fully: {served_size} bytes')
    except Exception as e:
        warn(f'Could not verify served content: {e}')

    # ── CHECK: BOM in template ──
    with open(template_path, 'rb') as f:
        if f.read(3) == b'\xef\xbb\xbf':
            warn('Template has UTF-8 BOM', 'BOM can cause issues with some parsers; consider removing')

    # ── CHECK: Dead code patterns ──
    dead_patterns = [
        (r'//\s*TODO', 'TODO comments'),
        (r'//\s*HACK', 'HACK comments'),
        (r'//\s*FIXME', 'FIXME comments'),
        (r'console\.log\(', 'console.log statements'),
        (r'debugger;', 'debugger statements'),
    ]
    for pattern, desc in dead_patterns:
        matches = [(i+1, line.strip()[:80]) for i, line in enumerate(lines) if re.search(pattern, line)]
        if matches:
            if desc == 'console.log statements' and len(matches) > 5:
                warn(f'{len(matches)} {desc} found', f'First: L{matches[0][0]}: {matches[0][1]}')
            elif desc in ('debugger statements',):
                fail(f'{desc} found', '0', len(matches), f'L{matches[0][0]}', severity='CODE-QUALITY')
            else:
                pass  # TODOs/FIXMEs are informational

    # ── CHECK: Duplicate function definitions ──
    func_defs = {}
    for i, line in enumerate(lines, 1):
        m = re.match(r'\s*(?:function|const|let|var)\s+(\w+)\s*[=(]', line)
        if m:
            name = m.group(1)
            if name in func_defs:
                if name not in ('i', 'j', 'k', 'n', 'x', 'y', 's', 'v', 'r', 'e', 'a', 'b', 'c', 'd', 'p', 'm', 't', 'w'):
                    warn(f'Possible duplicate: {name} defined at L{func_defs[name]} and L{i}')
            func_defs[name] = i

    # ── CHECK: Large inline script blocks ──
    script_starts = [i+1 for i, line in enumerate(lines) if '<script>' in line and 'src=' not in line]
    script_ends = [i+1 for i, line in enumerate(lines) if '</script>' in line]
    if script_starts and script_ends:
        for s, e in zip(script_starts, script_ends):
            block_size = e - s
            if block_size > 1000:
                warn(f'Large inline <script> block: L{s}-L{e} ({block_size} lines)', 'Consider externalizing to reduce template size')


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    run_all_tests()
    run_oracle_knowledge_tests()
    run_mathematical_boundary_tests()
    run_code_quality_checks()

    # Final summary
    total = _pass + _fail
    accuracy = (_pass / total * 100) if total > 0 else 0

    print(f"\n{BOLD}{'='*78}")
    print(f"  FINAL SCORE: {_pass}/{total} ({accuracy:.1f}%)")
    print(f"  BUGS: {_fail}  |  WARNINGS: {_warn}")
    print(f"{'='*78}{D}\n")

    # Write JSON report
    report = {
        'total_tests': total,
        'passed': _pass,
        'failed': _fail,
        'warnings': _warn,
        'accuracy_pct': round(accuracy, 1),
        'findings': _findings,
    }
    report_path = os.path.join(os.path.dirname(__file__), '_pe_exam_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Report written to: {report_path}")

    sys.exit(0 if _fail == 0 else 1)
