"""
Patch: 3 targeted edits for multi-verdict co-existence.
FIX 1A — Score-magnitude tie-breaking in winner selection
FIX 1B — contributingVerdicts built and returned
FIX 1C — _buildContributingVerdictHtml helper + rendered in narrative
"""

FILE = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'

with open(FILE, encoding='utf-8') as f:
    src = f.read()

# ── FIX 1A ─────────────────────────────────────────────────────────────────────
# Add score-magnitude tie-breaking else-if after the existing !winner guard.

OLD_1A = (
    "        if (!isDQ && score > 0 && !winner) { winner = cat; winnerScore = score; }\n"
    "    }\n"
    "    const primaryVerdict = winner || 'INCONCLUSIVE';"
)

NEW_1A = (
    "        if (!isDQ && score > 0 && !winner) { winner = cat; winnerScore = score; }\n"
    "        else if (!isDQ && score > 0 && winner && (score - winnerScore) > 15) {\n"
    "            // Higher score wins if gap > 15 points — positional priority\n"
    "            // only applies to near-ties (within 15 points)\n"
    "            winner = cat; winnerScore = score;\n"
    "        }\n"
    "    }\n"
    "    const primaryVerdict = winner || 'INCONCLUSIVE';"
)

assert src.count(OLD_1A) == 1, f"FIX 1A: expected 1 match, got {src.count(OLD_1A)}"
src = src.replace(OLD_1A, NEW_1A, 1)

# ── FIX 1B part 1 ──────────────────────────────────────────────────────────────
# Insert contributingVerdicts derivation immediately after primaryVerdict.

OLD_1B1 = (
    "    const primaryVerdict = winner || 'INCONCLUSIVE';\n"
    "\n"
    "    // ---------------------------------------------------------------\n"
    "    // SECTION 8 — SIDE-EFFECT ROLE MAP"
)

NEW_1B1 = (
    "    const primaryVerdict = winner || 'INCONCLUSIVE';\n"
    "\n"
    "    // Contributing verdicts — fired but not primary\n"
    "    const contributingVerdicts = consideredCategories\n"
    "        .filter(c => c.score > 0 && !c.disqualified\n"
    "                     && c.category !== primaryVerdict)\n"
    "        .sort((a, b) => b.score - a.score)\n"
    "        .slice(0, 2);\n"
    "\n"
    "    // ---------------------------------------------------------------\n"
    "    // SECTION 8 — SIDE-EFFECT ROLE MAP"
)

assert src.count(OLD_1B1) == 1, f"FIX 1B1: expected 1 match, got {src.count(OLD_1B1)}"
src = src.replace(OLD_1B1, NEW_1B1, 1)

# ── FIX 1B part 2 ──────────────────────────────────────────────────────────────
# Add contributingVerdicts to the return object.

OLD_1B2 = (
    "        consideredCategories, categoryScores: scores,"
)

NEW_1B2 = (
    "        consideredCategories,\n"
    "        contributingVerdicts,\n"
    "        categoryScores: scores,"
)

assert src.count(OLD_1B2) == 1, f"FIX 1B2: expected 1 match, got {src.count(OLD_1B2)}"
src = src.replace(OLD_1B2, NEW_1B2, 1)

# ── FIX 1C step 1 ──────────────────────────────────────────────────────────────
# Insert _buildContributingVerdictHtml before generateComparisonVerdictNarrative.
# Uses string concatenation only — no nested template literals.

