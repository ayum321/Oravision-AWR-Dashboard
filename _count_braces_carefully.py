with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_line = 6774  # 0-indexed will be 6774
end_line = 7090   # 0-indexed will be 7089

brace_open_count = 0
brace_close_count = 0

for i in range(start_line, end_line):
    line = lines[i]
    for char in line:
        if char == '{':
            brace_open_count += 1
        elif char == '}':
            brace_close_count += 1

print(f"Lines {start_line+1} to {end_line}:")
print(f"  Opening braces: {brace_open_count}")
print(f"  Closing braces: {brace_close_count}")
print(f"  Difference: {brace_close_count - brace_open_count}")

# Check the function signature line
func_line = lines[6774].strip()
print(f"\nFunction line 6775: {func_line}")

# Count what we expect
# Line 6775: function_name() { = +1
# Lines 6776-7089: should have balanced braces within
# Line 7090: } = closes the function

# So in range 6775-7089, we should have 1 opening brace (from function line) 
# and (N closing braces where N is the number of closing braces in the function body)

print("\nExpected structure:")
print("  Line 6775: 'function _scoreCategories(...) {' has 1 opening brace")
print("  Lines 6776-7089: should have balanced braces")
print("  Line 7090: '}'  closes the function")
print("")
print("If closing > opening in the range, it means line 7090 has an extra closing brace")
if brace_close_count > brace_open_count:
    print(f"  ✓ Confirmed: {brace_close_count - brace_open_count} extra closing brace(s)")
