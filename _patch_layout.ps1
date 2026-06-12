$file = (Resolve-Path 'backend/templates/index.html').Path
$c = [System.IO.File]::ReadAllText($file)
$fnStart = $c.IndexOf('function renderSingleDashboard(')
Write-Host "renderSingleDashboard at: $fnStart"

# Find the function end using brace counting
$i = $c.IndexOf('{', $fnStart)
$braceCount = 1; $i++
while ($braceCount -gt 0 -and $i -lt $c.Length) {
    if ($c[$i] -eq '{') { $braceCount++ }
    elseif ($c[$i] -eq '}') { $braceCount-- }
    $i++
}
$fnEnd = $i
$fnLen = $fnEnd - $fnStart
Write-Host "Function length: $fnLen chars (ends at $fnEnd)"

$fn = $c.Substring($fnStart, $fnLen)

# Find key anchors within the function
$treemapEnd = $fn.IndexOf("// SESSION PERFORMANCE INTELLIGENCE")
$sessionPerfStart = $treemapEnd
$sreStart = $fn.IndexOf("// SRE Operations Intelligence panel")
$deepDiagStart = $fn.IndexOf("// === SECTION 4: DEEP DIAGNOSTICS")

# Find the SRE block end (it's an IIFE that returns a string, ends with "})();")
# The SRE block starts with "html += (function() {" at sreStart
# We need to find the end of that IIFE
$sreHtmlIdx = $fn.IndexOf("html += (function() {", $sreStart)
$sreIifeStart = $fn.IndexOf("(function() {", $sreHtmlIdx)
$sreBraceStart = $fn.IndexOf("{", $sreIifeStart + 12)
$braceCount2 = 1; $j = $sreBraceStart + 1
while ($braceCount2 -gt 0 -and $j -lt $fn.Length) {
    if ($fn[$j] -eq '{') { $braceCount2++ }
    elseif ($fn[$j] -eq '}') { $braceCount2-- }
    $j++
}
# j is now past the closing } of the IIFE function body
# The IIFE closes with })(); so we need to go past that
$sreBlockEnd = $fn.IndexOf(";", $j) + 1
Write-Host "SRE block ends at fn offset: $sreBlockEnd"

# Now find where the Batch Purge IIFE is
$bpStart = $fn.IndexOf("// Batch Purge Detection (always visible")
$bpIifeStart = $fn.IndexOf("(function() {", $bpStart)
$bpBrace = $fn.IndexOf("{", $bpIifeStart + 12)
$braceCount3 = 1; $k = $bpBrace + 1
while ($braceCount3 -gt 0 -and $k -lt $fn.Length) {
    if ($fn[$k] -eq '{') { $braceCount3++ }
    elseif ($fn[$k] -eq '}') { $braceCount3-- }
    $k++
}
$bpEnd = $fn.IndexOf(";", $k) + 1
# Include any trailing whitespace/newlines
while ($bpEnd -lt $fn.Length -and ($fn[$bpEnd] -eq "`r" -or $fn[$bpEnd] -eq "`n" -or $fn[$bpEnd] -eq " ")) { $bpEnd++ }
$bpBlock = $fn.Substring($bpStart, $bpEnd - $bpStart)
Write-Host "Batch Purge block: $($bpBlock.Length) chars"

# Find the Workload Pattern Detection block
$wpStart = $fn.IndexOf("// === Workload Pattern Detection ===")
$wpIf = $fn.IndexOf("if (typeof detectSingleWorkloadPatterns", $wpStart)
# This is wrapped in: if (...) { setTimeout(function() { ... }, 300); }
$wpBrace = $fn.IndexOf("{", $wpIf + 30)
$braceCount4 = 1; $m = $wpBrace + 1
while ($braceCount4 -gt 0 -and $m -lt $fn.Length) {
    if ($fn[$m] -eq '{') { $braceCount4++ }
    elseif ($fn[$m] -eq '}') { $braceCount4-- }
    $m++
}
$wpBlockEnd = $m
while ($wpBlockEnd -lt $fn.Length -and ($fn[$wpBlockEnd] -eq "`r" -or $fn[$wpBlockEnd] -eq "`n" -or $fn[$wpBlockEnd] -eq " ")) { $wpBlockEnd++ }
$wpBlock = $fn.Substring($wpStart, $wpBlockEnd - $wpStart)
Write-Host "Workload Pattern block: $($wpBlock.Length) chars"

# ===== BUILD NEW EVIDENCE SECTION =====
# After the treemap, before Session Performance Intelligence, add:
# 1. Workload Pattern Analysis (synchronous, not setTimeout)
# 2. Batch Purge Detection

