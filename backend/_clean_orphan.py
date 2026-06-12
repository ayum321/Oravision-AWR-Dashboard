"""
Clean up the orphaned body of the old generateComparisonVerdictNarrative function.
Strategy: find the first real filterDelta function (the one with .delta-row content)
and the duplicate/broken opening before it, then stitch cleanly.
"""
import re

with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the real filterDelta function body (the one with .delta-row)
# It appears AFTER the orphaned code.
# Mark: look for the double occurrence of filterDelta and keep only the second one.

# Strategy: find "function filterDelta(sev) {" occurrences
marker = 'function filterDelta(sev) {'
positions = [m.start() for m in re.finditer(re.escape(marker), content)]
print(f'Found {len(positions)} filterDelta declarations at positions: {positions}')

if len(positions) >= 2:
    # First occurrence is broken/orphaned, second is real
    first_pos = positions[0]
    second_pos = positions[1]
    
    # Remove everything from first_pos up to (but not including) second_pos
    # BUT: we need to check there's no "parts.join" after second_pos
    # (it should be clean from second_pos)
    removed_block = content[first_pos:second_pos]
    print(f'Removing {len(removed_block)} chars between first and second filterDelta')
    print('First 200 chars of removed block:', repr(removed_block[:200]))
    print('Last 200 chars of removed block:', repr(removed_block[-200:]))
    
    new_content = content[:first_pos] + content[second_pos:]
    
    # Verify no more orphans
    remaining = [m.start() for m in re.finditer(re.escape(marker), new_content)]
    print(f'After fix: {len(remaining)} filterDelta declarations')
    
    # Verify old parts are gone
    checks = [
        ('① SEVERITY gone', '\u2460 SEVERITY' not in new_content),
        ('⑦ ACTION gone', '\u2467 ACTION' not in new_content),
        ('parts.join(<br><br>) gone', "parts.join('<br><br>')" not in new_content),
    ]
    all_ok = True
    for label, result in checks:
        print(f'  {"OK" if result else "FAIL"}: {label}')
        if not result:
            all_ok = False
    
    if all_ok:
        with open('templates/index.html', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print('\nFile written successfully.')
    else:
        print('\nChecks failed — file NOT written.')
else:
    print('Could not find two filterDelta declarations — manual inspection needed.')
    # Print context around the one found
    if positions:
        print(repr(content[positions[0]-100:positions[0]+200]))
