
lines = open('C:/Users/1039081/Downloads/cluade/awr-dashboard/backend/templates/index.html', encoding='utf-8').readlines()
s = e = -1
marker = "        let _wAct = '';\n"
for i, l in enumerate(lines):
    if l == marker and s == -1:
        s = i
    if '── Convergence line' in l and s != -1 and e == -1:
        e = i
        break
print('start:', s, 'line', s+1)
print('end:', e, 'line', e+1)
print('count:', e-s)
print('--- start context ---')
print(repr(lines[s]))
print(repr(lines[s+1]))
print('--- end context ---')
print(repr(lines[e-3]))
print(repr(lines[e-2]))
print(repr(lines[e-1]))
