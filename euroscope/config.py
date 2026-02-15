"""
EuroScope Configuration

All settings sourced from environment variables (with .env support).
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    api_key: str = ""
    api_base: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.4
    # Fallback provider
    fallback_api_key: str = ""
    fallback_api_base: str = "https://api.openai.com/v1"
    fallback_model: str = "gpt-4o-mini"


@dataclass
class TelegramConfig:
    token: str = ""
    allowed_users: list[int] = field(default_factory=list)


@dataclass
class DataConfig:
    brave_api_key: str = ""
    alphavantage_key: str = ""
    tiingo_key: str = ""
    fred_api_key: str = ""
    symbol: str = "EURUSD=X"  # Yahoo Finance symbol for EUR/USD
    update_interval_minutes: int = 15


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    data: DataConfig = field(default_factory=DataConfig)
    log_level: str = "INFO"
    data_dir: str = "data"

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        # Parse allowed users
        allowed_raw = os.getenv("EUROSCOPE_TELEGRAM_ALLOWED_USERS", "")
        allowed_users = []
        if allowed_raw:
            allowed_users = [int(uid.strip()) for uid in allowed_raw.split(",") if uid.strip()]

        return cls(
            llm=LLMConfig(
                api_key=os.getenv("EUROSCOPE_LLM_API_KEY", ""),
                api_base=os.getenv("EUROSCOPE_LLM_API_BASE", "https://api.deepseek.com"),
                model=os.getenv("EUROSCOPE_LLM_MODEL", "deepseek-chat"),
                max_tokens=int(os.getenv("EUROSCOPE_LLM_MAX_TOKENS", "4096")),
                temperature=float(os.getenv("EUROSCOPE_LLM_TEMPERATURE", "0.4")),
            ),
            telegram=TelegramConfig(
                token=os.getenv("EUROSCOPE_TELEGRAM_TOKEN", ""),
                allowed_users=allowed_users,
            ),
            data=DataConfig(
                brave_api_key=os.getenv("EUROSCOPE_BRAVE_API_KEY", ""),
                alphavantage_key=os.getenv("EUROSCOPE_ALPHAVANTAGE_KEY", ""),
                tiingo_key=os.getenv("EUROSCOPE_TIINGO_KEY", ""),
                fred_api_key=os.getenv("EUROSCOPE_FRED_API_KEY", ""),
            ),
            log_level=os.getenv("EUROSCOPE_LOG_LEVEL", "INFO"),
        )

    def validate(self) -> list[str]:
        """Return list of configuration warnings."""
        warnings = []
        if not self.llm.api_key:
            warnings.append("⚠️  EUROSCOPE_LLM_API_KEY not set — AI features disabled")
        if not self.telegram.token:
            warnings.append("⚠️  EUROSCOPE_TELEGRAM_TOKEN not set — Telegram bot disabled")
        if not self.data.alphavantage_key:
            warnings.append("⚠️  EUROSCOPE_ALPHAVANTAGE_KEY not set — AlphaVantage disabled")
        if not self.data.tiingo_key:
            warnings.append("⚠️  EUROSCOPE_TIINGO_KEY not set — Tiingo (deep history) disabled")
        if not self.data.fred_api_key:
            warnings.append("⚠️  EUROSCOPE_FRED_API_KEY not set — FRED macro data disabled")
        return warnings

    def validate_connections(self) -> dict[str, bool]:
        """
        Quick connectivity check for configured APIs.
        Returns {service_name: is_reachable}.
        """
        import urllib.request
        results = {}

        checks = [
            ("LLM API", self.llm.api_base),
            ("Telegram", "https://api.telegram.org"),
        ]

        for name, url in checks:
            try:
                req = urllib.request.Request(url, method="HEAD")
                urllib.request.urlopen(req, timeout=5)
                results[name] = True
            except Exception:
                results[name] = False

        return results

    def print_startup_summary(self):
        """Print a concise startup summary to the console."""
        warnings = self.validate()
        total = 5  # LLM, Telegram, AlphaVantage, Tiingo, FRED
        configured = total - len(warnings)

        print(f"  ✅ {configured}/{total} API keys configured")
        for w in warnings:
            print(f"  {w}")
        print()
