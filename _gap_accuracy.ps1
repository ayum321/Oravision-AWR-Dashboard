$raw = [System.IO.File]::ReadAllText("C:\Users\1039081\Downloads\cluade\awr-dashboard\_single_parsed.json")
$j = $raw | ConvertFrom-Json
$d = $j.data

Write-Host "============================================"
Write-Host "ACCURACY ANALYSIS: WHAT THE TOOL SEES vs REALITY"
Write-Host "============================================"

# 1. SEVERITY CHECK
$aas = [math]::Round($d.db_time_min / $d.elapsed_min, 2)
$ratio = [math]::Round($aas / $d.cpus, 3)
Write-Host ""
Write-Host "1. SEVERITY ASSESSMENT"
Write-Host "   AAS = $aas on $($d.cpus) CPUs (ratio=$ratio)"
if ($ratio -gt 2) { Write-Host "   -> CRITICAL: AAS is ${ratio}x CPUs" }
elseif ($ratio -gt 1) { Write-Host "   -> DEGRADED: AAS exceeds CPU count" }
Write-Host ""

# 2. TOP SQL BOTTLENECK
Write-Host "2. TOP SQL IDENTIFICATION"
$dbTimeSec = $d.db_time_min * 60
$topSqls = $d.sql_stats | Sort-Object {[double]$_.elapsed_time_secs} -Descending
$top3Pct = 0
foreach ($s in ($topSqls | Select-Object -First 5)) {
    $pct = [math]::Round($s.elapsed_time_secs / $dbTimeSec * 100, 2)
    $top3Pct += $pct
    $cpuPct = if ($s.elapsed_time_secs -gt 0) { [math]::Round($s.cpu_time_secs / $s.elapsed_time_secs * 100, 1) } else { 0 }
    $epe = if ($s.executions -gt 0) { [math]::Round($s.elapsed_time_secs / $s.executions, 2) } else { 0 }
    $gpe = if ($s.executions -gt 0) { [math]::Round([double]$s.buffer_gets / $s.executions, 0) } else { 0 }
    Write-Host "   $($s.sql_id): $pct% DB Time | EPE=${epe}s | GPE=$gpe | CPU%=$cpuPct%"
}
Write-Host "   Top 5 SQLs = $([math]::Round($top3Pct, 1))% of DB Time"
Write-Host ""

# 3. WAIT EVENT GAP
Write-Host "3. WAIT EVENT COVERAGE"
$cpuEvent = $d.wait_events | Where-Object { $_.event_name -eq 'DB CPU' }
$cpuPct = if ($cpuEvent) { $cpuEvent.pct_db_time } else { 0 }
$totalWaitPct = ($d.wait_events | Measure-Object -Property pct_db_time -Sum).Sum
Write-Host "   wait_events has $($d.wait_events.Count) events covering $totalWaitPct% of DB Time"
Write-Host "   DB CPU alone = $cpuPct%"
Write-Host "   Non-CPU waits = $([math]::Round($totalWaitPct - $cpuPct, 1))%"
Write-Host "   *** MISSING: $([math]::Round(100 - $totalWaitPct, 1))% of DB Time is unaccounted!"
Write-Host ""

# But foreground events tell a different story
$fgNonIdle = $d._foreground_wait_events | Where-Object { 
    $_.event_name -notmatch 'SQL\*Net message from client|watchdog|jobq slave' 
}
$fgNonIdleTime = ($fgNonIdle | Measure-Object -Property time_waited_secs -Sum).Sum
$fgNonIdlePct = [math]::Round($fgNonIdleTime / $dbTimeSec * 100, 1)
Write-Host "   _foreground_wait_events (non-idle): $($fgNonIdle.Count) events, $fgNonIdleTime s ($fgNonIdlePct%)"
Write-Host "   -> CPU (from Time Model): $([math]::Round(52018.84 / $dbTimeSec * 100, 1))%"
Write-Host "   -> Total accounted (CPU + non-idle waits): $([math]::Round((52018.84 + $fgNonIdleTime) / $dbTimeSec * 100, 1))%"
Write-Host ""

