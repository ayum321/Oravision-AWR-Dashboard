"""
Patch: FIX 2A (ctx.meta derived fields) + FIX 2B (CPU threshold unification)
       + FIX 2C (adaptive IO latency threshold)
       + FIX 2D extract (physReadsDelta location report only)
"""

FILE = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'

with open(FILE, encoding='utf-8') as f:
    src = f.read()

# ── FIX 2A ─────────────────────────────────────────────────────────────────────
# Add snap_duration_seconds + db_time_ceiling to ctx.meta

OLD_2A = (
    "            window_delta_pct: windowDeltaPct,\n"
    "            cpu_count: cpuCount,\n"
    "            lbl1: data._label1 || 'Period 1',"
)

NEW_2A = (
    "            window_delta_pct: windowDeltaPct,\n"
    "            cpu_count: cpuCount,\n"
    "            snap_duration_seconds: elMin2 * 60,\n"
    "            db_time_ceiling: (elMin2 * 60) * cpuCount,\n"
    "            lbl1: data._label1 || 'Period 1',"
)

assert src.count(OLD_2A) == 1, f"FIX 2A: expected 1 match, got {src.count(OLD_2A)}"
src = src.replace(OLD_2A, NEW_2A, 1)

# ── FIX 2B step 1 ──────────────────────────────────────────────────────────────
# Insert _getCpuSatThreshold function immediately before buildEvidenceObject

CPU_THRESH_FN = (
    "function _getCpuSatThreshold(cpuCount) {\n"
    "    // Scales from 45% floor (low-CPU) to 70% ceiling (large systems)\n"
    "    // 2-CPU  ~ 48%   4-CPU ~ 55%   16-CPU ~ 65%   64-CPU = 70%\n"
    "    return Math.min(70, Math.max(45, 50 + (Math.log2(cpuCount || 1) * 3)));\n"
    "}\n"
    "\n"
)

OLD_2B1 = "function buildEvidenceObject(ctx, opts) {"
NEW_2B1 = CPU_THRESH_FN + OLD_2B1

assert src.count(OLD_2B1) == 1, f"FIX 2B1: expected 1 match, got {src.count(OLD_2B1)}"
src = src.replace(OLD_2B1, NEW_2B1, 1)

# ── FIX 2B step 2 ──────────────────────────────────────────────────────────────
# Replace the CPU_SATURATION scoring block to use _cpuThresh

OLD_2B2 = (
    "    // 5. CPU_SATURATION\n"
    "    if (dbCpuPct > 70 && (aasB/cpus) > 0.8 && hardParseDelta < 50) {\n"
    "        scores.CPU_SATURATION = 40 + dbCpuPct * 0.4;\n"
    "        scoreReasons.CPU_SATURATION = `DB CPU ${dbCpuPct.toFixed(0)}% DB Time, AAS/CPU=${(aasB/cpus).toFixed(2)}`;\n"
    "    } else { scores.CPU_SATURATION = 0; scoreReasons.CPU_SATURATION = `DB CPU ${dbCpuPct.toFixed(0)}% (>70%), AAS/CPU ${(aasB/cpus).toFixed(2)} (>0.8) — not both met`; }"
)

NEW_2B2 = (
    "    // 5. CPU_SATURATION\n"
    "    const _cpuThresh = _getCpuSatThreshold(cpus);\n"
    "    if (dbCpuPct > _cpuThresh && (aasB/cpus) > 0.8 && hardParseDelta < 50) {\n"
    "        scores.CPU_SATURATION = 40 + dbCpuPct * 0.4;\n"
    "        scoreReasons.CPU_SATURATION = `DB CPU ${dbCpuPct.toFixed(0)}% DB Time (threshold: ${_cpuThresh.toFixed(0)}%), AAS/CPU=${(aasB/cpus).toFixed(2)}`;\n"
    "    } else { scores.CPU_SATURATION = 0; scoreReasons.CPU_SATURATION = `DB CPU ${dbCpuPct.toFixed(0)}% (threshold: ${_cpuThresh.toFixed(0)}%), AAS/CPU ${(aasB/cpus).toFixed(2)} (>0.8) — not both met`; }"
)

assert src.count(OLD_2B2) == 1, f"FIX 2B2: expected 1 match, got {src.count(OLD_2B2)}"
src = src.replace(OLD_2B2, NEW_2B2, 1)

# ── FIX 2B step 3 ──────────────────────────────────────────────────────────────
# Update scorecard CPU signal: add _cpuThreshSc computation + update signal name/fired/threshold

OLD_2B3 = (
    "    var f = function(v){ return (+v||0).toFixed(1); };\n"
    "\n"
    "    var SIGNALS = {\n"
    "        CPU_SATURATION: [\n"
    "            { name:'DB CPU % >= 35%',                    fired: cpuPct2>=35,           value: f(cpuPct2)+'%',                    threshold:'>=35%',   panel:'Wait Events',   absentMeans:'CPU not dominant — seek wait-class bottleneck' },"
)

NEW_2B3 = (
    "    var f = function(v){ return (+v||0).toFixed(1); };\n"
    "\n"
    "    var _cpuThreshSc = _getCpuSatThreshold(cpus);\n"
    "\n"
    "    var SIGNALS = {\n"
    "        CPU_SATURATION: [\n"
    "            { name:'DB CPU % >= threshold', fired: cpuPct2>=_cpuThreshSc, value: f(cpuPct2)+'%', threshold:'>='+_cpuThreshSc.toFixed(0)+'%', panel:'Wait Events', absentMeans:'CPU not dominant — seek wait-class bottleneck' },"
)

