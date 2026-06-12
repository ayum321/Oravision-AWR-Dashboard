import datetime

STANDARD_INTERVALS = [15, 30, 60]
SNAP_TOL = 2

def on_boundary(minute):
    return any(minute % i == 0 for i in STANDARD_INTERVALS)

def interval_is_std(inf):
    return any(abs(inf - i) <= SNAP_TOL for i in STANDARD_INTERVALS)

def classify_window(begin_min, end_min, inferred_interval, snap_intervals):
    start_on = on_boundary(begin_min)
    end_on   = on_boundary(end_min)
    std_int  = interval_is_std(inferred_interval)
    if not start_on:
        return 'JOB_SPECIFIC', f'Start (:{begin_min:02d}) not on standard boundary — manually triggered'
    if not std_int and snap_intervals > 0:
        return 'JOB_SPECIFIC', f'Interval {inferred_interval:.1f} min not standard (15/30/60)'
    if start_on and end_on and std_int:
        return 'STANDARD_SNAP', f'All match standard schedule'
    return 'PARTIAL', 'One boundary on schedule, other not'

# --- User's actual data ---
# Good: Jan 11 10:01:28 to 10:30:21, SNAP 185519-185521, 28.9 min
good_begin_min, good_end_min = 1, 30
good_snap_intervals = 185521 - 185519   # 2
good_inferred = 28.9 / good_snap_intervals  # 14.45

# Bad: Jan 31 20:32:53 to 21:30:23, SNAP 187829-187831, 57.5 min
bad_begin_min, bad_end_min = 32, 30
bad_snap_intervals = 187831 - 187829    # 2
bad_inferred = 57.5 / bad_snap_intervals   # 28.75

print("=== GOOD PERIOD (old vs new classification) ===")
print(f"  beginMin={good_begin_min}, endMin={good_end_min}, interval={good_inferred:.2f}")
print(f"  OLD: {'JOB_SPECIFIC' if (not on_boundary(good_begin_min) and not on_boundary(good_end_min)) else 'NOT old-JOB'}")
g_type, g_reason = classify_window(good_begin_min, good_end_min, good_inferred, good_snap_intervals)
print(f"  NEW: {g_type} — {g_reason}")

print()
print("=== BAD PERIOD (old vs new classification) ===")
print(f"  beginMin={bad_begin_min}, endMin={bad_end_min}, interval={bad_inferred:.2f}")
b_type, b_reason = classify_window(bad_begin_min, bad_end_min, bad_inferred, bad_snap_intervals)
print(f"  NEW: {b_type} — {b_reason}")

print()
print("=== BANNERS THAT WILL NOW FIRE ===")
both_job = g_type == 'JOB_SPECIFIC' and b_type == 'JOB_SPECIFIC'
print(f"  [A] bothJob = {both_job} → 'Job-Targeted Capture — High Confidence Comparison'")

tod_good = 10*60+1   # 10:01
tod_bad  = 20*60+32  # 20:32
tod_diff = abs(tod_good - tod_bad)
print(f"  [A2] TOD diff = {tod_diff} min ({tod_diff/60:.1f}h), fires at >180 = {tod_diff > 180} → 'Different Time of Day'")

good_end_dt  = datetime.datetime(2026, 1, 11, 10, 30, 21)
bad_begin_dt = datetime.datetime(2026, 1, 31, 20, 32, 53)
gap_days = abs((bad_begin_dt - good_end_dt).total_seconds()) / 86400
print(f"  [F]  Gap = {gap_days:.1f} days → ", end="")
if gap_days >= 30:
    print("CRITICAL banner (>=30 days)")
elif gap_days >= 7:
    print("WARNING banner (>=7 days)")
elif gap_days >= 1:
    print("INFO banner (>=1 day)")
else:
    print("POSITIVE banner (same-day)")

dur_delta_pct = (57.5 - 28.9) / 28.9 * 100
print(f"  [E]  Duration mismatch = {dur_delta_pct:.0f}% → {'WARNING banner (>25%)' if abs(dur_delta_pct) > 25 else 'no banner'}")

print()
print("=== SUMMARY OF OLD vs NEW ===")
print("  OLD: Both classified as PARTIAL → no job-targeted, no time-of-day, no gap banner (threshold 30 days, 20 days missed)")
print("  NEW: Both JOB_SPECIFIC + Time-of-Day warning (10h apart) + Gap warning (20 days) + Duration mismatch = 4 informative banners")
