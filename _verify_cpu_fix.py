"""Verify all 3 fixes applied correctly."""
with open("backend/templates/index.html", "r", encoding="utf-8") as f:
    src = f.read()

# 1. Check CPU_SATURATION action block
marker = "} else if (cat === 'CPU_SATURATION')"
idx = src.find(marker)
if idx < 0:
    print("ERROR: CPU_SATURATION block not found!")
else:
    # Find end of the block (next else if)
    end = src.find("} else if (cat ===", idx + 10)
    block = src[idx:end]
    push_count = block.count("actions.push")
    print(f"1. CPU_SATURATION actions.push count: {push_count} (expected 1)")
    # Check merged query
    has_module_sql = "module, sql_id" in block
    has_pct_cpu = "pct_cpu" in block
    print(f"   Has combined module+sql_id query: {has_module_sql}")
    print(f"   Has pct_cpu analytics: {has_pct_cpu}")
    # Check old patterns are gone
    has_old1 = "Reduce concurrent workload" in block
    has_old2 = "Tune top-N CPU SQL" in block
    print(f"   Old action 1 removed: {not has_old1}")
    print(f"   Old action 2 removed: {not has_old2}")

# 2. Check _classify pattern
has_classify = "if (/cpu consumer/.test(t))" in src
# Verify it comes before /identify/
classify_idx = src.find("if (/cpu consumer/.test(t))")
identify_idx = src.find("if (/identify|review|attribut|ash analysis/.test(t))")
print(f"\n2. _classify 'cpu consumer' pattern exists: {has_classify}")
if has_classify:
    print(f"   Before /identify/ pattern: {classify_idx < identify_idx}")

# 3. Check _peContext pattern
has_pe = "// CPU saturation" in src and "cpu consumer" in src
# Verify it comes before /module/ pattern
pe_idx = src.find("// CPU saturation — top consumers")
module_idx = src.find("// ASH module attribution")
print(f"\n3. _peContext 'CPU saturation' pattern exists: {has_pe}")
if pe_idx > 0:
    print(f"   Before /module/ pattern: {pe_idx < module_idx}")

print("\nAll checks passed!" if push_count == 1 and has_module_sql and has_pct_cpu and not has_old1 and not has_old2 and has_classify and has_pe else "\nSOME CHECKS FAILED!")
