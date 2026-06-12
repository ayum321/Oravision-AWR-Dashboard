$raw = [System.IO.File]::ReadAllText("C:\Users\1039081\Downloads\cluade\awr-dashboard\_compare_result.json")
$cr = $raw | ConvertFrom-Json

Write-Host "=== COMPARISON RCA DETAIL ==="
$rca = $cr.comparison_rca
Write-Host "RCA1: $($rca.rca1)"
Write-Host ""
Write-Host "RCA2: $($rca.rca2)"
Write-Host ""

Write-Host "=== DELTA FINDINGS ==="
foreach ($df in $rca.delta_findings) {
    Write-Host "  $df"
}

Write-Host ""
Write-Host "=== DB SUMMARY 1 (Good) ==="
Write-Host $rca.db_summary_1

Write-Host ""
Write-Host "=== DB SUMMARY 2 (Bad) ==="
Write-Host $rca.db_summary_2

Write-Host ""
Write-Host "=== CULPRITS ==="
foreach ($c in $cr.advanced.culprits) {
    Write-Host "  $($c.sql_id): score=$($c.culprit_score) | reason=$($c.reason)"
}

Write-Host ""
Write-Host "=== CAUSAL CHAINS ==="
$chains = $cr.advanced.causal_chains
if ($chains) {
    Write-Host ($chains | ConvertTo-Json -Depth 5 | Select-Object -First 50)
}

Write-Host ""
Write-Host "=== RECOMMENDATIONS ==="
foreach ($rec in $cr.recommendations) {
    $title = if ($rec.PSObject.Properties['title']) { $rec.title } else { $rec.category }
    $desc = if ($rec.PSObject.Properties['description']) { $rec.description.Substring(0, [Math]::Min(120, $rec.description.Length)) } else { "" }
    Write-Host "  [$($rec.severity)] $title"
    Write-Host "    $desc"
}
