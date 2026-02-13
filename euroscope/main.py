"""
EuroScope — EUR/USD Expert Bot

Main entry point. Loads config, validates, and starts the Telegram bot.
"""

import logging
import sys

from .config import Config
from .bot.telegram_bot import EuroScopeBot


def setup_logging(level: str = "INFO"):
    """Configure logging for EuroScope."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s │ %(levelname)-7s │ %(name)-28s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


def main():
    """Main entry point."""
    print(r"""
    ╔══════════════════════════════════════╗
    ║   🌐 EuroScope v0.1.0               ║
    ║   EUR/USD Expert Bot                 ║
    ╚══════════════════════════════════════╝
    """)

    # Load configuration
    config = Config.from_env()
    setup_logging(config.log_level)

    logger = logging.getLogger("euroscope")
    logger.info("EuroScope starting up...")

    # Validate configuration
    warnings = config.validate()
    for w in warnings:
        logger.warning(w)

    # Check critical requirements
    if not config.telegram.token:
        logger.error("❌ EUROSCOPE_TELEGRAM_TOKEN is required!")
        logger.error("   Create a bot via @BotFather on Telegram and set the token in .env")
        sys.exit(1)

    # Start bot
    bot = EuroScopeBot(config)
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("EuroScope shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
