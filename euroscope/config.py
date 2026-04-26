"""
EuroScope Configuration

All settings sourced from environment variables (with .env support).
Now hardened with Pydantic for strict type validation.
"""

import os
import logging
from typing import Optional, List, Tuple
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("euroscope.config")


class LLMConfig(BaseModel):
    api_key: str = "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"
    api_base: str = "https://integrate.api.nvidia.com/v1"
    model: str = "deepseek-ai/deepseek-v4-flash"
    max_tokens: int = 4096
    temperature: float = 0.4
    fallback_api_key: str = ""
    fallback_api_base: str = "https://api.openai.com/v1"
    fallback_model: str = "gpt-4o-mini"


class TelegramConfig(BaseModel):
    token: str = ""
    allowed_users: List[int] = Field(default_factory=list)
    web_app_url: str = ""


class DataConfig(BaseModel):
    brave_api_key: str = ""
    alphavantage_key: str = ""
    tiingo_key: str = ""
    fred_api_key: str = ""
    oanda_api_key: str = ""
    oanda_account_id: str = ""
    oanda_practice: bool = True
    capital_api_key: str = ""
    capital_identifier: str = ""
    capital_password: str = ""
    symbol: str = "EURUSD=X"
    update_interval_minutes: int = 15


class Config(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    api_secret_key: str = Field(default="euroscope-zenith-v5")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    
    log_level: str = "INFO"
    data_dir: str = "data"
    database_url: Optional[str] = None  # Added for Postgres Migration (Task 6.1)
    rate_limit_requests: int = 5
    rate_limit_window_minutes: int = 1
    admin_chat_ids: List[str] = Field(default_factory=list)
    vector_memory_ttl_days: int = 30
    proactive_analysis_interval_minutes: int = 15
    proactive_alert_cache_minutes: int = 15
    proactive_alert_chat_ids: List[int] = Field(default_factory=list)
    proactive_quiet_hours: Optional[Tuple[int, int]] = None
    proactive_disable_weekends: bool = True
    proactive_holiday_dates: List[str] = Field(default_factory=list)
    paper_trading_only: bool = True
    safety_news_block_minutes: int = 30
    safety_asian_min_confidence: float = 0.75
    safety_volatility_stop_min: int = 25
    safety_max_weekly_drawdown_pct: float = 6.0
    safety_max_monthly_drawdown_pct: float = 10.0
    safety_max_spread_pips: float = 8.0

    @classmethod
    def _validate_env_syntax(cls, filepath=".env"):
        """Check for common syntax errors in .env file."""
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        logger.warning(f"Malformed line {i+1} in {filepath}: Missing '='")
                    else:
                        key, val = line.split("=", 1)
                        if val.count('"') % 2 != 0 or val.count("'") % 2 != 0:
                            logger.warning(f"Malformed line {i+1} in {filepath}: Unclosed quote in {key.strip()}")
        except Exception as e:
            logger.debug(f"Could not validate .env syntax: {e}")

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        cls._validate_env_syntax()
        
        # Parse allowed users cleanly
        allowed_raw = os.getenv("EUROSCOPE_TELEGRAM_ALLOWED_USERS", "")
        allowed_users = [int(uid.strip()) for uid in allowed_raw.split(",") if uid.strip() and uid.strip().lstrip('-').isdigit()]
        
        admin_raw = os.getenv("EUROSCOPE_ADMIN_CHAT_IDS", "")
        admin_chat_ids = [cid.strip() for cid in admin_raw.split(",") if cid.strip()]
        
        primary_key = os.getenv("EUROSCOPE_LLM_API_KEY", "")
        fallback_key = os.getenv("EUROSCOPE_LLM_FALLBACK_API_KEY", "")
        
        proactive_chat_raw = os.getenv("EUROSCOPE_PROACTIVE_CHAT_IDS", "")
        proactive_chat_ids = [int(cid.strip()) for cid in proactive_chat_raw.split(",") if cid.strip() and cid.strip().lstrip('-').isdigit()]
        
        quiet_hours_raw = os.getenv("EUROSCOPE_PROACTIVE_QUIET_HOURS", "")
        quiet_hours = None
        if "-" in quiet_hours_raw:
            parts = [p.strip() for p in quiet_hours_raw.split("-", 1)]
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                quiet_hours = (int(parts[0]), int(parts[1]))
                
        holidays_raw = os.getenv("EUROSCOPE_PROACTIVE_HOLIDAYS", "")
        holiday_dates = [d.strip() for d in holidays_raw.split(",") if d.strip()]

        config_data = dict(
            api_secret_key=os.getenv("EUROSCOPE_API_SECRET", "euroscope-zenith-v5"),
            llm=LLMConfig(
                api_key=primary_key,
                api_base=os.getenv("EUROSCOPE_LLM_API_BASE", "https://api.deepseek.com"),
                model=os.getenv("EUROSCOPE_LLM_MODEL", "deepseek-chat"),
                max_tokens=int(os.getenv("EUROSCOPE_LLM_MAX_TOKENS", "4096")),
                temperature=float(os.getenv("EUROSCOPE_LLM_TEMPERATURE", "0.4")),
                fallback_api_key=fallback_key,
                fallback_api_base=os.getenv("EUROSCOPE_LLM_FALLBACK_API_BASE", "https://api.openai.com/v1"),
                fallback_model=os.getenv("EUROSCOPE_LLM_FALLBACK_MODEL", "gpt-4o-mini"),
            ),
            telegram=TelegramConfig(
                token=os.getenv("EUROSCOPE_TELEGRAM_TOKEN", ""),
                allowed_users=allowed_users,
                web_app_url=os.getenv("EUROSCOPE_TELEGRAM_WEB_APP_URL", ""),
            ),
            data=DataConfig(
                brave_api_key=os.getenv("EUROSCOPE_BRAVE_API_KEY", ""),
                alphavantage_key=os.getenv("EUROSCOPE_ALPHAVANTAGE_KEY", ""),
                tiingo_key=os.getenv("EUROSCOPE_TIINGO_KEY", ""),
                fred_api_key=os.getenv("EUROSCOPE_FRED_API_KEY", ""),
                oanda_api_key=os.getenv("EUROSCOPE_OANDA_API_KEY", ""),
                oanda_account_id=os.getenv("EUROSCOPE_OANDA_ACCOUNT_ID", ""),
                oanda_practice=os.getenv("EUROSCOPE_OANDA_PRACTICE", "1") != "0",
                capital_api_key=os.getenv("EUROSCOPE_CAPITAL_API_KEY", ""),
                capital_identifier=os.getenv("EUROSCOPE_CAPITAL_IDENTIFIER", ""),
                capital_password=os.getenv("EUROSCOPE_CAPITAL_PASSWORD", ""),
            ),
            log_level=os.getenv("EUROSCOPE_LOG_LEVEL", "INFO"),
            rate_limit_requests=int(os.getenv("EUROSCOPE_RATE_LIMIT_REQUESTS", "5")),
            rate_limit_window_minutes=int(os.getenv("EUROSCOPE_RATE_LIMIT_WINDOW_MINUTES", "1")),
            admin_chat_ids=admin_chat_ids,
            vector_memory_ttl_days=int(os.getenv("EUROSCOPE_VECTOR_MEMORY_TTL_DAYS", "30")),
            proactive_analysis_interval_minutes=int(os.getenv("EUROSCOPE_PROACTIVE_INTERVAL_MINUTES", "15")),
            proactive_alert_cache_minutes=int(os.getenv("EUROSCOPE_PROACTIVE_CACHE_MINUTES", "15")),
            proactive_alert_chat_ids=proactive_chat_ids,
            proactive_quiet_hours=quiet_hours,
            proactive_disable_weekends=os.getenv("EUROSCOPE_PROACTIVE_DISABLE_WEEKENDS", "1") != "0",
            proactive_holiday_dates=holiday_dates,
            paper_trading_only=os.getenv("EUROSCOPE_PAPER_TRADING_ONLY", "1") != "0",
            safety_news_block_minutes=int(os.getenv("EUROSCOPE_SAFETY_NEWS_BLOCK_MINUTES", "30")),
            safety_asian_min_confidence=float(os.getenv("EUROSCOPE_SAFETY_ASIAN_MIN_CONFIDENCE", "0.75")),
            safety_volatility_stop_min=int(os.getenv("EUROSCOPE_SAFETY_VOLATILITY_STOP_MIN", "25")),
            safety_max_weekly_drawdown_pct=float(os.getenv("EUROSCOPE_MAX_WEEKLY_DRAWDOWN", "6.0")),
            safety_max_monthly_drawdown_pct=float(os.getenv("EUROSCOPE_MAX_MONTHLY_DRAWDOWN", "10.0")),
            safety_max_spread_pips=float(os.getenv("EUROSCOPE_SAFETY_MAX_SPREAD_PIPS", "8.0")),
        )
        return cls(**config_data)

    def validate(self) -> List[str]:
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
        if not self.data.oanda_api_key and not self.data.capital_api_key:
            warnings.append("⚠️  Neither OANDA nor Capital.com API keys set — Real-time execution disabled!")
        return warnings

    async def validate_connections(self) -> dict[str, bool]:
        """Quick connectivity check for configured APIs."""
        import httpx
        import asyncio
        results = {}

        checks = [
            ("LLM API", self.llm.api_base),
            ("Telegram", "https://api.telegram.org"),
        ]

        async def check_url(name, url):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.head(url)
                return name, True
            except Exception as e:
                logger.debug(f"Configuration check for {name} failed: {e}")
                return name, False

        tasks = [check_url(name, url) for name, url in checks]
        for result in await asyncio.gather(*tasks):
            results[result[0]] = result[1]

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
