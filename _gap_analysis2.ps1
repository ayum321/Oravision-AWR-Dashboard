$raw = [System.IO.File]::ReadAllText("C:\Users\1039081\Downloads\cluade\awr-dashboard\_single_parsed.json")
$j = $raw | ConvertFrom-Json
$d = $j.data

Write-Host "=== FOREGROUND WAIT EVENTS (detailed) ==="
$totalFgTime = 0
foreach ($fe in $d._foreground_wait_events) {
    $totalFgTime += $fe.time_waited_secs
    Write-Host "  $($fe.pct_db_time)% | $($fe.event_name) | $($fe.wait_class) | $($fe.time_waited_secs)s | $($fe.total_waits) waits | Avg=$($fe.avg_wait_ms)ms"
}
Write-Host "Total FG events: $($d._foreground_wait_events.Count) | Total FG time: $totalFgTime s"
$dbTimeSec = $d.db_time_min * 60
Write-Host "DB Time: $dbTimeSec s | Accounted: $([math]::Round($totalFgTime / $dbTimeSec * 100, 1))%"

Write-Host ""
Write-Host "=== WAIT CLASSES ==="
foreach ($wc in $d._wait_classes) {
    Write-Host "  $($wc.wait_class): $($wc.total_waits) waits | $($wc.time_waited_secs)s | $($wc.pct_db_time)%"
}

Write-Host ""
Write-Host "=== COMPARING wait_events vs _foreground_wait_events ==="
Write-Host "wait_events (used for verdict): $($d.wait_events.Count) events"
Write-Host "_foreground_wait_events (not used?): $($d._foreground_wait_events.Count) events"

# Check top events by actual DB time contribution
Write-Host ""
Write-Host "=== TOP 20 by %DB TIME (foreground) ==="
$sorted = $d._foreground_wait_events | Sort-Object {[double]$_.pct_db_time} -Descending | Select-Object -First 20
foreach ($s in $sorted) {
    Write-Host "  $($s.pct_db_time)% | $($s.event_name) | $($s.wait_class) | $($s.time_waited_secs)s"
}

Write-Host ""
Write-Host "=== SQL TEXT MAP ==="
$stm = $d._sql_text_map
if ($stm) {
    $stmProps = $stm.PSObject.Properties
    Write-Host "SQL Text Map entries: $($stmProps.Count)"
    foreach ($p in ($stmProps | Select-Object -First 5)) {
        $txt = if ($p.Value.Length -gt 80) { $p.Value.Substring(0,80) + "..." } else { $p.Value }
        Write-Host "  $($p.Name): $txt"
    }
} else {
    Write-Host "SQL Text Map: MISSING"
}

Write-Host ""
Write-Host "=== SQL REGISTRY ==="
$sr = $d._sql_registry
if ($sr) {
    Write-Host "SQL Registry entries: $($sr.Count)"
    foreach ($r in ($sr | Select-Object -First 3)) {
        Write-Host "  $($r.sql_id) | PlanHash=$($r.plan_hash_value) | Module=$($r.module) | Action=$($r.action)"
    }
} else {
    Write-Host "SQL Registry: MISSING"
}
