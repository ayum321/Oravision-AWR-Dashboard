import math

print("=== STAFF EXPERT AUDIT: PEEngine Mathematical & Logic Verification ===\n")

# --- BUG 1: P-tier ignores dominant wait event %  ---
print("CHALLENGE 1: HW contention 90% DB Time but low dbTimeDelta")
ev = dict(dbTimeDelta=40, aasRatio=0.9, domSqlPct=20, commitPct=5, ioPct=5, hwEnqPct=90)
pTier = 'P3'
if ev['dbTimeDelta'] >= 100 or ev['aasRatio'] >= 1.5 or ev['domSqlPct'] >= 50:
    pTier = 'P1'
elif ev['dbTimeDelta'] >= 50 or ev['aasRatio'] >= 1.0 or ev['domSqlPct'] >= 30 or ev['commitPct'] >= 20 or ev['ioPct'] >= 50:
    pTier = 'P2'
print(f"  hwEnqPct=90%, dbTimeDelta=40%, aasRatio=0.9 -> P-tier: {pTier}")
print("  BUG: Should be P2 minimum. P-tier ignores hwEnqPct, txRowPct, libCachePct, freeBufPct.\n")

# --- BUG 2: TX_ROW_LOCK projection uses txEnqPct (all TX) not txRowPct ---
print("CHALLENGE 2: TX_ROW_LOCK projection vs match mismatch")
txRowPct = 10   # fires the rule
txIdxPct = 8    # also present
txItlPct = 5    # ITL waits
txEnqPct = txRowPct + txIdxPct + txItlPct   # 23%
recovery_claimed = min(70, txEnqPct * 0.7)
recovery_correct = min(70, txRowPct * 0.7)
print(f"  txRowPct={txRowPct}%, txEnqPct={txEnqPct}% (all TX types combined)")
print(f"  Claimed recovery (code uses txEnqPct): {recovery_claimed:.1f}%")
print(f"  Correct recovery (should use txRowPct): {recovery_correct:.1f}%")
print(f"  BUG: Overstates recovery by {recovery_claimed - recovery_correct:.1f}pp (x{recovery_claimed/max(recovery_correct,1):.1f})\n")

# --- BUG 3: GENERIC_LOAD_INCREASE confidence inflation  ---
print("CHALLENGE 3: Only GENERIC_LOAD_INCREASE fires (dbTimeDelta=39%)")
top_weight = min(0.45, 0.2 + 39/300)
baseConf = round(50 + top_weight * 40)
confidence = max(35, min(95, baseConf + min(1 * 3, 12)))
label = 'HIGH' if confidence >= 80 else ('LOW' if confidence < 60 else 'MEDIUM')
print(f"  top_weight={top_weight:.3f}, confidence={confidence} -> {label}")
print(f"  BUG: MEDIUM confidence shown with hardcoded 15% recovery regardless of actual data.\n")

# --- BUG 4: latchPct double-counts events also in libCachePct ---
print("CHALLENGE 4: latchPct double-counting with sharedPoolLatchPct")
libCachePct = 12
sharedPoolLatchPct = 8  # 'latch: shared pool' = 8%
# latchPct regex /latch:|cursor:.*pin/i also matches 'latch: shared pool'
latchPct_approx = libCachePct + sharedPoolLatchPct  # 20% (double-counts 8%)
lib_weight = min(1.0, 0.5 + (libCachePct + sharedPoolLatchPct) / 100)
conc_weight = min(1.0, 0.35 + latchPct_approx / 50)
print(f"  libCachePct={libCachePct}%, sharedPoolLatchPct={sharedPoolLatchPct}%")
print(f"  latchPct ~{latchPct_approx}% (includes shared pool latch already in sharedPoolLatchPct)")
print(f"  LIBRARY_CACHE_PRESSURE weight: {lib_weight:.3f}")
print(f"  CONCURRENCY weight: {conc_weight:.3f}")
print(f"  BUG: Both rules fire. latchPct inflated by double-counting.\n")

# --- BUG 5: CONCURRENT_DML reclaim double-counts downstream symptoms ---
print("CHALLENGE 5: CONCURRENT_DML reclaim sums correlated waits as independent costs")
freeBufPct = 22; fbEnqPct = 5; bufBusyPct = 18; commitPct = 15
reclaim = min(freeBufPct + fbEnqPct + bufBusyPct + commitPct * 0.5, 80)
print(f"  freeBufPct={freeBufPct}% + fbEnqPct={fbEnqPct}% + bufBusyPct={bufBusyPct}%(downstream) + commitPct*0.5={commitPct*0.5}%(downstream)")
print(f"  Sum = {freeBufPct+fbEnqPct+bufBusyPct+commitPct*0.5}%  -> reclaim={reclaim:.1f}%  -> dbTimeReduction={reclaim*0.7:.1f}%")
print(f"  BUG: bufBusy and log-file-sync are CAUSED by the DBWR backlog - not additive waits.")
print(f"       True unique cost = freeBufPct + fbEnqPct = {freeBufPct+fbEnqPct}%. Recovery overstated.\n")

# --- BUG 6: GENERIC hardcoded 15% ---
print("CHALLENGE 6: GENERIC_LOAD_INCREASE 15% regardless of magnitude")
for delta in [30, 200, 1000, 5000]:
    w = min(0.45, 0.2 + delta/300)
    bc = round(50 + w * 40)
    conf = max(35, min(95, bc + 3))
    lbl = 'HIGH' if conf >= 80 else ('LOW' if conf < 60 else 'MEDIUM')
    print(f"  dbTimeDelta={delta:5}%: weight={w:.3f}, conf={conf}({lbl}), recovery=15% FIXED")
