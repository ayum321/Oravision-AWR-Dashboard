import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find script blocks
script_start = content.find('<script>')
script_end = content.rfind('</script>')

if script_start != -1 and script_end != -1:
    script_content = content[script_start + 8:script_end]
    
    # Count overall
    brace_open = script_content.count('{')
    brace_close = script_content.count('}')
    paren_open = script_content.count('(')
    paren_close = script_content.count(')')
    
    print(f"Overall counts:")
    print(f"  Braces: {brace_open} open, {brace_close} close, diff={brace_close-brace_open}")
    print(f"  Parens: {paren_open} open, {paren_close} close, diff={paren_close-paren_open}")
    
    # Find the extra/missing ones
    if brace_close > brace_open:
        print(f"\n  Finding {brace_close-brace_open} extra closing brace(s)...")
        # Find by tracking balance
        stack = []
        for i, char in enumerate(script_content):
            if char == '{':
                stack.append(i)
            elif char == '}':
                if not stack:
                    line_num = script_content[:i].count('\n') + 1
                    col = i - script_content.rfind('\n', 0, i)
                    # Get context
                    start = max(0, i-60)
                    end = min(len(script_content), i+60)
                    ctx = script_content[start:end].replace('\n', ' ').replace('  ', ' ')
                    print(f"  Line ~{line_num}, Pos {i}: ...{ctx}...")
                    break
                else:
                    stack.pop()
    
    if paren_close < paren_open:
        print(f"\n  Finding {paren_open-paren_close} unclosed paren(s)...")
        # Find by tracking balance
        stack = []
        for i, char in enumerate(script_content):
            if char == '(':
                stack.append(i)
            elif char == ')':
                if stack:
                    stack.pop()

        if stack:
            for pos in stack[:3]:
                line_num = script_content[:pos].count('\n') + 1
                # Get context
                start = max(0, pos-60)
                end = min(len(script_content), pos+60)
                ctx = script_content[start:end].replace('\n', ' ').replace('  ', ' ')
                print(f"  Line ~{line_num}, Pos {pos}: ...{ctx}...")
