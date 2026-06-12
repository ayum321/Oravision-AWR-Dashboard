"""
_check_js_syntax.py — stateful JS bracket-balance checker for index.html
Catches unbalanced () {} [] introduced by replace_string_in_file edits.

Uses a proper state machine with RECURSIVE template literal handling:
  • Skips single-quoted, double-quoted, and template-literal string contents
  • Handles ${ } nesting inside template literals at arbitrary depth
  • Skips line comments (//) and block comments (/* */)
  • Reports: line number + context when imbalance detected

Usage:
    py _check_js_syntax.py [path/to/index.html]
"""

import sys, re
from pathlib import Path

TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/templates/index.html")
if not TARGET.exists():
    print(f"ERROR: {TARGET} not found"); sys.exit(1)

html = TARGET.read_text(encoding="utf-8", errors="replace")
lines_all = html.splitlines()

# ── 1. Extract JS segments ───────────────────────────────────────────────────
def extract_js_segments(lines):
    segs = []
    in_script = False; seg_lines = []; seg_start = 0
    for i, line in enumerate(lines, 1):
        if re.search(r'<script\b', line, re.I) and '</script>' not in line:
            in_script = True; seg_start = i; seg_lines = []
        elif '</script>' in line and in_script:
            in_script = False
            segs.append((seg_start + 1, '\n'.join(seg_lines)))
            seg_lines = []
        elif in_script:
            seg_lines.append(line)
    return segs

# ── 2. Stateful tokenizer — yields (bracket_char, line_number) ───────────────
#
# Key design: skip_template_literal is RECURSIVE.  When inside a ${} block
# and we encounter a backtick, we call skip_template_literal again instead of
# naively scanning for the next backtick.  This correctly handles patterns like:
#   `outer ${cond ? `yes ${a}` : `no ${b}`} rest`
#
def bracket_tokens(code, base_line=1):
    i = 0; n = len(code); line = base_line

    def skip_string(quote):
        nonlocal i, line
        i += 1
        while i < n:
            c = code[i]
            if c == '\\': i += 2; continue
            if c == '\n': line += 1
            if c == quote: i += 1; break
            i += 1

    def skip_block_comment():
        nonlocal i, line
        i += 2
        while i < n - 1:
            if code[i] == '\n': line += 1
            if code[i] == '*' and code[i+1] == '/': i += 2; break
            i += 1

    def skip_template_literal():
        """Consume a template literal starting AFTER the opening backtick.
        Yields bracket tokens found inside ${} expressions.
        Handles nested template literals recursively."""
        nonlocal i, line
        i += 1  # skip opening backtick
        while i < n:
            c = code[i]
            if c == '\\': i += 2; continue
            if c == '\n': line += 1; i += 1; continue
            if c == '`': i += 1; return  # end of this template literal
            if c == '$' and i + 1 < n and code[i+1] == '{':
                # ${} expression — scan as JS code with depth tracking
                yield ('{', line); i += 2
                depth = 1
                while i < n and depth > 0:
                    ec = code[i]
                    if ec == '\n': line += 1; i += 1; continue
                    if ec == '\\': i += 2; continue
                    # Strings inside ${}
                    if ec in ('"', "'"):
                        skip_string(ec); continue
                    # Nested template literal inside ${} — RECURSIVE
                    if ec == '`':
                        yield from skip_template_literal(); continue
                    # Line comments inside ${}
                    if ec == '/' and i+1 < n and code[i+1] == '/':
                        while i < n and code[i] != '\n':
                            i += 1
                        continue
                    # Block comments inside ${}
                    if ec == '/' and i+1 < n and code[i+1] == '*':
                        skip_block_comment(); continue
                    # Regex literals inside ${}
                    if ec == '/' and i+1 < n and code[i+1] not in ('/', '*'):
                        j = i - 1
                        while j >= 0 and code[j] in ' \t': j -= 1
                        if j < 0 or code[j] in _rx_prev or code[j] == '/':
                            skip_regex(); continue
                    # Bracket tracking
                    if ec == '{': depth += 1; yield ('{', line)
                    elif ec == '}':
                        depth -= 1; yield ('}', line)
                        if depth == 0: i += 1; break
                    elif ec in '()[]': yield (ec, line)
                    i += 1
                continue
            i += 1

    # Characters that can precede a regex literal (not a division operator)
    _rx_prev = set('=({[,;:!&|?~^+-*/%<>\n')

    def skip_regex():
        """Skip a regex literal /pattern/flags."""
        nonlocal i, line
        i += 1  # skip opening /
        while i < n and code[i] != '\n':
            if code[i] == '\\': i += 2; continue
            if code[i] == '/': i += 1; break  # closing /
            i += 1
        # Skip flags (g, i, m, s, u, y, d)
        while i < n and code[i] in 'gimsuyd': i += 1

    while i < n:
        c = code[i]
        if c == '\n': line += 1; i += 1; continue
        if c == '/' and i+1 < n and code[i+1] == '/':
            while i < n and code[i] != '\n':
                i += 1
            continue
        if c == '/' and i+1 < n and code[i+1] == '*':
            skip_block_comment(); continue
        if c == '/' and i+1 < n and code[i+1] not in ('/', '*'):
            # Might be regex literal — check preceding non-whitespace char
            j = i - 1
            while j >= 0 and code[j] in ' \t': j -= 1
            if j < 0 or code[j] in _rx_prev or code[j] == '/':
                # Preceding context suggests regex, not division
                skip_regex(); continue
        if c in ('"', "'"):
            skip_string(c); continue
        if c == '`':
            yield from skip_template_literal(); continue
        if c in '(){}[]': yield (c, line)
        i += 1

# ── 3. Balance check ─────────────────────────────────────────────────────────
def check_segment(seg_text, base_line):
    errors = []
    pairs = {')': '(', '}': '{', ']': '['}
    openers = '({['
    stack = []
    for char, lineno in bracket_tokens(seg_text, base_line):
        if char in openers:
            stack.append((char, lineno))
        elif char in pairs:
            expected = pairs[char]
            if stack and stack[-1][0] == expected:
                stack.pop()
            else:
                last = f" (last open: '{stack[-1][0]}' at line {stack[-1][1]})" if stack else " (stack empty)"
                errors.append(f"Line {lineno}: Unmatched '{char}' — expected matching '{expected}'{last}")
                if stack: stack.pop()
    for char, lineno in stack[-5:]:
        errors.append(f"Line {lineno}: Unclosed '{char}' — no matching closer found")
    return errors

# ── 4. Run ───────────────────────────────────────────────────────────────────
segs = extract_js_segments(lines_all)
all_errors = []
for base, text in segs:
    all_errors.extend(check_segment(text, base))

print(f"\n{'='*62}")
print(f"  JS Bracket Balance — {TARGET.name}")
print(f"  {len(segs)} script block(s) · {len(lines_all):,} lines")
print(f"{'='*62}")

if not all_errors:
    print("  ✓ All parentheses, braces, and brackets are balanced.\n")
    sys.exit(0)
else:
    print(f"\n  ✗ {len(all_errors)} imbalance(s):\n")
    for e in all_errors[:20]:
        print(f"    ► {e}")
    if len(all_errors) > 20:
        print(f"    … and {len(all_errors)-20} more")
    print()
    sys.exit(1)
