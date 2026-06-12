"""Fix escaped template literal variables in CPU_SATURATION query."""
path = "backend/templates/index.html"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

# The bad pattern has backslash-escaped $ in template literal
old = "AND    snap_id BETWEEN \\${_snB_b} AND \\${_snB_e}"
new = "AND    snap_id BETWEEN ${_snB_b} AND ${_snB_e}"
count = src.count(old)
print(f"Found {count} occurrences of escaped template vars")
if count > 0:
    src = src.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("Fixed: removed backslash escapes from template literals")
else:
    print("No fix needed — checking if already correct...")
    correct = "AND    snap_id BETWEEN ${_snB_b} AND ${_snB_e}"
    # Find in CPU_SATURATION context
    idx = src.find("Identify top CPU consumers by module and SQL")
    if idx > 0:
        chunk = src[idx:idx+500]
        if correct in chunk:
            print("Already correct!")
        else:
            print("WARNING: Neither pattern found near CPU consumer action")
            print(chunk[:300])
