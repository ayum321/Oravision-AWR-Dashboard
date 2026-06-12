content = open('backend/templates/index.html', encoding='utf-8').read()
for pat in ['exhibited a significant', 'demands changed materially', 'workload intensity versus']:
    idx = content.find(pat, 893647)
    if idx > 0 and idx < 960000:
        print(f'Found "{pat}" at {idx}:')
        print(content[idx-300:idx+300])
        print()
        break
else:
    # Search broader
    for pat in ['part1 =', 'part2 =']:
        idx = 920000
        while idx < 935000:
            idx = content.find(pat, idx)
            if idx == -1: break
            ctx = content[idx:idx+80]
            print(f'{pat} at {idx}: {ctx!r}')
            idx += 1