# 4. WAIT CLASS GAPS
Write-Host "4. WAIT CLASS PARSING"
$hasWaitClass = ($d._foreground_wait_events | Where-Object { $_.wait_class -and $_.wait_class -ne '' }).Count
Write-Host "   Events with wait_class: $hasWaitClass / $($d._foreground_wait_events.Count)"
if ($hasWaitClass -eq 0) { Write-Host "   *** CRITICAL GAP: wait_class is NOT parsed from foreground events!" }
Write-Host ""

# 5. INSTANCE EFFICIENCY
Write-Host "5. INSTANCE EFFICIENCY"
$hasEff = ($d.efficiency | Where-Object { $_.value -and $_.value -ne '' -and $_.value -ne '0' }).Count
Write-Host "   Non-empty efficiency entries: $hasEff / $($d.efficiency.Count)"
if ($hasEff -eq 0) { Write-Host "   *** CRITICAL GAP: Instance Efficiency metrics not parsed!" }
Write-Host ""

# 6. PLAN HASH
Write-Host "6. SQL PLAN HASH VALUES"
$hasPlan = ($d.sql_stats | Where-Object { $_.plan_hash_value -and $_.plan_hash_value -ne '' -and $_.plan_hash_value -ne '0' }).Count
Write-Host "   SQLs with plan_hash: $hasPlan / $($d.sql_stats.Count)"
if ($hasPlan -eq 0) { Write-Host "   *** CRITICAL GAP: plan_hash_value not parsed from any SQL!" }
Write-Host ""

# 7. ROWS PROCESSED
Write-Host "7. ROWS PROCESSED"
$hasRows = ($d.sql_stats | Where-Object { $_.rows_processed -gt 0 }).Count
Write-Host "   SQLs with rows_processed > 0: $hasRows / $($d.sql_stats.Count)"
Write-Host ""

# 8. ADDM
Write-Host "8. ADDM FINDINGS"
$hasAddm = ($d.addm_findings | Where-Object { $_.finding_type -and $_.finding_type -ne '' }).Count
Write-Host "   Non-empty ADDM findings: $hasAddm / $($d.addm_findings.Count)"
if ($d.addm_findings.Count -gt 0 -and $hasAddm -eq 0) { Write-Host "   *** GAP: ADDM findings exist but fields not parsed!" }
Write-Host ""

# 9. SEGMENT DATA
Write-Host "9. SEGMENT DATA"
$hasSeg = ($d.segments | Where-Object { $_.physical_reads_delta -and $_.physical_reads_delta -ne '' }).Count
Write-Host "   Segments with physical_reads: $hasSeg / $($d.segments.Count)"
if ($d.segments.Count -gt 0 -and $hasSeg -eq 0) { Write-Host "   *** GAP: Segment data exists but numeric fields not parsed!" }
Write-Host ""

# 10. WHAT VERDICT SHOULD THE TOOL GIVE?
Write-Host "==========================================="
Write-Host "10. EXPECTED vs ACTUAL VERDICT"
Write-Host "==========================================="
Write-Host ""
Write-Host "EXPECTED VERDICT:"
Write-Host "  Severity: CRITICAL (AAS $aas on $($d.cpus) CPUs = ${ratio}x overloaded)"
Write-Host "  Root Cause: Excessive Logical I/O from 3 dominant SQLs"
Write-Host "  Top SQL: cw9q26vnqk1cs (41.5% DB Time, 336K gets/exec)"
Write-Host "  Wait Pattern: No single dominant wait = CPU + micro-latching from billions of buffer gets"
Write-Host "  Action: Tune top 3 SQLs to reduce buffer gets (fix indexes, reduce FTS)"
Write-Host ""
Write-Host "ACCURACY ISSUES:"
Write-Host "  1. wait_class not parsed -> bottleneck type classification broken"
Write-Host "  2. Instance efficiency empty -> can't check buffer cache hit %, soft parse %"
Write-Host "  3. Plan hash missing -> can't detect plan changes or suggest DBMS_XPLAN"
Write-Host "  4. 89% of DB Time unaccounted in wait_events -> misleading narrative"
Write-Host "  5. ADDM findings not parsed -> missing Oracle's own bottleneck analysis"
Write-Host "  6. No rows_processed for top SQLs -> cardinality analysis broken"
