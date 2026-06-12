"""Test if Jinja2 renders the full template."""
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('backend/templates'))
tmpl = env.get_template('index.html')
rendered = tmpl.render(request={'url': type('X', (), {'path': '/'})()})
print(f"Rendered length: {len(rendered)}")
print(f"Has PEEngine: {'PEEngine' in rendered}")
print(f"Has closing html: {'</html>' in rendered}")

# Also check raw file
with open('backend/templates/index.html', encoding='utf-8') as f:
    raw = f.read()
print(f"Raw file length: {len(raw)}")

if len(rendered) < len(raw) * 0.5:
    # Find where rendering stopped
    # Binary search for the last matching point
    for i in range(0, len(rendered), 10000):
        chunk = rendered[i:i+100]
        if chunk not in raw:
            print(f"Divergence around rendered char {i}")
            break
    # Show last 300 chars of rendered
    print(f"Last 300 rendered: {rendered[-300:]}")
