"""Fix the narrative Part 1/2 generic fallback properly (no nested template literals)."""
content = open('backend/templates/index.html', encoding='utf-8').read()

# Find the Part 1 generic else block
idx = content.find('exhibited a significant decrease')
if idx < 0:
    idx = content.find('exhibited a significant increase')
if idx < 0:
    print("ERROR: Can't find Part 1 generic")
    exit(1)

# Get the full else block
start = content.rfind('} else {\n', 0, idx)
end_marker = content.find(';\n    }', idx)
# Handle the multi-line block properly
# Find the closing of the else block
brace_count = 0
pos = start
while pos < len(content):
    if content[pos] == '{':
        brace_count += 1
    elif content[pos] == '}':
        brace_count -= 1
        if brace_count == 0:
            end = pos + 1
            break
    pos += 1

old_block = content[start:end]
print("OLD Part 1 generic block length:", len(old_block))
print(repr(old_block[:150]))

new_block = """} else {
        const aasGood = ctx.aas?.good || 0;
        const aasChg  = aasGood > 0 && aas2 > 0 ? ` (AAS: ${f1(aasGood)} \u2192 ${f1(aas2)})` : '';
        const _dtDecreased = dtChange < -10;
        if (_dtDecreased) {
            part1 = `The <em>${esc(lbl2)}</em> period exhibited a <strong>decrease</strong> in database workload intensity versus the <em>${esc(lbl1)}</em> baseline${aasChg}. DB Time fell ${Math.abs(dtChange).toFixed(0)}% \u2014 the database processed less total work. The bottleneck profile (<strong>"${esc(topWaitName)}"</strong> at ${f1(topWaitPct)}% DB Time) is structurally similar between periods \u2014 no regression mechanism was identified. If a job or process performed poorly, the root cause is likely at the application scheduling, data, or logic layer rather than the Oracle infrastructure.`;
        } else {
            part1 = `The <em>${esc(lbl2)}</em> period exhibited a significant increase in database workload intensity versus the <em>${esc(lbl1)}</em> baseline${aasChg}. The primary wait event <strong>"${esc(topWaitName)}"</strong> at ${f1(topWaitPct)}% DB Time identifies the dominant resource being contested \u2014 the database is responding correctly to the demands placed on it, but those demands changed materially between the two periods.`;
        }
    }"""

content = content.replace(old_block, new_block, 1)
print("Fixed Part 1 generic")

# Fix Part 2 generic
# Find it - should have "shift in bottleneck type" or our earlier replacement
for pattern in ['bottleneck profile is consistent between', 'shift in bottleneck type between', 'identifies the primary resource being contested. A shift']:
    idx2 = content.find(pattern, 920000)
    if idx2 > 0 and idx2 < 960000:
        break

if idx2 > 0 and idx2 < 960000:
    start2 = content.rfind('} else {\n', 920000, idx2)
    # Find closing brace
    brace_count2 = 0
    pos2 = start2
    while pos2 < len(content):
        if content[pos2] == '{':
            brace_count2 += 1
        elif content[pos2] == '}':
            brace_count2 -= 1
            if brace_count2 == 0:
                end2 = pos2 + 1
                break
        pos2 += 1
    
    old_part2 = content[start2:end2]
    print(f"\nOLD Part 2 generic length: {len(old_part2)}")
    print(repr(old_part2[:100]))
    
    new_part2 = """} else {
        if (dtChange < -10) {
            part2 = `The bottleneck profile is consistent between the <em>${esc(lbl1)}</em> and <em>${esc(lbl2)}</em> periods \u2014 <strong>"${esc(topWaitName)}"</strong> (${f1(topWaitPct)}% DB Time) was the dominant wait event in both snapshots. No infrastructure-level regression was identified. The database infrastructure served the workload correctly in both periods; the change in DB Time reflects a change in application demand, not Oracle performance.`;
        } else {
            part2 = `The dominant wait event <strong>"${esc(topWaitName)}"</strong> (${f1(topWaitPct)}% DB Time) identifies the primary resource being contested. A shift in bottleneck type between the <em>${esc(lbl1)}</em> and <em>${esc(lbl2)}</em> periods indicates a structural change in workload character \u2014 either a new SQL access pattern, data volume crossing a threshold that changes the optimizer\u2019s access path choice, or a combination of frequency and per-execution cost that pushed a previously minor bottleneck into the dominant position.`;
        }
    }"""
    
    content = content.replace(old_part2, new_part2, 1)
    print("Fixed Part 2 generic")
else:
    print(f"Part 2 generic not found (idx2={idx2})")

from pathlib import Path
Path('backend/templates/index.html').write_text(content, encoding='utf-8')
print(f"\nDone. File saved ({len(content)} chars)")
