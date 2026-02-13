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


def divider() -> str:
    """A simple divider."""
    return "─" * 25


def safe_markdown(text: str) -> str:
    """
    Sanitize text for Telegram classic Markdown.

    Strips unmatched *, _, and ` that would cause
    'Can't parse entities' BadRequest errors.
    """
    if not text:
        return text

    # Fix unmatched bold markers (*)
    # Count non-escaped * characters; if odd, remove the last one
    asterisks = [m.start() for m in re.finditer(r'(?<!\\)\*', text)]
    if len(asterisks) % 2 != 0:
        # Remove the last unmatched asterisk
        text = text[:asterisks[-1]] + text[asterisks[-1] + 1:]

    # Fix unmatched italic markers (_)
    underscores = [m.start() for m in re.finditer(r'(?<!\\)_', text)]
    if len(underscores) % 2 != 0:
        text = text[:underscores[-1]] + text[underscores[-1] + 1:]

    # Fix unmatched code markers (`)
    backticks = [m.start() for m in re.finditer(r'(?<!\\)`', text)]
    if len(backticks) % 2 != 0:
        text = text[:backticks[-1]] + text[backticks[-1] + 1:]

    return text
