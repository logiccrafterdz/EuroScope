"""
Message Formatting Helpers

Utilities for formatting Telegram messages.
"""

import re


def truncate(text: str, max_length: int = 4096) -> str:
    """Truncate text to fit Telegram's message limit."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 20] + "\n\n_...truncated_"


def escape_markdown(text: str) -> str:
    """Escape special Markdown characters for Telegram MarkdownV2."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_price(price: float) -> str:
    """Format price for display."""
    return f"{price:.5f}"


def format_pips(value: float) -> str:
    """Format a price difference as pips."""
    pips = abs(value) * 10000
    return f"{pips:.1f} pips"


def header(text: str, emoji: str = "📊") -> str:
    """Create a formatted header line."""
    return f"{emoji} *{text}*"


def rich_header(text: str, type: str = "main") -> str:
    """
    Create a stylized Unicode header.
    Types: main (Large/Bold), sub (Serif/Sleek), info (Italic/Clean)
    """
    # Mapping for pseudo-bold/serif icons and text styles
    headers = {
        "main": ("◈", "★"),
        "sub": ("▹", ""),
        "info": ("ℹ️", ""),
        "success": ("✅", ""),
        "warning": ("⚠️", ""),
        "signal": ("🎯", ""),
    }
    prefix, suffix = headers.get(type, ("◈", ""))
    
    # We use bold for now as Telegram's Unicode support for mathematical alphanumeric symbols 
    # can be inconsistent across fonts, but we enhance it with thematic characters.
    return f"{prefix} *{text.upper()}* {suffix}"


def progress_bar(percent: float, width: int = 10) -> str:
    """Create a sleek visual progress bar."""
    filled = int(round(percent * width))
    bar = "▩" * filled + "□" * (width - filled)
    return f"`{bar}` {percent*100:.0f}%"


def thematic_divider() -> str:
    """A high-end financial thematic divider."""
    return "◈" + "─" * 15 + "◈"


def priority_label(text: str, color: str = "blue") -> str:
    """Create a stylized box label for priority/status."""
    return f"⟦ *{text.upper()}* ⟧"


def divider() -> str:
    """A simple divider."""
    return "─" * 25


def safe_markdown(text: str) -> str:
    """
    Sanitize text for Telegram classic Markdown.

    Escapes unmatched *, _, ` and [ that would cause
    'Can't parse entities' BadRequest errors.
    """
    if not text:
        return text

    # 1. Escape [ to prevent it being treated as a link start
    text = text.replace("[", "\\[")

    # 2. Fix unmatched code markers (`) - if odd count, escape the last one
    backticks = [m.start() for m in re.finditer(r'(?<!\\)`', text)]
    if len(backticks) % 2 != 0:
        idx = backticks[-1]
        text = text[:idx] + "\\" + text[idx:]

    # 3. Handle markers outside of code blocks
    # Note: We find all non-escaped markers. If count is odd, we escape the last one.
    
    # Bold (*)
    asterisks = [m.start() for m in re.finditer(r'(?<!\\)\*', text)]
    if len(asterisks) % 2 != 0:
        idx = asterisks[-1]
        text = text[:idx] + "\\" + text[idx:]

    # Italic (_)
    underscores = [m.start() for m in re.finditer(r'(?<!\\)_', text)]
    if len(underscores) % 2 != 0:
        idx = underscores[-1]
        text = text[:idx] + "\\" + text[idx:]

    return text
