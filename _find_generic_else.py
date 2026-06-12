"""Find the generic else fallback for Part 1 in the narrative."""
content = open('backend/templates/index.html', encoding='utf-8').read()

# Find Part 1 else clause (after all specific paths)
# The Part 1 code has: if (isSqlVerdict) ... else if (HW_ENQUEUE) ... else if ... else { generic }
# Look for the generic else before Part 2
idx = content.find("} else {\n", 917000)
while idx > 0 and idx < 930000:
    ctx = content[idx:idx+500]
    if 'part1' in ctx and 'significant increase' in ctx.lower():
        print(f"FOUND generic Part 1 else at {idx}:")
        print(ctx[:500])
        break
    elif 'part1' in ctx:
        print(f"Part 1 else candidate at {idx}:")
        print(ctx[:300])
        print()
    idx = content.find("} else {\n", idx+1)
    
# Also search for "significant increase" to find the exact text
idx2 = content.find("significant increase", 910000)
if idx2 > 0:
    print(f"\n'significant increase' at {idx2}:")
    print(content[idx2-200:idx2+300])
