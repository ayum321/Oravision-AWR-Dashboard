# Examine the AWR HTML raw table structure for key sections
$awr = [System.IO.File]::ReadAllText("C:\Users\1039081\Downloads\awr_adsprddb_23april_1210_1240AM.html")

# 1. Check foreground wait events table headers
Write-Host "=== FOREGROUND WAIT EVENTS TABLE ==="
$fgIdx = $awr.IndexOf("Foreground Wait Event")
if ($fgIdx -lt 0) { $fgIdx = $awr.IndexOf("foreground wait events") }
if ($fgIdx -lt 0) { $fgIdx = $awr.IndexOf("Foreground Wait") }
Write-Host "Found at offset: $fgIdx"
if ($fgIdx -gt 0) {
    # Find the next <table after this
    $tblStart = $awr.IndexOf("<table", $fgIdx)
    $tblEnd = $awr.IndexOf("</table>", $tblStart) + 8
    $tblHtml = $awr.Substring($tblStart, [Math]::Min(5000, $tblEnd - $tblStart))
    # Extract just the header row
    $headerMatch = [regex]::Match($tblHtml, '<tr[^>]*>.*?</tr>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($headerMatch.Success) {
        $headerHtml = $headerMatch.Value
        # Extract th/td content
        $cells = [regex]::Matches($headerHtml, '<t[hd][^>]*>(.*?)</t[hd]>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
        Write-Host "Header cells:"
        foreach ($c in $cells) {
            $txt = $c.Groups[1].Value -replace '<[^>]+>', '' -replace '&nbsp;', ' '
            Write-Host "  [$txt]"
        }
    }
    # Also show first 2 data rows
    $allRows = [regex]::Matches($tblHtml, '<tr[^>]*>(.*?)</tr>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    $rowNum = 0
    foreach ($r in $allRows) {
        $rowNum++
        if ($rowNum -le 3) {
            $cells = [regex]::Matches($r.Value, '<t[hd][^>]*>(.*?)</t[hd]>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
            $vals = @()
            foreach ($c in $cells) { $vals += ($c.Groups[1].Value -replace '<[^>]+>', '' -replace '&nbsp;', ' ').Trim() }
            Write-Host "Row $rowNum: $($vals -join ' | ')"
        }
    }
}

Write-Host ""
Write-Host "=== INSTANCE EFFICIENCY TABLE ==="
$effIdx = $awr.IndexOf("Instance Efficiency")
Write-Host "Found at offset: $effIdx"
if ($effIdx -gt 0) {
    $tblStart = $awr.IndexOf("<table", $effIdx)
    $tblEnd = $awr.IndexOf("</table>", $tblStart) + 8
    $tblHtml = $awr.Substring($tblStart, [Math]::Min(3000, $tblEnd - $tblStart))
    $allRows = [regex]::Matches($tblHtml, '<tr[^>]*>(.*?)</tr>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    $rowNum = 0
    foreach ($r in $allRows) {
        $rowNum++
        $cells = [regex]::Matches($r.Value, '<t[hd][^>]*>(.*?)</t[hd]>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
        $vals = @()
        foreach ($c in $cells) { $vals += ($c.Groups[1].Value -replace '<[^>]+>', '' -replace '&nbsp;', ' ').Trim() }
        Write-Host "Row $rowNum: $($vals -join ' | ')"
    }
}

Write-Host ""
Write-Host "=== SQL ORDERED BY ELAPSED TIME TABLE ==="
$sqlIdx = $awr.IndexOf("SQL ordered by Elapsed")
if ($sqlIdx -lt 0) { $sqlIdx = $awr.IndexOf("sql ordered by elapsed") }
Write-Host "Found at offset: $sqlIdx"
if ($sqlIdx -gt 0) {
    $tblStart = $awr.IndexOf("<table", $sqlIdx)
    $tblEnd = $awr.IndexOf("</table>", $tblStart) + 8
    $tblHtml = $awr.Substring($tblStart, [Math]::Min(5000, $tblEnd - $tblStart))
    $allRows = [regex]::Matches($tblHtml, '<tr[^>]*>(.*?)</tr>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    $rowNum = 0
    foreach ($r in $allRows) {
        $rowNum++
        if ($rowNum -le 3) {
            $cells = [regex]::Matches($r.Value, '<t[hd][^>]*>(.*?)</t[hd]>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
            $vals = @()
            foreach ($c in $cells) { $vals += ($c.Groups[1].Value -replace '<[^>]+>', '' -replace '&nbsp;', ' ').Trim() }
            Write-Host "Row $rowNum: $($vals -join ' | ')"
        }
    }
}

Write-Host ""
Write-Host "=== ADDM FINDINGS TABLE ==="
$addmIdx = $awr.IndexOf("ADDM")
Write-Host "Found at offset: $addmIdx"
if ($addmIdx -gt 0) {
    $tblStart = $awr.IndexOf("<table", $addmIdx)
    if ($tblStart -gt 0 -and ($tblStart - $addmIdx) -lt 2000) {
        $tblEnd = $awr.IndexOf("</table>", $tblStart) + 8
        $tblHtml = $awr.Substring($tblStart, [Math]::Min(5000, $tblEnd - $tblStart))
        $allRows = [regex]::Matches($tblHtml, '<tr[^>]*>(.*?)</tr>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
        $rowNum = 0
        foreach ($r in $allRows) {
            $rowNum++
            if ($rowNum -le 6) {
                $cells = [regex]::Matches($r.Value, '<t[hd][^>]*>(.*?)</t[hd]>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
                $vals = @()
                foreach ($c in $cells) { $vals += ($c.Groups[1].Value -replace '<[^>]+>', '' -replace '&nbsp;', ' ').Trim() }
                Write-Host "Row $rowNum ($($cells.Count) cells): $($vals -join ' | ')"
            }
        }
    }
}

Write-Host ""
Write-Host "=== TOP TIMED EVENTS TABLE ==="
$tteIdx = $awr.IndexOf("Top Timed Events")
if ($tteIdx -lt 0) { $tteIdx = $awr.IndexOf("top 10 foreground") }
Write-Host "Found at offset: $tteIdx"
if ($tteIdx -gt 0) {
    $tblStart = $awr.IndexOf("<table", $tteIdx)
    $tblEnd = $awr.IndexOf("</table>", $tblStart) + 8
    $tblHtml = $awr.Substring($tblStart, [Math]::Min(3000, $tblEnd - $tblStart))
    $allRows = [regex]::Matches($tblHtml, '<tr[^>]*>(.*?)</tr>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
    $rowNum = 0
    foreach ($r in $allRows) {
        $rowNum++
        if ($rowNum -le 5) {
            $cells = [regex]::Matches($r.Value, '<t[hd][^>]*>(.*?)</t[hd]>', [System.Text.RegularExpressions.RegexOptions]::Singleline)
            $vals = @()
            foreach ($c in $cells) { $vals += ($c.Groups[1].Value -replace '<[^>]+>', '' -replace '&nbsp;', ' ').Trim() }
            Write-Host "Row $rowNum: $($vals -join ' | ')"
        }
    }
}
