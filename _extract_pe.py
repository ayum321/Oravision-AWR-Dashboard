import os
tmpl = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'
out = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\static\_pe_bootstrap.js'
with open(tmpl, encoding='utf-8') as f:
    lines = f.readlines()
pe = ''.join(lines[8549:9198])
build = ''.join(lines[1947:2194])
with open(out, 'w', encoding='utf-8') as f:
    f.write(build)
    f.write('\n\n')
    f.write(pe)
print('Wrote', os.path.getsize(out), 'bytes')
