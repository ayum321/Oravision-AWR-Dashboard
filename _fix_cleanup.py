"""Clean up the Part 1 generic block - remove leftover from previous bad fix."""
content = open('backend/templates/index.html', encoding='utf-8').read()

# Find the good block we just inserted
good_end = content.find("the Oracle infrastructure.`;", 909126)
if good_end < 0:
    print("ERROR: Can't find end of good block")
    exit(1)

# After our good block closes with "}\n    }", find where that is
# Our block ends with:  }\n    }
# Then there should be leftover garbage starting with " → ${f1..."
our_block_end = content.find('\n    }', good_end)
our_block_end += len('\n    }')
print(f"Our block ends at {our_block_end}")

# Now find where Part 2 starts: "// ----------" before "PART 2"
part2_start = content.find('// PART 2', our_block_end)
if part2_start < 0:
    # Try finding the next section delimiter
    part2_start = content.find('// -----', our_block_end)
print(f"Part 2 section starts at {part2_start}")

# The garbage is between our_block_end and the Part 2 delimiter
garbage = content[our_block_end:part2_start]
print(f"Garbage length: {len(garbage)}")
print(f"Garbage starts with: {repr(garbage[:100])}")
print(f"Garbage ends with: {repr(garbage[-100:])}")

if len(garbage) > 10:
    # Remove it, keep just a newline separator
    content = content[:our_block_end] + '\n\n    ' + content[part2_start:]
    print(f"Removed {len(garbage)} chars of garbage")
    
    from pathlib import Path
    Path('backend/templates/index.html').write_text(content, encoding='utf-8')
    print(f"Saved ({len(content)} chars)")
else:
    print("No garbage found - looks clean")
