with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Count braces just up to line 6877 (where the scoring section starts)
start = 6774  # line 6775
end = 6877    # line 6877

opens = 0
closes = 0

for i in range(start, end):
    line = lines[i]
    for j, char in enumerate(line):
        if char == '{':
            opens += 1
        elif char == '}':
            closes += 1
            if closes > opens:
                print(f"PROBLEM AT LINE {i+1}, CHAR {j}")
                print(f"  {line.rstrip()}")
                print(f"  Closes ({closes}) > Opens ({opens})")
                break

print(f"\nLines 6775-6877 (pre-scoring setup):")
print(f"  Opens: {opens}")
print(f"  Closes: {closes}")
print(f"  Net: {opens - closes}")

# Then from 6877 to 6898 (the scoring section)
opens2 = 0
closes2 = 0

for i in range(6876, 6898):  # line 6877 to 6898 (0-indexed 6876 to 6897)
    line = lines[i]
    for j, char in enumerate(line):
        if char == '{':
            opens2 += 1
        elif char == '}':
            closes2 += 1

print(f"\nLines 6877-6898 (scoring section):")
print(f"  Opens: {opens2}")
print(f"  Closes: {closes2}")
print(f"  Net: {opens2 - closes2}")

print(f"\nTotal 6775-6898:")
print(f"  Opens: {opens + opens2}")
print(f"  Closes: {closes + closes2}")
print(f"  Net: {opens + opens2 - closes - closes2}")
