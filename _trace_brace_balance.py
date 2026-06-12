with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_line = 6774  # 0-indexed
end_line = 7089    # up to and including line 7089

brace_balance = 0
balance_history = []

for i in range(start_line, end_line + 1):
    line = lines[i]
    prev_balance = brace_balance
    for char in line:
        if char == '{':
            brace_balance += 1
        elif char == '}':
            brace_balance -= 1
    
    balance_history.append((i+1, prev_balance, brace_balance, line.rstrip()[:80]))
    
    # Show lines where balance changed
    if brace_balance != prev_balance:
        change = brace_balance - prev_balance
        if change < 0:
            print(f"Line {i+1}: balance {prev_balance} → {brace_balance} (closed {abs(change)})")
            print(f"  {line.rstrip()[:100]}")

print(f"\nFinal balance before line 7090: {brace_balance}")
print("(Should be 0 if all braces are balanced within the function body)")
print("(If > 0, there are unclosed braces. If < 0, there are extra closing braces)")

# Show the last few lines
print("\nLast 5 lines in range:")
for line_num, prev_bal, new_bal, content in balance_history[-5:]:
    print(f"Line {line_num}: balance={new_bal} {content}")
