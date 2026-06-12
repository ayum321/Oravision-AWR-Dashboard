"""Fix Part 4 generic fallback for DB Time decrease."""
content = open('backend/templates/index.html', encoding='utf-8').read()

old_part4 = """    } else {
        part4 = `<strong>Step 1 — Generate full AWR SQL report for the problem period:</strong> ${code(`SELECT * FROM TABLE(DBMS_WORKLOAD_REPOSITORY.AWR_SQL_REPORT_HTML([dbid],[inst_num],[begin_snap],[end_snap]))`)}"""

new_part4 = """    } else {
        if (dtChange < -10) {
            part4 = `<strong>No Oracle-level remediation is required.</strong> DB Time fell ${Math.abs(dtChange).toFixed(0)}% — the database served less work, not slower work. Investigation should focus on: (1) Was the batch job or application process scheduled correctly? (2) Did upstream data feeds arrive on time and completely? (3) Were any application-level errors, exits, or short-circuits recorded in the job log? The AWR data confirms the Oracle infrastructure performed normally in both periods.`;
        } else {
            part4 = `<strong>Step 1 — Generate full AWR SQL report for the problem period:</strong> ${code(`SELECT * FROM TABLE(DBMS_WORKLOAD_REPOSITORY.AWR_SQL_REPORT_HTML([dbid],[inst_num],[begin_snap],[end_snap]))`)}"""

assert old_part4 in content, f"Part 4 generic pattern not found"
content = content.replace(old_part4, new_part4, 1)

# Now close the else block after the existing part4 assignment ends
# Find the end of the existing assignment after the replacement
marker = "drops below"
idx = content.find(marker, 951000)
end_line = content.find("`;", idx)
end_line += len("`;")
content = content[:end_line] + "\n        }" + content[end_line:]

from pathlib import Path
Path('backend/templates/index.html').write_text(content, encoding='utf-8')
print(f"Fixed Part 4 generic for DB Time decrease")
print(f"Saved ({len(content)} chars)")

# Verify
content2 = open('backend/templates/index.html', encoding='utf-8').read()
assert "No Oracle-level remediation is required" in content2
print("Assertions passed")
