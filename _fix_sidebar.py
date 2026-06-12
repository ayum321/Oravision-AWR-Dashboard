"""Fix sidebar nav buttons: bigger icons, bigger font, ambient hover"""
FILE = 'backend/templates/index.html'
with open(FILE, encoding='utf-8') as f:
    c = f.read()
orig = len(c)

# Update all remaining nav buttons (they all follow same pattern)
c = c.replace(
    'class="nav-btn flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs text-left hover:bg-Ccard transition"',
    'class="nav-btn flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-[13px] text-left hover:bg-white/5 transition"'
)

# Update all nav SVG icons from w-3.5 h-3.5 to w-4 h-4
c = c.replace(
    '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">',
    '<svg class="w-4 h-4 opacity-80" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
)

# Update nav-btn active styling in CSS or inline
# Make divider slightly more visible
c = c.replace(
    '<div class="my-1 border-t border-Cborder/60"></div>',
    '<div class="my-2 border-t border-indigo-500/15"></div>'
)

# Update bottom section
c = c.replace(
    '<div class="mt-auto pt-3 border-t border-Cborder/60 space-y-2">',
    '<div class="mt-auto pt-4 border-t border-indigo-500/15 space-y-2.5">'
)

# Update version badge
c = c.replace(
    '<div class="text-[10px] text-Cmuted/60">OraVision AWR Pro v3.0</div>',
    '<div class="text-[10px] text-indigo-300/40 font-medium">OraVision AWR Pro v3.0</div>'
)

print(f"delta: {len(c)-orig}")
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(c)
print("done")
