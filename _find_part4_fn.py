"""Find which function contains Part 4 and verify brace balance."""
content = open('backend/templates/index.html', encoding='utf-8').read()

# Part 4 is at pos ~938576
# Let's search for function declarations near this area
import re
# Find all function declarations within 50k chars before Part 4
region = content[880000:940000]
for m in re.finditer(r'function\s+(\w+)\s*\(', region):
    abs_pos = 880000 + m.start()
    print(f"  {m.group()[:60]}  at pos {abs_pos}")

print()
# The narrative function generateComparisonVerdictNarrative ends at 930163
# Part 4 is at 938576 — so it's in a DIFFERENT function
# It's probably in the function that CALLS generateComparisonVerdictNarrative
# or in the rendering function

# Let's find what's at pos 930000-940000
print("=== Context around Part 4 ===")
# Find the function that contains 938576
# Look for 'function' between 930163 and 938576
chunk = content[930000:940000]
for m in re.finditer(r'function\s+(\w+)', chunk):
    print(f"Function '{m.group(1)}' at abs pos {930000 + m.start()}")

print()
# Actually Part 1-3 were inside generateComparisonVerdictNarrative (ends at 930163)
# But Part 4 at 938576 is outside it. Let me check what's between 930163 and 938576
bridge = content[930100:938600]
# Find function declarations
for m in re.finditer(r'function\s+\w+', bridge):
    print(f"Function at {930100+m.start()}: {m.group()}")
    
# Show what's right after generateComparisonVerdictNarrative ends
print("\n=== After narrative fn ===")
print(content[930150:930300])

print("\n=== Just before Part 4 ===")
print(content[938400:938600])
