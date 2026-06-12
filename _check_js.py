import re, subprocess, tempfile, os

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the main big script block
scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
main_script = max(scripts, key=len)

# Write to temp file and check with node
tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8')
tmp.write(main_script)
tmp.close()

result = subprocess.run(['node', '--check', tmp.name], capture_output=True, text=True)
if result.returncode != 0:
    print('SYNTAX ERROR:')
    print(result.stderr)
    # Map error line back to original
    err_lines = result.stderr.strip().split('\n')
    for el in err_lines:
        m = re.search(r':(\d+)', el)
        if m:
            js_line = int(m.group(1))
            # Find this line in original file
            script_start = content.find(main_script)
            orig_line = content[:script_start].count('\n') + js_line
            print(f'  -> Original file line: ~{orig_line}')
            # Show context
            lines = main_script.split('\n')
            start = max(0, js_line-5)
            end = min(len(lines), js_line+5)
            for j in range(start, end):
                marker = '>>>' if j == js_line-1 else '   '
                print(f'  {marker} {j+1}: {lines[j][:120]}')
else:
    print('No syntax errors found in main script block')

os.unlink(tmp.name)
