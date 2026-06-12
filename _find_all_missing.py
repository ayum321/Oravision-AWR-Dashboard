import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

with open('backend/static/css/tailwind.min.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Extract ALL Tailwind-style classes used in the HTML
# Match class="..." and class='...'
class_attrs = re.findall(r'class\s*=\s*["\']([^"\']+)["\']', html)
# Also match from JS strings like className = '...' or .className = '...'  
class_attrs += re.findall(r'className\s*=\s*["\']([^"\']+)["\']', html)
# Also backtick template classes
class_attrs += re.findall(r'class\s*=\s*[`]([^`]+)[`]', html)

all_classes = set()
for attr in class_attrs:
    # Remove template expressions ${...}
    clean = re.sub(r'\$\{[^}]+\}', '', attr)
    for cls in clean.split():
        # Only keep Tailwind-style classes (not custom CSS classes)
        if re.match(r'^[a-z]', cls) and not cls.startswith('fg-') and not cls.startswith('chain-'):
            all_classes.add(cls)

# Check each class against the CSS
missing = []
for cls in sorted(all_classes):
    escaped = re.escape(cls)
    if not re.search(r'\.' + escaped + r'[\s{,>:+~\[]', css):
        # Skip classes that are defined in inline <style> blocks
        if not re.search(r'\.' + escaped + r'[\s{,>:+~\[]', html.split('</style>')[0] if '</style>' in html else ''):
            missing.append(cls)

print(f"Total unique classes used: {len(all_classes)}")
print(f"Missing from CSS: {len(missing)}")
print("\nMissing classes:")
for cls in sorted(missing):
    print(f"  .{cls}")
