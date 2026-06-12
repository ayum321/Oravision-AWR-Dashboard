with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Count all braces from line 6775 to 6898
start = 6774  # 0-indexed
end = 6898    # 0-indexed
opens = 0
closes = 0

for i in range(start, end):
    line = lines[i]
    for char in line:
        if char == '{':
            opens += 1
        elif char == '}':
            closes += 1

print(f"Lines 6775-6898:")
print(f"  Opening braces: {opens}")
print(f"  Closing braces: {closes}")
print(f"  Net: {opens - closes}")

# So the first brace is at line 6775
# Line 6898 should NOT close the function if opens > closes
# If closes >= opens, then we've closed too much

print(f"\nExpected: opens should be > closes (function body is still open)")
print(f"Actual: opens={opens}, closes={closes}, net={opens-closes}")

if opens <= closes:
    print(f"\n⚠ ERROR: Function body closed too early!")
    print(f"  The function return statement must be between lines 6899-7090")
    print(f"  But our brace count shows the function ended at line 6898")
