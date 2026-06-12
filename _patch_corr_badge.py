"""Wire correlation badge into 3-zone top-3 cards."""

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Find the exact line with "Zone-specific badge" and inject BEFORE it
marker = 'Zone-specific badge'
idx = content.find(marker)
if idx == -1:
    print('ERROR: marker not found')
    exit(1)

# Find the start of that comment line
line_start = content.rfind('\n', 0, idx) + 1
comment_line = content[line_start:content.find('\n', idx)]
print('Found comment: %s' % repr(comment_line.strip()[:60]))

inject = """
            // Wait correlation badge from unified registry
            const regEntry = AWRContext && AWRContext.sqlRegistry && AWRContext.sqlRegistry[s.id];
            const wc = regEntry && regEntry.waitCorrelation;
            const corrBadge = wc && wc.corrStrength > 5
                ? '<div style="margin-top:4px;padding:3px 8px;background:rgba(168,85,247,0.12);border:1px solid rgba(168,85,247,0.25);border-radius:5px;font-size:9px;color:#c4b5fd">&#9889; <b style="color:#a78bfa">'+esc(wc.corrDetail)+'</b>'+(AWRContext.sqlCorrelation&&AWRContext.sqlCorrelation.topWaitName ? ' &rarr; drives '+esc(AWRContext.sqlCorrelation.topWaitName) : '')+'</div>'
                : '';

"""

content = content[:line_start] + inject + content[line_start:]
print('Injected correlation lookup')

# 2. Find the card HTML and add corrBadge after headline, before border-t
headline_marker = '${headline}</div>'
# Search after the injection point
search_start = line_start + len(inject)
idx2 = content.find(headline_marker, search_start)
if idx2 == -1:
    print('ERROR: headline marker not found')
    exit(1)

# Find the end of this line
end_of_headline_line = content.find('\n', idx2)
# Find the next div with border-t
border_marker = '<div class="border-t pt-2"'
idx3 = content.find(border_marker, end_of_headline_line)
if idx3 == -1 or idx3 > end_of_headline_line + 500:
    print('ERROR: border-t div not found near headline')
    exit(1)

# Find the start of that line
border_line_start = content.rfind('\n', 0, idx3) + 1
indent = '                '
insert_text = indent + '${corrBadge}\n'
content = content[:border_line_start] + insert_text + content[border_line_start:]
print('Injected corrBadge display at offset %d' % border_line_start)

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
