# Compare mode test
$goodData = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/snapshots/data/uploaded_good"
$badData = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/snapshots/data/uploaded_bad"

$g = $goodData.data
$b = $badData.data

Write-Host "============================================"
Write-Host "COMPARE MODE GAP ANALYSIS"
Write-Host "============================================"
Write-Host ""
Write-Host "GOOD: $($g.db_name) | Snaps $($g.begin_snap)-$($g.end_snap) | Elapsed $($g.elapsed_min)m | DBTime $($g.db_time_min)m | CPUs $($g.cpus)"
$gAAS = [math]::Round($g.db_time_min / $g.elapsed_min, 2)
Write-Host "  AAS=$gAAS | AAS/CPU=$([math]::Round($gAAS / $g.cpus, 3))"
Write-Host ""
Write-Host "BAD:  $($b.db_name) | Snaps $($b.begin_snap)-$($b.end_snap) | Elapsed $($b.elapsed_min)m | DBTime $($b.db_time_min)m | CPUs $($b.cpus)"
$bAAS = [math]::Round($b.db_time_min / $b.elapsed_min, 2)
Write-Host "  AAS=$bAAS | AAS/CPU=$([math]::Round($bAAS / $b.cpus, 3))"
Write-Host ""
Write-Host "  DB Time change: $([math]::Round(($b.db_time_min - $g.db_time_min) / $g.db_time_min * 100, 1))%"
Write-Host ""

# Good top SQL
Write-Host "=== GOOD TOP 5 SQLs ==="
$gDbTimeSec = $g.db_time_min * 60
foreach ($s in ($g.sql_stats | Sort-Object {[double]$_.elapsed_time_secs} -Descending | Select-Object -First 5)) {
    $pct = [math]::Round($s.elapsed_time_secs / $gDbTimeSec * 100, 2)
    $epe = if ($s.executions -gt 0) { [math]::Round($s.elapsed_time_secs / $s.executions, 2) } else { 0 }
    Write-Host "  $($s.sql_id): $pct% | Elapsed=$($s.elapsed_time_secs)s | EPE=${epe}s | Execs=$($s.executions) | Gets=$($s.buffer_gets)"
}

# Bad top SQL
Write-Host ""
Write-Host "=== BAD TOP 5 SQLs ==="
$bDbTimeSec = $b.db_time_min * 60
foreach ($s in ($b.sql_stats | Sort-Object {[double]$_.elapsed_time_secs} -Descending | Select-Object -First 5)) {
    $pct = [math]::Round($s.elapsed_time_secs / $bDbTimeSec * 100, 2)
    $epe = if ($s.executions -gt 0) { [math]::Round($s.elapsed_time_secs / $s.executions, 2) } else { 0 }
    Write-Host "  $($s.sql_id): $pct% | Elapsed=$($s.elapsed_time_secs)s | EPE=${epe}s | Execs=$($s.executions) | Gets=$($s.buffer_gets)"
}

# Wait events comparison
Write-Host ""
Write-Host "=== GOOD WAIT EVENTS ==="
foreach ($e in ($g.wait_events | Select-Object -First 8)) {
    Write-Host "  $($e.pct_db_time)% | $($e.event_name) | Class=$($e.wait_class) | $($e.time_waited_secs)s"
}
Write-Host "  wait_class populated: $(($g.wait_events | Where-Object { $_.wait_class -and $_.wait_class -ne '' }).Count) / $($g.wait_events.Count)"

Write-Host ""
Write-Host "=== BAD WAIT EVENTS ==="
foreach ($e in ($b.wait_events | Select-Object -First 8)) {
    Write-Host "  $($e.pct_db_time)% | $($e.event_name) | Class=$($e.wait_class) | $($e.time_waited_secs)s"
}
Write-Host "  wait_class populated: $(($b.wait_events | Where-Object { $_.wait_class -and $_.wait_class -ne '' }).Count) / $($b.wait_events.Count)"

# Check GAPs in compare data
Write-Host ""
Write-Host "=== COMPARE DATA GAPS ==="
Write-Host "GOOD:"
Write-Host "  plan_hash: $(($g.sql_stats | Where-Object { $_.plan_hash_value -and $_.plan_hash_value -ne '' -and $_.plan_hash_value -ne '0' }).Count)/$($g.sql_stats.Count)"
Write-Host "  rows_processed>0: $(($g.sql_stats | Where-Object { $_.rows_processed -gt 0 }).Count)/$($g.sql_stats.Count)"
Write-Host "  efficiency non-empty: $(($g.efficiency | Where-Object { $_.value -and $_.value -ne '' }).Count)"
Write-Host "  addm non-empty: $(($g.addm_findings | Where-Object { $_.finding_type -and $_.finding_type -ne '' }).Count)/$($g.addm_findings.Count)"
Write-Host ""
Write-Host "BAD:"
Write-Host "  plan_hash: $(($b.sql_stats | Where-Object { $_.plan_hash_value -and $_.plan_hash_value -ne '' -and $_.plan_hash_value -ne '0' }).Count)/$($b.sql_stats.Count)"
Write-Host "  rows_processed>0: $(($b.sql_stats | Where-Object { $_.rows_processed -gt 0 }).Count)/$($b.sql_stats.Count)"
Write-Host "  efficiency non-empty: $(($b.efficiency | Where-Object { $_.value -and $_.value -ne '' }).Count)"
Write-Host "  addm non-empty: $(($b.addm_findings | Where-Object { $_.finding_type -and $_.finding_type -ne '' }).Count)/$($b.addm_findings.Count)"

# Now test the compare API
Write-Host ""
Write-Host "=== TESTING COMPARE API ==="
$compareResult = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/compare/" -Method POST -ContentType "application/json" -Body '{"good_period":"uploaded_good","bad_period":"uploaded_bad"}'
$compareResult | ConvertTo-Json -Depth 10 | Set-Content "_compare_result.json"
Write-Host "Compare result saved. Keys: $($compareResult.PSObject.Properties.Name -join ', ')"
