const fs = require('fs');
const h = fs.readFileSync('backend/templates/index.html', 'utf8');
function chk(label, s, e) {
    const si = h.indexOf(s);
    if (si < 0) { console.log(label, 'ANCHOR NOT FOUND:', s.slice(0,40)); return; }
    const ei = h.indexOf(e, si);
    if (ei < 0) { console.log(label, 'END NOT FOUND:', e.slice(0,40)); return; }
    const b = h.slice(si, ei);
    let d = 0;
    for (const c of b) { if (c==='{') d++; else if (c==='}') d--; }
    console.log(label, d, d===0 ? 'OK' : 'UNBALANCED');
}
chk('T7+T8 _dt block:',
    '// T7 \u2014 Execution count swing: SQL ran materially',
    '// PART 2 \u2014 WHY IT HAPPENED');
chk('T8 prose block:',
    '// T8 \u2014 Append I/O instability note to part2',
    '// whyBlock \u2014 1-sentence mechanism visible');
chk('WAIT_QUEUE_NOT_CPU part2:',
    "} else if (_finalPv === 'WAIT_QUEUE_NOT_CPU') {",
    "} else if (_finalPv === 'CONCURRENCY') {");
chk('_inThisCaseParts chips:',
    '// Chip: DBWR process count + checkpoint write rate spike',
    'const _inThisCaseHtml = _inThisCaseParts.length');
chk('WAIT_QUEUE_NOT_CPU in MECHANISM_TEXT:',
    'WAIT_QUEUE_NOT_CPU: function(ctx) {',
    'GENERIC: function(ctx) {');
