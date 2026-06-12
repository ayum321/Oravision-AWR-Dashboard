"""Patch: replace bubble chart canvas with heat table div in the HTML."""
import re

path = 'backend/templates/index.html'
with open(path, encoding='utf-8') as f:
    content = f.read()

# Locate the Impact Map block and replace canvas with div
old_marker = 'Impact Map <span style="color:#334155;font-weight:400;text-transform:none;font-size:8.5px">'
new_label   = 'Wait Event Impact Ranking <span style="color:#334155;font-weight:400;text-transform:none;font-size:8.5px">bad period · worst to best</span></div>\n                            <div id="dash-wait-heat" style="max-height:210px;overflow-y:auto"></div>'

# We want to replace from the start of the label div to end of the canvas div
# Use regex to find the entire block
pattern = r'(font-size:9px;color:#475569;font-weight:700;text-transform:uppercase;letter-spacing:0\.5px;margin-bottom:2px">)Impact Map.*?</canvas></div>'
replacement = r'\1Wait Event Impact Ranking <span style="color:#334155;font-weight:400;text-transform:none;font-size:8.5px">bad period ' + '\u00b7' + r' worst to best</span></div>' + '\n' + r'                            <div id="dash-wait-heat" style="max-height:210px;overflow-y:auto"></div>'

content2, n = re.subn(pattern, replacement, content, count=1, flags=re.DOTALL)
if n:
    print(f'OK: replaced {n} occurrence(s)')
else:
    print('FAIL: pattern not found')
    idx = content.find('Impact Map')
    print(f'Impact Map found at index {idx}')
    print(repr(content[idx-80:idx+200]))

# Also fix grid div: add min-width:0 to grid container and right column
grid_old = 'display:grid;grid-template-columns:58% 1fr;gap:20px;align-items:start">'
grid_new = 'display:grid;grid-template-columns:58% 1fr;gap:20px;align-items:start;min-width:0">'
if grid_old in content2:
    content2 = content2.replace(grid_old, grid_new, 1)
    print('OK: grid min-width:0 added')
else:
    print('WARN: grid_old not found')

right_col_old = 'display:flex;flex-direction:column;gap:14px">'
right_col_new = 'display:flex;flex-direction:column;gap:14px;min-width:0;overflow:hidden">'
# Only replace the one inside this section — find by proximity
idx_grid = content2.find(grid_new)
search_area = content2[idx_grid:idx_grid+600]
if right_col_old in search_area:
    content2 = content2[:idx_grid] + search_area.replace(right_col_old, right_col_new, 1) + content2[idx_grid+600:]
    print('OK: right column min-width:0 added')
else:
    print('WARN: right_col_old not found in proximity')

if n:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content2)
    print('File written.')
