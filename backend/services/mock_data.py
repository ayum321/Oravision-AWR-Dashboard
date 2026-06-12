"""Realistic AWR mock data for development and testing.

Provides two complete datasets:
- Good period: healthy Oracle database with normal performance
- Bad period: clear regression with parsing storms, I/O saturation, contention
"""
from __future__ import annotations

from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Snapshot catalogue (shared between good and bad periods)
# ---------------------------------------------------------------------------

def get_mock_snapshots() -> list[dict]:
    """Return 20 snapshot records spanning 20 hours at 1-hour intervals."""
    base = datetime(2026, 3, 27, 0, 0, 0)
    snapshots = []
    for i in range(20):
        begin = base + timedelta(hours=i)
        end = begin + timedelta(hours=1)
        snapshots.append({
            "snap_id": 48100 + i,
            "begin_time": begin.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_mins": 60.0,
        })
    return snapshots


# ---------------------------------------------------------------------------
# Common header fields
# ---------------------------------------------------------------------------

_COMMON_HEADER: dict = {
    "db_name": "PRODDB",
    "db_id": "2849301746",
    "instance": "PRODDB1",
    "release": "19.21.0.0.0",
    "host": "ora-prod-01.example.com",
    "cpus": 16,
    "memory_gb": 128.0,
    "platform": "Linux x86 64-bit",
    "rac": "NO",
}


# ---------------------------------------------------------------------------
# GOOD period
# ---------------------------------------------------------------------------

