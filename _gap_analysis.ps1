$raw = [System.IO.File]::ReadAllText("C:\Users\1039081\Downloads\cluade\awr-dashboard\_single_parsed.json")
$j = $raw | ConvertFrom-Json
$d = $j.data

Write-Host "============================================"
Write-Host "SINGLE AWR GAP ANALYSIS - $($d.db_name)"
Write-Host "============================================"
Write-Host ""
Write-Host "=== DB INFO ==="
Write-Host "DB: $($d.db_name) | Instance: $($d.instance) | Host: $($d.host)"
Write-Host "CPUs: $($d.cpus) | Memory: $($d.memory_gb) GB | RAC: $($d.rac)"
Write-Host "Release: $($d.release) | Platform: $($d.platform)"
Write-Host ""
Write-Host "=== SNAPSHOT INFO ==="
Write-Host "Snaps: $($d.begin_snap) - $($d.end_snap)"
Write-Host "Begin: $($d.begin_time) | End: $($d.end_time)"
Write-Host "Elapsed: $($d.elapsed_min) min | DB Time: $($d.db_time_min) min"
$aas = [math]::Round($d.db_time_min / $d.elapsed_min, 2)
$aasRatio = [math]::Round($aas / $d.cpus, 3)
Write-Host "AAS: $aas | AAS/CPU: $aasRatio"
Write-Host ""

Write-Host "=== TOP WAIT EVENTS (parsed) ==="
$evtCount = 0
foreach ($e in $d.wait_events) {
    $evtCount++
    Write-Host "  $($e.pct_db_time)% | $($e.event_name) | Class=$($e.wait_class) | Waits=$($e.total_waits) | Time=$($e.time_waited_secs)s | AvgWait=$($e.avg_wait_ms)ms"
}
Write-Host "Total wait events parsed: $evtCount"
Write-Host ""

Write-Host "=== SQL STATS (parsed) ==="
$sqlCount = 0
$topSqls = @()
foreach ($s in $d.sql_stats) {
    $sqlCount++
    if ($sqlCount -le 15) {
        $epe = if ($s.executions -gt 0) { [math]::Round($s.elapsed_time_secs / $s.executions, 4) } else { 0 }
        $gpe = if ($s.executions -gt 0) { [math]::Round($s.buffer_gets / $s.executions, 0) } else { 0 }
        $pctDb = if ($d.db_time_min -gt 0) { [math]::Round(($s.elapsed_time_secs / 60) / $d.db_time_min * 100, 2) } else { 0 }
        Write-Host "  $($s.sql_id) | Elapsed=$($s.elapsed_time_secs)s | CPU=$($s.cpu_time_secs)s | Execs=$($s.executions) | Gets=$($s.buffer_gets) | Reads=$($s.disk_reads) | Rows=$($s.rows_processed)"
        Write-Host "    -> EPE=$($epe)s | GPE=$gpe | %DB=$pctDb | PlanHash=$($s.plan_hash_value)"
    }
}
Write-Host "Total SQLs parsed: $sqlCount"
Write-Host ""

Write-Host "=== LOAD PROFILE ==="
foreach ($lp in $d.load_profile) {
    Write-Host "  $($lp.stat_name): PerSec=$($lp.per_sec) PerTxn=$($lp.per_txn)"
}
Write-Host ""

Write-Host "=== INSTANCE EFFICIENCY ==="
foreach ($eff in $d.efficiency) {
    Write-Host "  $($eff.stat_name): $($eff.value)"
}
Write-Host ""

Write-Host "=== TIME MODEL ==="
foreach ($tm in $d.time_model) {
    Write-Host "  $($tm.stat_name): $($tm.time_secs)s ($($tm.pct_db_time)%)"
}
Write-Host ""

Write-Host "=== ADDM FINDINGS ==="
foreach ($f in $d.addm_findings) {
    Write-Host "  Type=$($f.finding_type) | Impact=$($f.finding_impact) | Rec=$($f.recommendation)"
}
Write-Host ""

Write-Host "=== SEGMENTS ==="
$segCount = 0
foreach ($seg in $d.segments) {
    $segCount++
    if ($segCount -le 5) {
        Write-Host "  $($seg.object_name) | PhysReads=$($seg.physical_reads_delta) | LogReads=$($seg.logical_reads_delta)"
    }
}
Write-Host "Total segments: $segCount"
Write-Host ""

# Check what fields might be missing or zero
Write-Host "=== POTENTIAL GAPS ==="
$issues = @()
if (-not $d.cpus -or $d.cpus -eq 0) { $issues += "MISSING: CPUs not parsed" }
if (-not $d.db_time_min -or $d.db_time_min -eq 0) { $issues += "MISSING: DB Time not parsed" }
if (-not $d.elapsed_min -or $d.elapsed_min -eq 0) { $issues += "MISSING: Elapsed time not parsed" }
if ($evtCount -eq 0) { $issues += "MISSING: No wait events parsed" }
if ($sqlCount -eq 0) { $issues += "MISSING: No SQL stats parsed" }

# Check for SQL with zero rows_processed
$zeroRows = ($d.sql_stats | Where-Object { $_.rows_processed -eq 0 }).Count
if ($zeroRows -gt 0) { $issues += "GAP: $zeroRows SQLs have rows_processed=0 (may be unparsed)" }

# Check for SQL with no plan hash
$noPlan = ($d.sql_stats | Where-Object { -not $_.plan_hash_value -or $_.plan_hash_value -eq '0' -or $_.plan_hash_value -eq '' }).Count
if ($noPlan -gt 0) { $issues += "GAP: $noPlan SQLs have no plan_hash_value" }

# Check for wait events with 0 avg_wait
$zeroAvgWait = ($d.wait_events | Where-Object { $_.avg_wait_ms -eq 0 }).Count
if ($zeroAvgWait -gt 0) { $issues += "GAP: $zeroAvgWait wait events have avg_wait_ms=0" }

# Check if SQL text is captured
$noText = ($d.sql_stats | Where-Object { -not $_.sql_text -or $_.sql_text.Length -lt 5 }).Count
if ($noText -gt 0) { $issues += "INFO: $noText SQLs have short/missing sql_text (normal for AWR)" }

# Check foreground events
$fgCount = 0
if ($d._foreground_wait_events) { $fgCount = $d._foreground_wait_events.Count }
Write-Host "Foreground wait events: $fgCount"

# Check wait classes
$wcCount = 0
if ($d._wait_classes) { $wcCount = $d._wait_classes.Count }
Write-Host "Wait classes: $wcCount"

# Check ASH
$ashEntries = 0
if ($d.ash_summary) { $ashEntries = $d.ash_summary.Count }
Write-Host "ASH summary entries: $ashEntries"

# Check latch activity
$latchCount = 0
if ($d._latch_activity) { $latchCount = $d._latch_activity.Count }
Write-Host "Latch activity entries: $latchCount"

# Check tablespace I/O
$tsioCount = 0
if ($d._tablespace_io) { $tsioCount = $d._tablespace_io.Count }
Write-Host "Tablespace I/O entries: $tsioCount"

foreach ($i in $issues) { Write-Host "  *** $i" }
