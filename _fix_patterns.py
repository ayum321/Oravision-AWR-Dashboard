with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 4a: Add LOAD_PROFILE_PATTERNS catalog before GENERIC METRIC SELECTION ENGINE
marker = '// GENERIC METRIC SELECTION ENGINE'
assert marker in content, "Could not find GENERIC METRIC SELECTION ENGINE"

idx = content.index(marker)
line_start = content.rfind('\n', 0, idx) + 1

patterns_block = '''// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// LOAD PROFILE PATTERNS — non-wait-event causal signals from Load Profile
// Each pattern: detect from Load Profile deltas, cross-ref with wait events
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const LOAD_PROFILE_PATTERNS = [
  {
    id: 'DML_SURGE',
    detect: (allDeltas) => {
        const bcd = allDeltas['lp_block_changes'];
        return bcd && bcd.delta_pct > 200;
    },
    score: (allDeltas) => {
        const bcd = allDeltas['lp_block_changes'];
        return bcd ? bcd.delta_pct / 100 : 0;
    },
    label: 'DML Volume Surge',
    detail: (allDeltas) => {
        const bcd = allDeltas['lp_block_changes'] || {};
        const red = allDeltas['lp_redo_size'] || {};
        return 'Block changes grew ' + num(bcd.delta_pct || 0, 0) + '% (' + num(bcd.good || 0, 0) + ' \\u2192 ' + num(bcd.bad || 0, 0) + '/s). '
            + 'Redo size grew ' + num(red.delta_pct || 0, 0) + '%. '
            + 'More rows modified per second \\u2014 cross-reference with log file sync wait event.';
    },
    relatedWaits: ['log file sync', 'log file parallel write', 'log buffer space'],
    verifyQuery: "SELECT name, value FROM v$sysstat\\nWHERE name IN ('user commits','user rollbacks','redo size')",
  },
  {
    id: 'PARSE_STORM',
    detect: (allDeltas) => {
        const hp = allDeltas['lp_hard_parses'];
        return hp && hp.delta_pct > 100;
    },
    score: (allDeltas) => {
        const hp = allDeltas['lp_hard_parses'];
        return hp ? hp.delta_pct / 100 : 0;
    },
    label: 'Hard Parse Storm',
    detail: (allDeltas) => {
        const hp = allDeltas['lp_hard_parses'] || {};
        const sp = allDeltas['eff_soft_parse_pct'] || {};
        return 'Hard parses grew ' + num(hp.delta_pct || 0, 0) + '% (' + num(hp.good || 0, 0) + ' \\u2192 ' + num(hp.bad || 0, 0) + '/s). '
            + 'Soft parse ratio: ' + num(sp.good || 0, 1) + '% \\u2192 ' + num(sp.bad || 0, 1) + '%. '
            + 'Application may not be using bind variables.';
    },
    relatedWaits: ['latch: shared pool', 'cursor: pin S wait on X', 'library cache lock'],
    verifyQuery: "SELECT namespace, gethits, gets, ROUND(gethitratio*100,2) hit_pct\\nFROM v$librarycache ORDER BY gets DESC FETCH FIRST 10 ROWS ONLY",
  },
  {
    id: 'REDO_PRESSURE',
    detect: (allDeltas) => {
        const redo = allDeltas['lp_redo_size'];
        return redo && redo.delta_pct > 200;
    },
    score: (allDeltas) => {
        const redo = allDeltas['lp_redo_size'];
        return redo ? redo.delta_pct / 100 : 0;
    },
    label: 'Redo Write Pressure',
    detail: (allDeltas) => {
        const redo = allDeltas['lp_redo_size'] || {};
        return 'Redo generation surged ' + num(redo.delta_pct || 0, 0) + '% (' + num((redo.good || 0)/1024, 0) + ' \\u2192 ' + num((redo.bad || 0)/1024, 0) + ' KB/s). '
            + 'LGWR under pressure \\u2014 cross-reference with log file sync and log file parallel write.';
    },
    relatedWaits: ['log file sync', 'log file parallel write', 'log buffer space'],
    verifyQuery: "SELECT name, value FROM v$sysstat\\nWHERE name IN ('redo size','redo writes','redo log space requests')",
  },
];

'''

content = content[:line_start] + patterns_block + content[line_start:]

# Fix 4b: Detect fired LOAD_PROFILE_PATTERNS in verdict builder
corr_marker = '3 corroborating metrics from different sections'
assert corr_marker in content, "Could not find corroborating metrics marker"

insert_idx = content.index(corr_marker)
# Go back to the start of that comment line
line_start2 = content.rfind('\n', 0, insert_idx) + 1

patterns_detect = '''    // Detect Load Profile patterns (DML_SURGE, PARSE_STORM, REDO_PRESSURE)
    const firedPatterns = [];
    for (const pat of LOAD_PROFILE_PATTERNS) {
        if (pat.detect(allDeltas)) {
            firedPatterns.push(pat);
            contextNotes.push(pat.label + ': ' + pat.detail(allDeltas));
            if (primary.type === 'wait_event' && pat.relatedWaits.some(w => w.toLowerCase() === primary.metric.toLowerCase())) {
                actionSteps.push({
                    what: 'Verify ' + pat.label + ' (causal signal for ' + primary.metric + ')',
                    query: pat.verifyQuery,
                });
            }
        }
    }

'''

content = content[:line_start2] + patterns_detect + content[line_start2:]

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fix 4 applied: LOAD_PROFILE_PATTERNS with DML_SURGE, PARSE_STORM, REDO_PRESSURE")
