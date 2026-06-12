"""Fix Part 3 generic fallback for DB Time decrease."""
content = open('backend/templates/index.html', encoding='utf-8').read()

old_part3_generic = """    } else {
        part3 = `This regression is driven by a change in workload character rather than infrastructure failure"""

new_part3_generic = """    } else {
        if (dtChange < -10) {
            part3 = `No performance regression was identified. DB Time decreased ${Math.abs(dtChange).toFixed(0)}% between the <em>${esc(lbl1)}</em> and <em>${esc(lbl2)}</em> periods, and both periods share the same bottleneck profile. The database infrastructure performed normally in both snapshots. If a batch job or application process produced incorrect or incomplete results during the <em>${esc(lbl2)}</em> window, the root cause is at the application logic, scheduling, or data layer \\u2014 not the Oracle database.`;
        } else {
            part3 = `This regression is driven by a change in workload character rather than infrastructure failure"""

assert old_part3_generic in content, f"Part 3 generic pattern not found"
content = content.replace(old_part3_generic, new_part3_generic, 1)

# Need to close the extra if/else block - find the end of the old part3 assignment
idx = content.find("if the underlying access pattern is not addressed.", 937000)
end = content.find("`;", idx)
end += len("`;")
# Add closing brace for the else
content = content[:end] + "\n        }" + content[end:]

from pathlib import Path
Path('backend/templates/index.html').write_text(content, encoding='utf-8')
print(f"Fixed Part 3 generic for DB Time decrease")
print(f"Saved ({len(content)} chars)")

# Verify
assert "No performance regression was identified" in content
assert "application logic, scheduling, or data layer" in content
print("Assertions passed")
