with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    src = f.read()

# Fix the broken string in the WAIT_EVENT_CATALOG GC Buffer Busy fixAction
# The original has a premature closing quote: traffic.', updates shared
# Fix: remove the premature ' so the text becomes: traffic, updates shared
problem = "traffic.', updates shared"
solution = "traffic, updates shared"

if problem in src:
    src = src.replace(problem, solution, 1)
    print('Fixed: removed premature quote in fixAction string')
else:
    idx = src.find('updates shared')
    if idx >= 0:
        print('NOT FOUND. Context:', repr(src[max(0,idx-80):idx+100]))
    else:
        print('updates shared not found at all')

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(src)

print('Done')