def _build_good_data() -> dict:
    data = dict(_COMMON_HEADER)
    data.update({
        "begin_snap": 48100,
        "end_snap": 48101,
        "begin_time": "2026-03-27 08:00:00",
        "end_time": "2026-03-27 09:00:00",
        "elapsed_min": 60.0,
        "db_time_min": 45.0,
        "sessions_begin": 142,
        "sessions_end": 148,
    })

    # --- Instance Efficiency ---
    data["efficiency"] = {
        "buffer_cache_hit_pct": 99.1,
        "library_cache_hit_pct": 99.4,
        "soft_parse_pct": 97.3,
        "execute_to_parse_pct": 92.1,
        "latch_hit_pct": 99.92,
    }

    # --- Load Profile ---
    data["load_profile"] = [
        {"stat_name": "Logical Reads",     "per_sec": 12400.0,   "per_txn": 68.9},
        {"stat_name": "Physical Reads",    "per_sec": 340.0,     "per_txn": 1.89},
        {"stat_name": "Redo Size (bytes)", "per_sec": 2202009.6, "per_txn": 12233.4},  # ~2.1 MB/s
        {"stat_name": "User Commits",      "per_sec": 180.0,     "per_txn": 1.0},
        {"stat_name": "User Rollbacks",    "per_sec": 2.1,       "per_txn": 0.012},
        {"stat_name": "Parses",            "per_sec": 620.0,     "per_txn": 3.44},
        {"stat_name": "Hard Parses",       "per_sec": 12.0,      "per_txn": 0.067},
        {"stat_name": "Block Changes",     "per_sec": 4820.0,    "per_txn": 26.8},
        {"stat_name": "User Calls",        "per_sec": 2100.0,    "per_txn": 11.67},
        {"stat_name": "Executes",          "per_sec": 8100.0,    "per_txn": 45.0},
        {"stat_name": "Logons",            "per_sec": 0.5,       "per_txn": 0.003},
    ]

    # --- Session/Logon metrics (Instance Activity Stats) ---
    data["logons_cumulative_total"] = 1800.0       # 0.5/s × 3600s
    data["logons_current_begin"] = 245.0
    data["logons_current_end"] = 248.0              # +3 net sessions

    # --- Top Wait Events ---
    data["wait_events"] = [
        {
            "event_name": "DB CPU",
            "total_waits": 0,
            "time_waited_secs": 1134.0,      # 42% of 2700s db_time
            "avg_wait_ms": 0.0,
            "pct_db_time": 42.0,
            "wait_class": "CPU",
        },
        {
            "event_name": "db file sequential read",
            "total_waits": 312400,
            "time_waited_secs": 486.0,       # 18%
            "avg_wait_ms": 3.2,
            "pct_db_time": 18.0,
            "wait_class": "User I/O",
        },
        {
            "event_name": "log file sync",
            "total_waits": 64800,
            "time_waited_secs": 135.0,       # 5%
            "avg_wait_ms": 2.1,
            "pct_db_time": 5.0,
            "wait_class": "Commit",
        },
        {
            "event_name": "db file scattered read",
            "total_waits": 9640,
            "time_waited_secs": 81.0,        # 3%
            "avg_wait_ms": 8.4,
            "pct_db_time": 3.0,
            "wait_class": "User I/O",
        },
        {
            "event_name": "read by other session",
            "total_waits": 4200,
            "time_waited_secs": 40.5,        # 1.5%
            "avg_wait_ms": 9.6,
            "pct_db_time": 1.5,
            "wait_class": "User I/O",
        },
        {
            "event_name": "direct path read",
            "total_waits": 2100,
            "time_waited_secs": 27.0,        # 1%
            "avg_wait_ms": 12.9,
            "pct_db_time": 1.0,
            "wait_class": "User I/O",
        },
    ]

    # --- SQL Statistics (top 10 by elapsed time) ---
    data["sql_stats"] = [
        {
            "sql_id": "a3f8c71bd29e4",
            "sql_text": "SELECT o.order_id, c.customer_name, p.product_name FROM orders o JOIN customers c ON ...",
            "executions": 42000,
            "elapsed_time_secs": 216.0,       # ~8% db_time
            "cpu_time_secs": 182.4,
            "disk_reads": 18400,
            "buffer_gets": 2940000,
            "avg_elapsed_secs": 0.00514,
        },
        {
            "sql_id": "b9d2e04fc81a7",
            "sql_text": "UPDATE inventory SET qty_on_hand = qty_on_hand - :1 WHERE product_id = :2 AND warehouse...",
            "executions": 18500,
            "elapsed_time_secs": 148.2,
            "cpu_time_secs": 98.4,
            "disk_reads": 12200,
            "buffer_gets": 1480000,
            "avg_elapsed_secs": 0.00801,
        },
        {
            "sql_id": "c4e7a29d0f3b2",
            "sql_text": "SELECT /*+ INDEX(t idx_txn_date) */ t.txn_id, t.amount FROM transactions t WHERE t.txn_...",
            "executions": 86400,
            "elapsed_time_secs": 129.6,
            "cpu_time_secs": 112.8,
            "disk_reads": 4100,
            "buffer_gets": 4320000,
            "avg_elapsed_secs": 0.0015,
        },
        {
            "sql_id": "d1f5b83ec72d6",
            "sql_text": "INSERT INTO audit_log (event_id, event_type, event_time, user_id, details) VALUES (:1,...",
            "executions": 324000,
            "elapsed_time_secs": 97.2,
            "cpu_time_secs": 81.0,
            "disk_reads": 0,
            "buffer_gets": 1620000,
            "avg_elapsed_secs": 0.0003,
        },
        {
            "sql_id": "e8a4d67b1c9f0",
            "sql_text": "SELECT account_balance, last_activity FROM accounts WHERE account_id = :1 FOR UPDATE N...",
            "executions": 9200,
            "elapsed_time_secs": 82.8,
            "cpu_time_secs": 48.6,
            "disk_reads": 7400,
            "buffer_gets": 276000,
            "avg_elapsed_secs": 0.009,
        },
        {
            "sql_id": "f2c9e15a4d80b",
            "sql_text": "MERGE INTO daily_summary ds USING (SELECT product_id, SUM(amount) total FROM orders WH...",
            "executions": 24,
            "elapsed_time_secs": 72.0,
            "cpu_time_secs": 64.8,
            "disk_reads": 82000,
            "buffer_gets": 2160000,
            "avg_elapsed_secs": 3.0,
        },
        {
            "sql_id": "07b3d9a2e6f14",
            "sql_text": "SELECT p.plan_id, p.plan_name FROM subscription_plans p WHERE p.status = 'ACTIVE' AND ...",
            "executions": 54000,
            "elapsed_time_secs": 54.0,
            "cpu_time_secs": 48.6,
            "disk_reads": 2700,
            "buffer_gets": 810000,
            "avg_elapsed_secs": 0.001,
        },
        {
            "sql_id": "18c4e0f7b5a23",
            "sql_text": "DELETE FROM session_tokens WHERE expiry_time < SYSDATE - INTERVAL '7' DAY",
            "executions": 6,
            "elapsed_time_secs": 48.0,
            "cpu_time_secs": 36.0,
            "disk_reads": 24000,
            "buffer_gets": 960000,
            "avg_elapsed_secs": 8.0,
        },
        {
            "sql_id": "29d5f1a8c6b34",
            "sql_text": "SELECT region_id, SUM(revenue) FROM sales_fact WHERE fiscal_year = :1 GROUP BY region_i...",
            "executions": 120,
            "elapsed_time_secs": 42.0,
            "cpu_time_secs": 38.4,
            "disk_reads": 54000,
            "buffer_gets": 1800000,
            "avg_elapsed_secs": 0.35,
        },
        {
            "sql_id": "3ae6012b9d7c5",
            "sql_text": "SELECT username, email, last_login FROM users u WHERE u.org_id = :1 ORDER BY u.last_lo...",
            "executions": 32400,
            "elapsed_time_secs": 32.4,
            "cpu_time_secs": 29.2,
            "disk_reads": 1600,
            "buffer_gets": 648000,
            "avg_elapsed_secs": 0.001,
        },
    ]

    # --- OS Statistics ---
    data["os_stats"] = {
        "num_cpus": 16,
        "cpu_busy_pct": 45.0,
        "iowait_pct": 5.0,
        "phys_mem_gb": 128.0,
        "free_mem_gb": 42.0,
    }

    # --- Time Model ---
    data["time_model"] = [
        {"stat_name": "DB time",                  "time_secs": 2700.0,  "pct_db_time": 100.0},
        {"stat_name": "DB CPU",                   "time_secs": 1134.0,  "pct_db_time": 42.0},
        {"stat_name": "sql execute elapsed time",  "time_secs": 918.0,   "pct_db_time": 34.0},
        {"stat_name": "parse time elapsed",        "time_secs": 162.0,   "pct_db_time": 6.0},
        {"stat_name": "hard parse elapsed time",   "time_secs": 40.5,    "pct_db_time": 1.5},
        {"stat_name": "PL/SQL execution elapsed time", "time_secs": 108.0, "pct_db_time": 4.0},
        {"stat_name": "connection management call elapsed time", "time_secs": 27.0, "pct_db_time": 1.0},
        {"stat_name": "sequence load elapsed time", "time_secs": 5.4,    "pct_db_time": 0.2},
    ]

    # --- ASH Summary ---
    data["ash_summary"] = [
        {"session_state": "ON CPU",     "wait_class": "",           "event": "",                        "sample_count": 5040, "pct": 42.0},
        {"session_state": "WAITING",    "wait_class": "User I/O",  "event": "db file sequential read", "sample_count": 2160, "pct": 18.0},
        {"session_state": "WAITING",    "wait_class": "Commit",    "event": "log file sync",           "sample_count": 600,  "pct": 5.0},
        {"session_state": "WAITING",    "wait_class": "User I/O",  "event": "db file scattered read",  "sample_count": 360,  "pct": 3.0},
        {"session_state": "WAITING",    "wait_class": "User I/O",  "event": "read by other session",   "sample_count": 180,  "pct": 1.5},
        {"session_state": "WAITING",    "wait_class": "User I/O",  "event": "direct path read",        "sample_count": 120,  "pct": 1.0},
        {"session_state": "WAITING",    "wait_class": "Network",   "event": "SQL*Net message from dblink", "sample_count": 84, "pct": 0.7},
        {"session_state": "WAITING",    "wait_class": "Other",     "event": "latch free",              "sample_count": 48,   "pct": 0.4},
    ]

    # --- SGA Components ---
    data["sga"] = [
        {"component": "Database Buffers",  "current_size_mb": 32768.0, "min_size_mb": 32768.0, "max_size_mb": 32768.0},
        {"component": "Shared Pool",       "current_size_mb": 8192.0,  "min_size_mb": 8192.0,  "max_size_mb": 8192.0},
        {"component": "Large Pool",        "current_size_mb": 1024.0,  "min_size_mb": 1024.0,  "max_size_mb": 1024.0},
        {"component": "Java Pool",         "current_size_mb": 512.0,   "min_size_mb": 512.0,   "max_size_mb": 512.0},
        {"component": "Streams Pool",      "current_size_mb": 256.0,   "min_size_mb": 256.0,   "max_size_mb": 256.0},
        {"component": "Redo Buffers",      "current_size_mb": 128.0,   "min_size_mb": 128.0,   "max_size_mb": 128.0},
    ]

    # --- Segment Statistics (top 10) ---
    data["segments"] = [
        {"object_name": "ORDERS",             "object_type": "TABLE",  "logical_reads": 4200000,  "physical_reads": 82000,  "physical_writes": 24000},
        {"object_name": "ORDERS_PK",          "object_type": "INDEX",  "logical_reads": 2940000,  "physical_reads": 18400,  "physical_writes": 0},
        {"object_name": "INVENTORY",          "object_type": "TABLE",  "logical_reads": 1890000,  "physical_reads": 46000,  "physical_writes": 18500},
        {"object_name": "TRANSACTIONS",       "object_type": "TABLE",  "logical_reads": 1620000,  "physical_reads": 12200,  "physical_writes": 8400},
        {"object_name": "IDX_TXN_DATE",       "object_type": "INDEX",  "logical_reads": 1440000,  "physical_reads": 4100,   "physical_writes": 0},
        {"object_name": "AUDIT_LOG",          "object_type": "TABLE",  "logical_reads": 980000,   "physical_reads": 0,      "physical_writes": 32400},
        {"object_name": "ACCOUNTS",           "object_type": "TABLE",  "logical_reads": 840000,   "physical_reads": 7400,   "physical_writes": 4600},
        {"object_name": "DAILY_SUMMARY",      "object_type": "TABLE",  "logical_reads": 720000,   "physical_reads": 54000,  "physical_writes": 12000},
        {"object_name": "SALES_FACT",         "object_type": "TABLE",  "logical_reads": 680000,   "physical_reads": 48000,  "physical_writes": 0},
        {"object_name": "IDX_ORDERS_CUST",    "object_type": "INDEX",  "logical_reads": 540000,   "physical_reads": 6200,   "physical_writes": 0},
    ]

    return data