print("  BUG: 5000% DB Time surge gets identical recovery projection as 30% surge.\n")

# --- BUG 7: P-tier edge cases with high single-event dominance ---
print("CHALLENGE 7: P-tier edge cases — high single-event scenarios wrongly scored")
cases = [
    (40, 0.9, 20, 5, 5, "HW-enq 90% DB Time, delta only 40%"),
    (35, 0.85, 20, 8, 4, "Library cache 60% DB Time, delta 35%"),
    (48, 0.95, 22, 8, 46, "I/O 46% DB Time, delta 48% (misses ioPct>=50 by 4pp)"),
    (55, 1.05, 28, 4, 4, "Both dbTimeDelta>=50 AND aasRatio>=1.0 -> P2 correct"),
]
for dbDelta, aasR, domPct, commitP, ioP, desc in cases:
    pt = 'P3'
    if dbDelta >= 100 or aasR >= 1.5 or domPct >= 50: pt = 'P1'
    elif dbDelta >= 50 or aasR >= 1.0 or domPct >= 30 or commitP >= 20 or ioP >= 50: pt = 'P2'
    print(f"  {desc}  ->  {pt}")
print()

# --- BUG 8: cpuUtilPct formula correctness depends on lp2.db_cpu_s being a RATE ---
print("CHALLENGE 8: cpuUtilPct = $f(lp2.db_cpu_s) / cpus * 100")
print("  Formula: db_cpu_s / cpus * 100")
print("  CORRECT if db_cpu_s = 'DB CPU seconds per wall-clock second' (rate from AWR Load Profile Per Second column)")
print("  WRONG   if db_cpu_s = 'total DB CPU seconds for the interval'")
db_cpu_total_secs = 1000   # 1000 CPU-seconds in 60-min snapshot
cpus = 8
elapsed = 3600  # 60 minutes
util_from_total  = db_cpu_total_secs / cpus * 100          # 12500% -> clamped to 100%
util_from_rate   = (db_cpu_total_secs / elapsed) / cpus * 100  # 3.47%
util_correct     = db_cpu_total_secs / (cpus * elapsed) * 100  # 3.47%
print(f"  If db_cpu_s is TOTAL ({db_cpu_total_secs}s): formula gives {util_from_total:.0f}% -> clamped to 100% (WRONG)")
print(f"  If db_cpu_s is RATE  ({db_cpu_total_secs/elapsed:.3f}/s): formula gives {util_from_rate:.2f}% (CORRECT)")
print("  BUG RISK: If parser stores total seconds, cpuBound detection is always True, poisoning")
print("            SATURATED NOW vs WAIT-SATURATED distinction for every scenario.\n")

# --- BUG 9: sessionsFreed display vs sessions-stuck display ---
print("CHALLENGE 9: sessionsFreed can exceed sessions-stuck (confusing UI)")
aasB = 303; cpus = 52; hwEnqPct = 86.4
sessions_stuck = max(0, aasB - cpus)  # 251 -- shown in SESSION RISK
sessions_freed = aasB * (hwEnqPct * 0.9 / 100)  # 235.7 -- shown in PROJECTED RECOVERY
print(f"  aasB={aasB}, cpus={cpus}")
print(f"  Sessions stuck shown in SESSION RISK: {sessions_stuck:.0f}")
print(f"  Sessions freed in PROJECTED RECOVERY: {sessions_freed:.1f}")
print(f"  OK here ({sessions_freed:.1f} < {sessions_stuck:.0f}), but fragile: if hwEnqPct=100%")
alt = aasB * (100 * 0.9 / 100)
print(f"  sessionsFreed would be {alt:.1f} vs {sessions_stuck} stuck -> {alt:.1f} > {sessions_stuck} (contradiction)\n")

# --- SUMMARY ---
print("=== SUMMARY OF VERIFIED BUGS ===")
bugs = [
    ("P-tier severity", "CONFIRMED", "Ignores hwEnqPct, libCachePct, freeBufPct in severity calc. HW-enq 90% can show P3."),
    ("TX_ROW_LOCK recovery", "CONFIRMED", "Project uses txEnqPct (all TX types) not txRowPct. 2x+ overstatement possible."),
    ("GENERIC confidence inflation", "CONFIRMED", "15% hardcoded recovery regardless of dbTimeDelta magnitude."),
    ("latchPct double-count", "CONFIRMED", "latchPct includes events already in sharedPoolLatchPct. Inflates CONCURRENCY rule."),
    ("CONCURRENT_DML reclaim", "CONFIRMED", "Sums correlated downstream waits (bufBusy, commitPct) as independent cost."),
    ("ioPct >= 50 P2 gap", "CONFIRMED", "ioPct=46-49% with dbTimeDelta=48% misses both P1 and P2 conditions -> P3."),
    ("cpuUtilPct formula", "HIGH RISK", "Correct only if db_cpu_s is a rate. If parser gives totals, always 100% -> cpuBound always True."),
    ("HW project() rationale stale", "CONFIRMED", "Still says 'switch to uniform LMT extents' - KB was updated but RULES block was not."),
    ("BUFFER_CACHE threshold too low", "DESIGN", "freeBufPct>=8 && bufBusyPct>=5 fires at low values; noise risk in busy systems."),
]
for name, severity, desc in bugs:
    print(f"  [{severity}] {name}: {desc}")
