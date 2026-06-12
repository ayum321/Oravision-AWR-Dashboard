"""Fix the generic Part 1 fallback to handle DB Time decrease."""
content = open('backend/templates/index.html', encoding='utf-8').read()

old_generic = """    } else {
        const aasGood = ctx.aas?.good || 0;
        const aasChg  = aasGood > 0 && aas2 > 0 ? ` (AAS: ${f1(aasGood)} \\u2192 ${f1(aas2)})` : '';
        part1 = `The <em>${esc(lbl2)}</em> period exhibited a significant increase in database workload intensity versus the <em>${esc(lbl1)}</em> baseline${aasChg}. The primary wait event <strong>"${esc(topWaitName)}"</strong> at ${f1(topWaitPct)}% DB Time identifies the dominant resource being contested \\u2014 the database is responding correctly to the demands placed on it, but those demands changed materially between the two periods.`;
    }"""

# Need to find the actual text - let me check the exact encoding
idx = content.find('exhibited a significant increase')
if idx < 0:
    print("ERROR: 'exhibited a significant increase' not found")
    exit(1)
    
# Get the exact text from the file
start = content.rfind('} else {', 0, idx)
end = content.find(';\n    }', idx) + len(';\n    }')
actual = content[start:end]
print("Found generic else block:")
print(repr(actual[:200]))
print("...")
print(repr(actual[-200:]))
print()

# Build replacement - handle both increase and decrease
new_generic = actual.replace(
    "exhibited a significant increase in database workload intensity versus",
    "${dtChange < -10 ? 'exhibited a significant decrease in database workload intensity versus' : 'exhibited a significant increase in database workload intensity versus'}"
).replace(
    "the database is responding correctly to the demands placed on it, but those demands changed materially between the two periods.",
    "${dtChange < -10 ? 'the database processed less total work in the problem period. The bottleneck profile is structurally similar between periods \\u2014 no regression mechanism was identified. If a job or process performed poorly, the root cause is likely at the application scheduling, data, or logic layer rather than the Oracle infrastructure.' : 'the database is responding correctly to the demands placed on it, but those demands changed materially between the two periods.'}"
)

content = content.replace(actual, new_generic, 1)
print("Fixed generic Part 1 for DB Time decrease")

# Also fix Part 2 generic fallback
idx2 = content.find('shift in bottleneck type between', 893647)
if idx2 > 0 and idx2 < 960000:
    # Get the full Part 2 generic block
    start2 = content.rfind('} else {', 893647, idx2)
    end2 = content.find(';\n    }', idx2) + len(';\n    }')
    actual2 = content[start2:end2]
    print(f"\nFound generic Part 2 at {start2}:")
    print(repr(actual2[:100]))
    
    new_generic2 = actual2.replace(
        "A shift in bottleneck type between",
        "${dtChange < -10 ? 'The bottleneck profile is consistent between' : 'A shift in bottleneck type between'}"
    ).replace(
        "indicates a structural change in workload character",
        "${dtChange < -10 ? 'confirms there is no infrastructure-level regression' : 'indicates a structural change in workload character'}"
    )
    
    # Only replace if the pattern changed
    if new_generic2 != actual2:
        content = content.replace(actual2, new_generic2, 1)
        print("Fixed generic Part 2 for DB Time decrease")
    else:
        print("Part 2 generic not modified (pattern unchanged)")

from pathlib import Path
Path('backend/templates/index.html').write_text(content, encoding='utf-8')
print(f"\nDone. File saved ({len(content)} chars)")