# ---------------------------------------------------------------------------
# BAD period  (clear regression: parsing storm, I/O saturation, contention)
# ---------------------------------------------------------------------------

def _build_bad_data() -> dict:
    data = dict(_COMMON_HEADER)
    data.update({
        "begin_snap": 48110,
        "end_snap": 48111,
        "begin_time": "2026-03-27 18:00:00",
        "end_time": "2026-03-27 19:00:00",
        "elapsed_min": 60.0,
        "db_time_min": 280.0,
        "sessions_begin": 148,
        "sessions_end": 312,
    })

    # --- Instance Efficiency ---
    data["efficiency"] = {
        "buffer_cache_hit_pct": 87.4,
        "library_cache_hit_pct": 91.2,
        "soft_parse_pct": 61.2,
        "execute_to_parse_pct": 42.8,
        "latch_hit_pct": 97.3,
    }

    # --- Load Profile ---
    data["load_profile"] = [
        {"stat_name": "Logical Reads",     "per_sec": 48200.0,     "per_txn": 141.8},
        {"stat_name": "Physical Reads",    "per_sec": 8400.0,      "per_txn": 24.7},
        {"stat_name": "Redo Size (bytes)", "per_sec": 13002342.4,  "per_txn": 38242.2},  # ~12.4 MB/s
        {"stat_name": "User Commits",      "per_sec": 340.0,       "per_txn": 1.0},
        {"stat_name": "User Rollbacks",    "per_sec": 24.0,        "per_txn": 0.071},
        {"stat_name": "Parses",            "per_sec": 4200.0,      "per_txn": 12.35},
        {"stat_name": "Hard Parses",       "per_sec": 1840.0,      "per_txn": 5.41},
        {"stat_name": "Block Changes",     "per_sec": 18400.0,     "per_txn": 54.1},
        {"stat_name": "User Calls",        "per_sec": 9800.0,      "per_txn": 28.8},
        {"stat_name": "Executes",          "per_sec": 14200.0,     "per_txn": 41.8},
        {"stat_name": "Logons",            "per_sec": 12.8,        "per_txn": 0.038},
    ]

    # --- Session/Logon metrics (Instance Activity Stats) ---
    data["logons_cumulative_total"] = 46080.0      # 12.8/s × 3600s — massive logon rate
    data["logons_current_begin"] = 248.0
    data["logons_current_end"] = 2749.0             # +2501 net sessions — session leak!

    # --- Top Wait Events ---
    # db_time = 280 min = 16800 s
    data["wait_events"] = [
        {
            "event_name": "latch: shared pool",
            "total_waits": 8420000,
            "time_waited_secs": 5208.0,      # 31%
            "avg_wait_ms": 0.62,
            "pct_db_time": 31.0,
            "wait_class": "Concurrency",
        },
        {
            "event_name": "DB CPU",
            "total_waits": 0,
            "time_waited_secs": 4704.0,      # 28%
            "avg_wait_ms": 0.0,
            "pct_db_time": 28.0,
            "wait_class": "CPU",
        },
        {
            "event_name": "db file sequential read",
            "total_waits": 972000,
            "time_waited_secs": 3696.0,      # 22%
            "avg_wait_ms": 38.0,
            "pct_db_time": 22.0,
            "wait_class": "User I/O",
        },
        {
            "event_name": "buffer busy waits",
            "total_waits": 1640000,
            "time_waited_secs": 1344.0,      # 8%
            "avg_wait_ms": 0.82,
            "pct_db_time": 8.0,
            "wait_class": "Concurrency",
        },
        {
            "event_name": "log file sync",
            "total_waits": 122400,
            "time_waited_secs": 1008.0,      # 6%
            "avg_wait_ms": 24.0,
            "pct_db_time": 6.0,
            "wait_class": "Commit",
        },
        {
            "event_name": "enq: TX - row lock contention",
            "total_waits": 18400,
            "time_waited_secs": 672.0,        # 4%
            "avg_wait_ms": 36.5,
            "pct_db_time": 4.0,
            "wait_class": "Application",
        },
        {
            "event_name": "cursor: pin S wait on X",
            "total_waits": 284000,
            "time_waited_secs": 336.0,        # 2%
            "avg_wait_ms": 1.18,
            "pct_db_time": 2.0,
            "wait_class": "Concurrency",
        },
        {
            "event_name": "library cache lock",
            "total_waits": 142000,
            "time_waited_secs": 252.0,        # 1.5%
            "avg_wait_ms": 1.77,
            "pct_db_time": 1.5,
            "wait_class": "Concurrency",
        },
    ]

    # --- SQL Statistics (top 10 by elapsed – regressions + new offenders) ---
    data["sql_stats"] = [
        {
            # NEW OFFENDER: untuned ad-hoc query flooding shared pool
            "sql_id": "x7k2m9p4qr1s8",
            "sql_text": "SELECT * FROM orders WHERE TO_CHAR(order_date, 'YYYY-MM-DD') = '2026-03-27' AND custo...",
            "executions": 186000,
            "elapsed_time_secs": 3024.0,      # ~18% db_time – massive new offender
            "cpu_time_secs": 1890.0,
            "disk_reads": 2480000,
            "buffer_gets": 18600000,
            "avg_elapsed_secs": 0.01626,
        },
        {
            # REGRESSION: same sql_id as good #1, 10x elapsed
            "sql_id": "a3f8c71bd29e4",
            "sql_text": "SELECT o.order_id, c.customer_name, p.product_name FROM orders o JOIN customers c ON ...",
            "executions": 48000,
            "elapsed_time_secs": 2160.0,      # was 216s -> 10x regression
            "cpu_time_secs": 720.0,
            "disk_reads": 1420000,
            "buffer_gets": 14400000,
            "avg_elapsed_secs": 0.045,
        },
        {
            # NEW OFFENDER: dynamic SQL with literals (parse storm contributor)
            "sql_id": "y8l3n0q5rs2t9",
            "sql_text": "SELECT c.credit_limit, c.balance FROM credit_accounts c WHERE c.account_num = 100384...",
            "executions": 92000,
            "elapsed_time_secs": 1848.0,
            "cpu_time_secs": 1240.0,
            "disk_reads": 644000,
            "buffer_gets": 5520000,
            "avg_elapsed_secs": 0.02009,
        },
        {
            # REGRESSION: same sql_id as good #2, 8x elapsed
            "sql_id": "b9d2e04fc81a7",
            "sql_text": "UPDATE inventory SET qty_on_hand = qty_on_hand - :1 WHERE product_id = :2 AND warehouse...",
            "executions": 24000,
            "elapsed_time_secs": 1200.0,      # was 148s -> 8x regression
            "cpu_time_secs": 360.0,
            "disk_reads": 480000,
            "buffer_gets": 4800000,
            "avg_elapsed_secs": 0.05,
        },
        {
            # REGRESSION: same sql_id as good #5, 7x elapsed (row lock heavy)
            "sql_id": "e8a4d67b1c9f0",
            "sql_text": "SELECT account_balance, last_activity FROM accounts WHERE account_id = :1 FOR UPDATE N...",
            "executions": 18400,
            "elapsed_time_secs": 920.0,       # was 82.8s -> ~11x
            "cpu_time_secs": 184.0,
            "disk_reads": 92000,
            "buffer_gets": 736000,
            "avg_elapsed_secs": 0.05,
        },
        {
            # NEW OFFENDER: full table scan on large table
            "sql_id": "z9m4o1r6st3u0",
            "sql_text": "SELECT /*+ FULL(h) */ h.hist_id, h.event_data FROM event_history h WHERE h.created_at...",
            "executions": 84,
            "elapsed_time_secs": 840.0,
            "cpu_time_secs": 252.0,
            "disk_reads": 4200000,
            "buffer_gets": 12600000,
            "avg_elapsed_secs": 10.0,
        },
        {
            # REGRESSION: same as good #3, 5x elapsed
            "sql_id": "c4e7a29d0f3b2",
            "sql_text": "SELECT /*+ INDEX(t idx_txn_date) */ t.txn_id, t.amount FROM transactions t WHERE t.txn_...",
            "executions": 92000,
            "elapsed_time_secs": 644.0,       # was 129.6s -> ~5x
            "cpu_time_secs": 322.0,
            "disk_reads": 184000,
            "buffer_gets": 9200000,
            "avg_elapsed_secs": 0.007,
        },
        {
            # REGRESSION: good #4 insert, contention on audit_log
            "sql_id": "d1f5b83ec72d6",
            "sql_text": "INSERT INTO audit_log (event_id, event_type, event_time, user_id, details) VALUES (:1,...",
            "executions": 648000,
            "elapsed_time_secs": 518.4,       # was 97.2s -> ~5x
            "cpu_time_secs": 259.2,
            "disk_reads": 64800,
            "buffer_gets": 6480000,
            "avg_elapsed_secs": 0.0008,
        },
        {
            # NEW OFFENDER: recursive SQL from hard parsing
            "sql_id": "w6j1k8n3op0q7",
            "sql_text": "SELECT obj#, type#, ctime, mtime, stime, status, dataobj#, flags, oid$, spare1, spare...",
            "executions": 1840000,
            "elapsed_time_secs": 460.0,
            "cpu_time_secs": 414.0,
            "disk_reads": 0,
            "buffer_gets": 9200000,
            "avg_elapsed_secs": 0.00025,
        },
        {
            # Same as good #6 merge but much slower due to I/O pressure
            "sql_id": "f2c9e15a4d80b",
            "sql_text": "MERGE INTO daily_summary ds USING (SELECT product_id, SUM(amount) total FROM orders WH...",
            "executions": 24,
            "elapsed_time_secs": 432.0,       # was 72s -> 6x
            "cpu_time_secs": 120.0,
            "disk_reads": 640000,
            "buffer_gets": 7200000,
            "avg_elapsed_secs": 18.0,
        },
    ]

    # --- OS Statistics ---
    data["os_stats"] = {
        "num_cpus": 16,
        "cpu_busy_pct": 94.0,
        "iowait_pct": 28.0,
        "phys_mem_gb": 128.0,
        "free_mem_gb": 4.0,
    }

    # --- Time Model ---
    # db_time = 16800s
    data["time_model"] = [
        {"stat_name": "DB time",                        "time_secs": 16800.0,  "pct_db_time": 100.0},
        {"stat_name": "DB CPU",                         "time_secs": 4704.0,   "pct_db_time": 28.0},
        {"stat_name": "sql execute elapsed time",       "time_secs": 5040.0,   "pct_db_time": 30.0},
        {"stat_name": "parse time elapsed",             "time_secs": 4536.0,   "pct_db_time": 27.0},
        {"stat_name": "hard parse elapsed time",        "time_secs": 3864.0,   "pct_db_time": 23.0},
        {"stat_name": "hard parse (sharing criteria) elapsed time", "time_secs": 1680.0, "pct_db_time": 10.0},
        {"stat_name": "PL/SQL execution elapsed time",  "time_secs": 672.0,    "pct_db_time": 4.0},
        {"stat_name": "connection management call elapsed time", "time_secs": 504.0, "pct_db_time": 3.0},
        {"stat_name": "sequence load elapsed time",     "time_secs": 168.0,    "pct_db_time": 1.0},
    ]

    # --- ASH Summary ---
    data["ash_summary"] = [
        {"session_state": "WAITING",    "wait_class": "Concurrency", "event": "latch: shared pool",       "sample_count": 18600, "pct": 31.0},
        {"session_state": "ON CPU",     "wait_class": "",            "event": "",                          "sample_count": 16800, "pct": 28.0},
        {"session_state": "WAITING",    "wait_class": "User I/O",   "event": "db file sequential read",   "sample_count": 13200, "pct": 22.0},
        {"session_state": "WAITING",    "wait_class": "Concurrency", "event": "buffer busy waits",        "sample_count": 4800,  "pct": 8.0},
        {"session_state": "WAITING",    "wait_class": "Commit",     "event": "log file sync",             "sample_count": 3600,  "pct": 6.0},
        {"session_state": "WAITING",    "wait_class": "Application", "event": "enq: TX - row lock contention", "sample_count": 2400, "pct": 4.0},
        {"session_state": "WAITING",    "wait_class": "Concurrency", "event": "cursor: pin S wait on X",  "sample_count": 1200,  "pct": 2.0},
        {"session_state": "WAITING",    "wait_class": "Concurrency", "event": "library cache lock",       "sample_count": 900,   "pct": 1.5},
    ]

    # --- SGA Components (same allocation but under pressure) ---
    data["sga"] = [
        {"component": "Database Buffers",  "current_size_mb": 32768.0, "min_size_mb": 32768.0, "max_size_mb": 32768.0},
        {"component": "Shared Pool",       "current_size_mb": 8192.0,  "min_size_mb": 7680.0,  "max_size_mb": 8704.0},   # resized under pressure
        {"component": "Large Pool",        "current_size_mb": 1024.0,  "min_size_mb": 512.0,   "max_size_mb": 1024.0},   # shrunk and grew back
        {"component": "Java Pool",         "current_size_mb": 512.0,   "min_size_mb": 256.0,   "max_size_mb": 512.0},    # shrunk to feed shared pool
        {"component": "Streams Pool",      "current_size_mb": 256.0,   "min_size_mb": 256.0,   "max_size_mb": 256.0},
        {"component": "Redo Buffers",      "current_size_mb": 128.0,   "min_size_mb": 128.0,   "max_size_mb": 128.0},
    ]

    # --- Segment Statistics (top 10 – showing hot segments) ---
    data["segments"] = [
        {"object_name": "ORDERS",             "object_type": "TABLE",  "logical_reads": 38400000, "physical_reads": 4200000,  "physical_writes": 86000},
        {"object_name": "ORDERS_PK",          "object_type": "INDEX",  "logical_reads": 14400000, "physical_reads": 1420000,  "physical_writes": 0},
        {"object_name": "EVENT_HISTORY",      "object_type": "TABLE",  "logical_reads": 12600000, "physical_reads": 4200000,  "physical_writes": 0},
        {"object_name": "CREDIT_ACCOUNTS",    "object_type": "TABLE",  "logical_reads": 5520000,  "physical_reads": 644000,   "physical_writes": 24000},
        {"object_name": "INVENTORY",          "object_type": "TABLE",  "logical_reads": 4800000,  "physical_reads": 480000,   "physical_writes": 48000},
        {"object_name": "TRANSACTIONS",       "object_type": "TABLE",  "logical_reads": 9200000,  "physical_reads": 184000,   "physical_writes": 42000},
        {"object_name": "IDX_TXN_DATE",       "object_type": "INDEX",  "logical_reads": 4600000,  "physical_reads": 92000,    "physical_writes": 0},
        {"object_name": "AUDIT_LOG",          "object_type": "TABLE",  "logical_reads": 6480000,  "physical_reads": 64800,    "physical_writes": 648000},
        {"object_name": "ACCOUNTS",           "object_type": "TABLE",  "logical_reads": 2400000,  "physical_reads": 92000,    "physical_writes": 18400},
        {"object_name": "DAILY_SUMMARY",      "object_type": "TABLE",  "logical_reads": 7200000,  "physical_reads": 640000,   "physical_writes": 24000},
    ]

    return data


# ---------------------------------------------------------------------------
# Cached datasets (built once per import)
# ---------------------------------------------------------------------------

_GOOD_DATA: dict | None = None
_BAD_DATA: dict | None = None


def get_mock_good_data() -> dict:
    """Return AWR data dict for a healthy / good period."""
    global _GOOD_DATA
    if _GOOD_DATA is None:
        _GOOD_DATA = _build_good_data()
    return _GOOD_DATA


def get_mock_bad_data() -> dict:
    """Return AWR data dict for a regressed / bad period."""
    global _BAD_DATA
    if _BAD_DATA is None:
        _BAD_DATA = _build_bad_data()
    return _BAD_DATA


def get_mock_awr_data(period: str = "good") -> dict:
    """Return complete AWR data dict matching the AWRData pydantic model.

    Parameters
    ----------
    period : str
        ``"good"`` for healthy baseline or ``"bad"`` for regressed period.

    Returns
    -------
    dict
        Dictionary suitable for ``AWRData(**data)``.
    """
    if period.lower() == "bad":
        return get_mock_bad_data()
    return get_mock_good_data()
