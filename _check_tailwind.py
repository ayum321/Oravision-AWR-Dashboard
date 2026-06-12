import re

with open('backend/static/css/tailwind.min.css', 'r') as f:
    css = f.read()

# Check which size classes are available
classes_to_check = [
    'w-3', 'w-3\\.5', 'w-4', 'w-5', 'w-6', 'w-8',
    'h-3', 'h-3\\.5', 'h-4', 'h-5', 'h-6', 'h-8',
    'flex', 'grid', 'hidden', 'block', 'inline',
    'text-xs', 'text-sm', 'text-lg', 'text-xl', 'text-2xl',
    'gap-2', 'gap-3', 'gap-4',
    'p-4', 'p-3', 'mb-4', 'mb-3', 'mb-2',
    'grid-cols-1', 'grid-cols-2', 'grid-cols-3', 'grid-cols-6',
    'rounded-lg', 'rounded-full',
    'items-center', 'justify-between', 'flex-wrap',
    'overflow-hidden', 'flex-shrink-0',
]

for cls in classes_to_check:
    pattern = r'\.' + cls + r'[\s{,:]'
    found = bool(re.search(pattern, css))
    status = 'OK' if found else 'MISSING!'
    print(f'.{cls.replace(chr(92), "")}: {status}')

# Also check for responsive prefixes  
print('\n--- Responsive ---')
for prefix in ['md\\:grid-cols-2', 'md\\:grid-cols-3', 'md\\:grid-cols-6']:
    found = bool(re.search(r'\.' + prefix + r'[\s{,:]', css))
    status = 'OK' if found else 'MISSING!'
    print(f'.{prefix.replace(chr(92), "")}: {status}')

print(f'\nTotal CSS size: {len(css)} bytes')
print(f'Total CSS rules (approx): {css.count("{")}')
