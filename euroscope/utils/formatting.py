"""
Message Formatting Helpers

Utilities for formatting Telegram messages.
"""


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
