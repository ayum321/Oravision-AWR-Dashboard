"""Fix Part 4 generic fallback for DB Time decrease (corrected indent)."""
content = open('backend/templates/index.html', encoding='utf-8').read()

old = '    } else {\n        part4 = `<strong>Step 1'
assert old in content, "Not found"

new = '    } else {\n        if (dtChange < -10) {\n            part4 = `<strong>No Oracle-level remediation is required.</strong> DB Time fell ${Math.abs(dtChange).toFixed(0)}% \\u2014 the database served less work, not slower work. Investigation should focus on: (1) Was the batch job or application process scheduled correctly? (2) Did upstream data feeds arrive on time and completely? (3) Were any application-level errors, exits, or short-circuits recorded in the job log? The AWR data confirms the Oracle infrastructure performed normally in both periods.`;\n        } else {\n        part4 = `<strong>Step 1'

content = content.replace(old, new, 1)

# Close the else block - find end of the old part4 generic assignment
idx = content.find('drops below', 951000)
end = content.find('`;', idx)
end += len('`;')
content = content[:end] + '\n        }' + content[end:]

from pathlib import Path
Path('backend/templates/index.html').write_text(content, encoding='utf-8')
print(f"Fixed Part 4. Saved ({len(content)} chars)")

# Verify
assert "No Oracle-level remediation is required" in content
print("OK")
