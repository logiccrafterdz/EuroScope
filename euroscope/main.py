"""
EuroScope — EUR/USD Expert Bot

Main entry point. Loads config, validates, and starts the Telegram bot.
"""

import logging
import sys

from .config import Config
from .bot.telegram_bot import EuroScopeBot
from .utils.logger import setup_structured_logging


def setup_logging(level: str = "INFO"):
    """Configure structured logging for EuroScope."""
    setup_structured_logging(level=level, log_dir="data/logs")


def main():
    """Main entry point."""
    print(r"""
    ╔══════════════════════════════════════╗
    ║   🌐 EuroScope v5.0.0               ║
    ║   EUR/USD Expert Bot (Skills-Based)  ║
    ╚══════════════════════════════════════╝
    """)

    # Load configuration
    config = Config.from_env()
    setup_logging(config.log_level)

    logger = logging.getLogger("euroscope")
    logger.info("EuroScope V5 starting up...")

    # Validate configuration
    config.print_startup_summary()
    warnings = config.validate()
    for w in warnings:
        logger.warning(w)

    # Check critical requirements
    if not config.telegram.token:
        logger.error("❌ EUROSCOPE_TELEGRAM_TOKEN is required!")
        logger.error("   Create a bot via @BotFather on Telegram and set the token in .env")
        sys.exit(1)

    # Health check is now handled via the integrated API server in EuroScopeBot
    # to avoid port conflicts on single-port platforms like Northflank/Heroku.

    # Start bot
    bot = EuroScopeBot(config)
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("EuroScope shutting down...")
    finally:
        pass


if __name__ == "__main__":
    main()
