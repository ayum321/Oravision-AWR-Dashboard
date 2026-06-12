$raw = [System.IO.File]::ReadAllText("C:\Users\1039081\Downloads\cluade\awr-dashboard\_compare_result.json")
$cr = $raw | ConvertFrom-Json

Write-Host "============================================"
Write-Host "COMPARE API RESULT ANALYSIS"
Write-Host "============================================"

# Summary
$s = $cr.report.summary
Write-Host ""
Write-Host "=== SUMMARY ==="
Write-Host "Good AAS: $($s.aas_good) | Bad AAS: $($s.aas_bad)"
Write-Host "DB Time Delta: $($s.db_time_delta_pct)%"
Write-Host "Exec Rate Delta: $($s.exec_rate_delta_pct)%"
Write-Host "CPU Capacity: $($s.cpu_capacity_used_pct)%"
Write-Host "Bottleneck Shift: $($s.bottleneck_shift)"
Write-Host "Causal Chain: $($s.causal_chain_text)"

# SQL Regressions
Write-Host ""
Write-Host "=== SQL REGRESSIONS (top 10) ==="
$regs = $cr.report.sql_regressions | Sort-Object {[double]$_.regression_score} -Descending | Select-Object -First 10
foreach ($r in $regs) {
    $assessment = if ($r.net_assessment) { $r.net_assessment } else { "N/A" }
    $planV = if ($r.plan_verdict) { $r.plan_verdict } else { "N/A" }
    Write-Host "  $($r.sql_id): score=$($r.regression_score) | severity=$($r.severity)"
    Write-Host "    Good: $($r.good_elapsed_secs)s ($($r.good_executions)x) | Bad: $($r.bad_elapsed_secs)s ($($r.bad_executions)x)"
    Write-Host "    Assessment=$assessment | PlanVerdict=$planV | WaitAbsorb=$($r.wait_absorption)"
    Write-Host "    Source=$($r.source_category) | OracleMaint=$($r.is_oracle_maintenance)"
}

# Wait comparisons
Write-Host ""
Write-Host "=== WAIT EVENT COMPARISONS ==="
foreach ($w in $cr.report.top_wait_events.comparisons) {
    Write-Host "  $($w.event_name): Good=$($w.good_pct_db_time)% -> Bad=$($w.bad_pct_db_time)% | Delta=$($w.delta_pct_db_time)pp | Class=$($w.classification)"
    if ($w.pathology_meaning) { Write-Host "    Meaning: $($w.pathology_meaning.Substring(0, [Math]::Min(100, $w.pathology_meaning.Length)))" }
    Write-Host "    LatencyFlag=$($w.latency_flag) | Extreme=$($w.extreme_wait_flag) | Confidence=$($w.confidence) | Z=$($w.zscore)"
}

# RCA
Write-Host ""
Write-Host "=== COMPARISON RCA ==="
$rca = $cr.comparison_rca
if ($rca) {
    if ($rca.PSObject.Properties['primary_verdict']) { Write-Host "Primary Verdict: $($rca.primary_verdict)" }
    if ($rca.PSObject.Properties['root_cause']) { Write-Host "Root Cause: $($rca.root_cause)" }
    if ($rca.PSObject.Properties['severity']) { Write-Host "Severity: $($rca.severity)" }
    if ($rca.PSObject.Properties['confidence']) { Write-Host "Confidence: $($rca.confidence)" }
    Write-Host "RCA Keys: $($rca.PSObject.Properties.Name -join ', ')"
}

# Insights
Write-Host ""
Write-Host "=== INSIGHTS ==="
$ins = $cr.insights
if ($ins) {
    Write-Host "Insight Keys: $($ins.PSObject.Properties.Name -join ', ')"
    if ($ins.PSObject.Properties['primary_issue']) { Write-Host "Primary Issue: $($ins.primary_issue)" }
}

# Advanced
Write-Host ""
Write-Host "=== ADVANCED ANALYTICS ==="
$adv = $cr.advanced
if ($adv) {
    Write-Host "Advanced Keys: $($adv.PSObject.Properties.Name -join ', ')"
}