$wpInlineCode = @'

    // Workload Pattern Analysis (inline in Evidence)
    html += (function() {
        try {
            var _ev3 = events, _lp3 = lp, _sq3 = sqls;
            var _patterns;
            if (typeof detectSingleWorkloadPatterns === 'function') {
                _patterns = detectSingleWorkloadPatterns(_ev3, _lp3);
            } else if (typeof detectWorkloadPatterns === 'function') {
                _patterns = detectWorkloadPatterns([], _ev3, [], _lp3, [], _sq3);
            }
            if (!_patterns || !_patterns.length) return '';
            var sevCol = {warning:'#f59e0b', critical:'#ef4444', info:'#6366f1'};
            var _pHtml = _patterns.map(function(p) {
                var _col3 = sevCol[p.severity] || '#6366f1';
                return '<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 12px;border-radius:6px;background:' + _col3 + '11;border-left:3px solid ' + _col3 + ';margin-bottom:8px">'
                    + '<div style="margin-top:1px;flex-shrink:0">' + (p.icon||'') + '</div>'
                    + '<div><div style="font-size:11px;font-weight:700;color:' + _col3 + '">' + esc(p.title||'Pattern') + '</div>'
                    + '<div style="font-size:11px;color:#94a3b8;margin-top:3px;line-height:1.5">' + esc(p.detail||'') + '</div></div></div>';
            }).join('');
            return '<div class="card p-4 mb-4 fade-in"><div style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px"><span style="display:inline-block;width:3px;height:12px;background:#6366f1;border-radius:2px;margin-right:8px;vertical-align:middle"></span>Workload Pattern Analysis</div>' + _pHtml + '</div>';
        } catch(e) { console.warn('detectWorkloadPatterns failed', e); return ''; }
    })();

    // Batch Purge Detection (inline in Evidence)
    html += (function() {
        var purges = ctx.analytics?.batch_purges;
        if (!purges || !purges.length) return '';
        var rows = purges.map(function(p) {
            return '<div style="display:flex;align-items:flex-start;gap:10px;padding:9px 12px;border-radius:6px;background:rgba(249,115,22,0.08);border-left:3px solid #f97316;margin-bottom:8px">'
                + '<div><div style="font-size:11px;font-weight:700;color:#f97316">' + esc(p.sql_id || 'Unknown') + ' \u2014 Batch DELETE/Purge</div>'
                + '<div style="font-size:10px;color:#94a3b8;margin-top:3px">' + esc(p.sql_text_fragment || p.sql_text || '') + '</div>'
                + '<div style="font-size:10px;color:#64748b;margin-top:4px">Elapsed: ' + num(p.elapsed_secs || 0, 1) + 's \u00B7 Executions: ' + comma(p.executions || 0) + ' \u00B7 Physical Reads: ' + comma(p.physical_reads || 0) + '</div></div></div>';
        }).join('');
        return '<div class="card p-4 mb-4 fade-in"><div style="font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px"><span style="display:inline-block;width:3px;height:12px;background:#f97316;border-radius:2px;margin-right:8px;vertical-align:middle"></span>Batch Purge Detection</div>' + rows + '</div>';
    })();

'@

# ===== APPLY CHANGES =====
# Strategy: work from END of function to START to preserve offsets

# 1. Remove old Workload Pattern Detection block (at offset wpStart)
$newFn = $fn.Remove($wpStart, $wpBlock.Length)
Write-Host "Removed old WP block ($($wpBlock.Length) chars) at fn offset $wpStart"

# 2. Remove old Batch Purge Detection block (at offset bpStart)
# Recalculate offset since we just modified the string
$bpStartNew = $newFn.IndexOf("// Batch Purge Detection (always visible")
if ($bpStartNew -ge 0) {
    $bpIifeNew = $newFn.IndexOf("(function() {", $bpStartNew)
    $bpBraceNew = $newFn.IndexOf("{", $bpIifeNew + 12)
    $bc5 = 1; $n = $bpBraceNew + 1
    while ($bc5 -gt 0 -and $n -lt $newFn.Length) {
        if ($newFn[$n] -eq '{') { $bc5++ }
        elseif ($newFn[$n] -eq '}') { $bc5-- }
        $n++
    }
    $bpEndNew = $newFn.IndexOf(";", $n) + 1
    while ($bpEndNew -lt $newFn.Length -and ($newFn[$bpEndNew] -eq "`r" -or $newFn[$bpEndNew] -eq "`n" -or $newFn[$bpEndNew] -eq " ")) { $bpEndNew++ }
    $bpLenNew = $bpEndNew - $bpStartNew
    $newFn = $newFn.Remove($bpStartNew, $bpLenNew)
    Write-Host "Removed old BP block ($bpLenNew chars) at fn offset $bpStartNew"
}

# 3. Insert new inline WP + BP code before Session Performance Intelligence
$insertPoint = $newFn.IndexOf("// SESSION PERFORMANCE INTELLIGENCE")
$newFn = $newFn.Insert($insertPoint, $wpInlineCode + "`r`n`r`n    ")
Write-Host "Inserted inline WP + BP at fn offset $insertPoint"

# ===== WRITE BACK =====
$newC = $c.Substring(0, $fnStart) + $newFn + $c.Substring($fnEnd)
[System.IO.File]::WriteAllText($file, $newC)
Write-Host "File saved. New size: $($newC.Length) chars (was $($c.Length))"
