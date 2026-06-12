"""Find the exact unpaired backtick by checking function-level balance."""
import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

BT = chr(96)

# Split into 500-line chunks and check each
lines = content.split('\n')
for start in range(0, len(lines), 500):
    end = min(start + 500, len(lines))
    chunk_bt = sum(line.count(BT) for line in lines[start:end])
    if chunk_bt % 2 != 0:
        print(f'L{start+1}-{end}: {chunk_bt} backticks (ODD)')
        # Narrow down to 50-line chunks
        for s2 in range(start, end, 50):
            e2 = min(s2 + 50, end)
            c2 = sum(line.count(BT) for line in lines[s2:e2])
            if c2 % 2 != 0:
                print(f'  L{s2+1}-{e2}: {c2} backticks (ODD)')
                # Narrow to 10-line chunks
                for s3 in range(s2, e2, 10):
                    e3 = min(s3 + 10, e2)
                    c3 = sum(line.count(BT) for line in lines[s3:e3])
                    if c3 % 2 != 0:
                        print(f'    L{s3+1}-{e3}: {c3} backticks (ODD)')
                        for j in range(s3, e3):
                            if lines[j].count(BT) > 0:
                                print(f'      L{j+1}: {lines[j].count(BT)} bt | {lines[j].strip()[:120]}')
                        break
                break
        break
