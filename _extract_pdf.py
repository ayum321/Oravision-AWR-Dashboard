import fitz, re, json

doc = fitz.open(r'c:\Material\Personal\Good_BOOK&material\Oracle_Performance\database-performance-tuning-guide.pdf')

def extract(start_pg, end_pg):
    text = ''
    for pg in range(start_pg, min(end_pg+1, len(doc))):
        text += doc[pg].get_text()
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text

sections = {
    'ch03_perf_method':      extract(51, 58),
    'ch05_measuring':        extract(71, 77),
    'ch07_addm':             extract(124, 138),
    'ch08_awr_compare':      extract(139, 157),
    'ch10_instance_tuning':  extract(169, 209),
    'ch11_memory_alloc':     extract(219, 224),
    'ch13_buffer_cache':     extract(245, 261),
    'ch14_shared_pool':      extract(262, 289),
    'ch16_pga':              extract(306, 324),
}

with open('_oracle_pe_knowledge.json', 'w', encoding='utf-8') as f:
    json.dump(sections, f, ensure_ascii=False, indent=2)

for k, v in sections.items():
    print(f'{k}: {len(v):,} chars')
doc.close()
print('Done')
