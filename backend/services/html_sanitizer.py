"""Small allowlist sanitizer for HTML fragments rendered by the dashboard."""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser

_ALLOWED_TAGS = {
    "b", "br", "code", "div", "em", "h4", "i", "li", "ol", "p", "span",
    "strong", "ul",
}
_VOID_TAGS = {"br"}
_BLOCKED_TAGS = {"embed", "iframe", "object", "script", "style"}


class _AllowlistParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in _BLOCKED_TAGS:
            self.blocked_depth += 1
        elif not self.blocked_depth and tag in _ALLOWED_TAGS:
            self.parts.append(f"<{tag}>")

    def handle_startendtag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if not self.blocked_depth and tag in _ALLOWED_TAGS:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _BLOCKED_TAGS:
            self.blocked_depth = max(0, self.blocked_depth - 1)
        elif not self.blocked_depth and tag in _ALLOWED_TAGS and tag not in _VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.parts.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        if not self.blocked_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.blocked_depth:
            self.parts.append(f"&#{name};")


def sanitize_html_fragment(value: str) -> str:
    """Return a display-safe subset of HTML with all attributes removed."""
    parser = _AllowlistParser()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.parts)