HELPER_FN = (
    "function _buildContributingVerdictHtml(cv) {\n"
    "    if (!cv || cv.score === 0) return '';\n"
    "    var labelMap = {\n"
    "        DOMINANT_SQL:    'Dominant SQL Load',\n"
    "        NEW_SQL:         'New SQL Introduced',\n"
    "        PLAN_CHANGE:     'Execution Plan Change',\n"
    "        SQL_REGRESSION:  'SQL Performance Regression',\n"
    "        CPU_SATURATION:  'CPU Saturation',\n"
    "        IO_BOTTLENECK:   'I/O Bottleneck',\n"
    "        COMMIT_LOGGING:  'Commit / Redo Logging Pressure',\n"
    "        WORKLOAD_GROWTH: 'Workload Volume Growth',\n"
    "        CONCURRENCY:     'Concurrency / Latch Contention',\n"
    "        LOGON_STORM:     'Logon Storm'\n"
    "    };\n"
    "    var label = labelMap[cv.category] || cv.category;\n"
    "    var reason = cv.reason || 'signals present but secondary to primary verdict';\n"
    "    return '<div style=\"margin-top:10px;padding:8px 12px;background:rgba(99,102,241,0.07);border-left:3px solid rgba(99,102,241,0.4);border-radius:6px;font-size:12px;color:#94a3b8\">'\n"
    "        + '<span style=\"color:#a5b4fc;font-weight:600;text-transform:uppercase;letter-spacing:0.04em\">'\n"
    "        + '&#9873; Also Detected: ' + label + '</span>'\n"
    "        + '<span style=\"margin-left:10px;color:#64748b\">Score: ' + cv.score.toFixed(0)\n"
    "        + ' \\u2014 ' + reason + '</span>'\n"
    "        + '</div>';\n"
    "}\n"
    "\n"
)

OLD_1C1 = "function generateComparisonVerdictNarrative(ctx, wkPatterns, sreConn) {"
NEW_1C1 = HELPER_FN + OLD_1C1

assert src.count(OLD_1C1) == 1, f"FIX 1C1: expected 1 match, got {src.count(OLD_1C1)}"
src = src.replace(OLD_1C1, NEW_1C1, 1)

# ── FIX 1C step 2 ──────────────────────────────────────────────────────────────
# Add _contributing extraction after _ev line inside the narrative function.

OLD_1C2 = (
    "    const _ev = ctx.evidence || ctx.verdict || {};\n"
    "    const _pv = _ev.primaryVerdict || 'UNKNOWN';"
)

NEW_1C2 = (
    "    const _ev = ctx.evidence || ctx.verdict || {};\n"
    "    const _contributing = _ev.contributingVerdicts || [];\n"
    "    const _pv = _ev.primaryVerdict || 'UNKNOWN';"
)

assert src.count(OLD_1C2) == 1, f"FIX 1C2: expected 1 match, got {src.count(OLD_1C2)}"
src = src.replace(OLD_1C2, NEW_1C2, 1)

# ── FIX 1C step 3 ──────────────────────────────────────────────────────────────
# Add ${_contributing.map(...)...} to the final return template literal.

OLD_1C3 = (
    "        ${sessionNote}\n"
    "        ${_peQueriesHtml}\n"
    "    </div>`;"
)

NEW_1C3 = (
    "        ${sessionNote}\n"
    "        ${_peQueriesHtml}\n"
    "        ${_contributing.map(_buildContributingVerdictHtml).join('')}\n"
    "    </div>`;"
)

assert src.count(OLD_1C3) == 1, f"FIX 1C3: expected 1 match, got {src.count(OLD_1C3)}"
src = src.replace(OLD_1C3, NEW_1C3, 1)

# ── Write ──────────────────────────────────────────────────────────────────────
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(src)

print(f"Done. File length: {len(src)} chars")

# ── Post-edit syntax validation ──────────────────────────────────────────────
import re
orphaned  = len(re.findall(r'`\s*;\s*\$\{', src))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', src))
contrib   = len(re.findall(r'contributingVerdicts', src))
helping   = len(re.findall(r'_buildContributingVerdictHtml', src))
tieBreak  = len(re.findall(r'score - winnerScore', src))
print(f"Syntax: orphaned={orphaned} brokenTag={brokenTag} (both must be 0)")
print(f"Symbols: contributingVerdicts={contrib} _buildContributingVerdictHtml={helping} tiebreak={tieBreak}")