assert src.count(OLD_2B3) == 1, f"FIX 2B3: expected 1 match, got {src.count(OLD_2B3)}"
src = src.replace(OLD_2B3, NEW_2B3, 1)

# ── FIX 2B step 4 ──────────────────────────────────────────────────────────────
# Update assertion A13 to use _cpuThresh

OLD_2B4 = (
    "    _assert('A13_CPU_SAT_NEEDS_HIGH_CPU',  !(primaryVerdict==='CPU_SATURATION')||dbCpuPct>70,          `CPU_SATURATION but dbCpuPct=${dbCpuPct.toFixed(0)}%`);"
)

NEW_2B4 = (
    "    _assert('A13_CPU_SAT_NEEDS_HIGH_CPU',  !(primaryVerdict==='CPU_SATURATION')||dbCpuPct>_cpuThresh,  `CPU_SATURATION but dbCpuPct=${dbCpuPct.toFixed(0)}% (threshold was ${_cpuThresh.toFixed(0)}%)`);"
)

assert src.count(OLD_2B4) == 1, f"FIX 2B4: expected 1 match, got {src.count(OLD_2B4)}"
src = src.replace(OLD_2B4, NEW_2B4, 1)

# ── FIX 2C ─────────────────────────────────────────────────────────────────────
# Replace the single-line slowestTs with the adaptive _ioLatThresh block,
# then update the signal definition's name and threshold string.

OLD_2C_TS = (
    "    var slowestTs  = tsIO.slice().sort(function(a,b){return (b.avg_read_ms||0)-(a.avg_read_ms||0);}).find(function(t){return (t.avg_read_ms||0)>5;});"
)

NEW_2C_TS = (
    "    // Infer storage class from median latency — determines dynamic threshold\n"
    "    var _allLatencies = tsIO\n"
    "        .map(function(t){return t.avg_read_ms||0;})\n"
    "        .filter(function(v){return v>0;})\n"
    "        .sort(function(a,b){return a-b;});\n"
    "    var _medianLat = _allLatencies.length > 0\n"
    "        ? _allLatencies[Math.floor(_allLatencies.length/2)]\n"
    "        : null;\n"
    "    var _ioLatThresh = _medianLat === null  ? 7\n"
    "                     : _medianLat < 2       ? 2    // SSD/NVMe\n"
    "                     : _medianLat > 8       ? 10   // HDD/SAN\n"
    "                     :                        5;   // mixed/unknown\n"
    "\n"
    "    var slowestTs  = tsIO.slice().sort(function(a,b){return (b.avg_read_ms||0)-(a.avg_read_ms||0);}).find(function(t){return (t.avg_read_ms||0) > _ioLatThresh;});"
)

assert src.count(OLD_2C_TS) == 1, f"FIX 2C (slowestTs): expected 1 match, got {src.count(OLD_2C_TS)}"
src = src.replace(OLD_2C_TS, NEW_2C_TS, 1)

OLD_2C_SIG = (
    "            { name:'Storage latency > 5ms (TS I/O)',     fired: !!slowestTs,           value: slowestTs ? f(slowestTs.avg_read_ms)+'ms' : 'N/A', threshold:'>5ms', panel:'TS I/O Stats', absentMeans:'Storage latency within SLA — volume, not speed, is the constraint' },"
)

NEW_2C_SIG = (
    "            { name:'Storage latency above threshold (TS I/O)', fired: !!slowestTs, value: slowestTs ? f(slowestTs.avg_read_ms)+'ms' : 'N/A', threshold:'>'+_ioLatThresh+'ms', panel:'TS I/O Stats', absentMeans:'Storage latency within SLA — volume, not speed, is the constraint' },"
)

assert src.count(OLD_2C_SIG) == 1, f"FIX 2C (signal): expected 1 match, got {src.count(OLD_2C_SIG)}"
src = src.replace(OLD_2C_SIG, NEW_2C_SIG, 1)

# ── Write ──────────────────────────────────────────────────────────────────────
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print(f"Done. File length: {len(src)} chars")

# ── Syntax check ──────────────────────────────────────────────────────────────
import re
orphaned  = len(re.findall(r'`\s*;\s*\$\{', src))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', src))
cpuFn     = len(re.findall(r'_getCpuSatThreshold', src))
snapDur   = len(re.findall(r'snap_duration_seconds', src))
ioThresh  = len(re.findall(r'_ioLatThresh', src))
cpuThreshSc = len(re.findall(r'_cpuThreshSc', src))
print(f"Syntax: orphaned={orphaned} brokenTag={brokenTag} (both must be 0)")
print(f"Symbols: _getCpuSatThreshold={cpuFn} snap_duration_seconds={snapDur} _ioLatThresh={ioThresh} _cpuThreshSc={cpuThreshSc}")

# ── FIX 2D: Report physReadsDelta location ─────────────────────────────────────
lines = src.splitlines()
for i, line in enumerate(lines):
    if 'physReadsDelta' in line and ('> 30' in line or '>30' in line):
        print(f"\nFIX 2D physReadsDelta location:")
        for j in range(max(0,i-2), min(len(lines),i+3)):
            print(f"  line {j+1}: {lines[j]}")
