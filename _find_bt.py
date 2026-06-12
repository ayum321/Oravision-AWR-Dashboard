"""
Find the unclosed template literal in index.html's main script.
Uses a simplified JS scanner that tracks template literal nesting.
"""
import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
main_script = max(scripts, key=len)
offset = content.find(main_script)
base_line = content[:offset].count('\n')

# Simple approach: scan line by line, tracking backtick balance
# Since template literals can nest via ${}, we track depth
# But for finding the ODD one, we can use a simpler trick:
# Walk through and toggle in/out of template literal. When we're
# left inside at EOF, the last "enter" is the unclosed one.

lines = main_script.split('\n')
bt_balance = 0
last_open_positions = []

for i, line in enumerate(lines):
    for ch in line:
        if ch == '`':
            bt_balance += 1
            if bt_balance % 2 == 1:  # Opening
                last_open_positions.append(i)
            else:  # Closing
                if last_open_positions:
                    last_open_positions.pop()

if bt_balance % 2 != 0:
    print(f"UNCLOSED template literal detected!")
    print(f"Backtick balance: {bt_balance} (odd)")
    if last_open_positions:
        suspect = last_open_positions[-1]
        print(f"\nLast unclosed template literal started at JS L{suspect+1} (file L{base_line + suspect + 1})")
        # Show context
        start = max(0, suspect - 3)
        end = min(len(lines), suspect + 8)
        for j in range(start, end):
            marker = '>>>' if j == suspect else '   '
            bt_in_line = lines[j].count('`')
            print(f"  {marker} L{base_line+j+1} ({bt_in_line} bt): {lines[j][:150]}")
    
    # Also find all lines with odd backtick counts (potential issue)
    print("\n--- Lines with odd backtick counts (potential problems) ---")
    running_bt = 0
    for i, line in enumerate(lines):
        count = line.count('`')
        if count > 0:
            old = running_bt
            running_bt += count
            if count % 2 != 0:
                # This line changes the overall parity - could be the problem
                print(f"  JS L{i+1} (file L{base_line+i+1}): {count} backtick(s), running total: {running_bt} {'(NOW ODD)' if running_bt % 2 != 0 else '(back to EVEN)'}")
                print(f"    {lines[i].strip()[:140]}")
else:
    print("Backtick count is even - no unclosed template literals")
