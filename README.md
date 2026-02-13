# 🌐 EuroScope

**AI-powered expert bot specialized exclusively in the EUR/USD forex pair.**

EuroScope is a Telegram bot that provides real-time technical analysis, classical pattern detection, fundamental analysis, AI-powered forecasting with self-learning, and interactive Q&A — all focused 100% on EUR/USD.

## Features

| Feature | Description |
|---------|-------------|
| 📊 **Technical Analysis** | RSI, MACD, EMA, Bollinger Bands, ATR, ADX, Stochastic |
| 🔍 **Pattern Detection** | Head & Shoulders, Double Top/Bottom, Triangles, Channels |
| 📐 **Key Levels** | Support/Resistance, Fibonacci Retracements, Pivot Points |
| 🎯 **Trading Signals** | Multi-indicator confluence scoring |
| 📰 **News Engine** | Real-time EUR/USD news via Brave Search |
| 📅 **Economic Calendar** | 15+ events (NFP, ECB, Fed, CPI, GDP...) with impact ratings |
| 🔮 **AI Forecasting** | LLM-powered directional forecasts with confidence scoring |
| 🧠 **Self-Learning** | Tracks prediction accuracy, adjusts from past mistakes |
| 📈 **Charts** | Dark-themed candlestick charts with EMA overlays |
| 💬 **Free-Form Q&A** | Ask any question about EUR/USD |

## Bot Commands

```
/price       — Current EUR/USD price & daily stats
/analysis    — Full technical analysis (specify timeframe: /analysis H4)
/chart       — Candlestick chart with indicators (/chart D1)
/patterns    — Detected classical chart patterns
/levels      — Support/resistance, Fibonacci & pivot points
/signals     — Multi-indicator trading signals
/news        — Latest EUR/USD news
/calendar    — Economic events that impact EUR/USD
/forecast    — AI directional forecast with confidence
/report      — Comprehensive daily report
/accuracy    — Prediction track record
/ask         — Ask anything about EUR/USD
```

## Quick Start

### 1. Clone & Install

```bash
cd EuroScope
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 2. Configure

```bash
copy .env.example .env
```

Edit `.env` with your API keys:

```env
EUROSCOPE_LLM_API_KEY=your-openrouter-key
EUROSCOPE_TELEGRAM_TOKEN=your-telegram-bot-token
EUROSCOPE_TELEGRAM_ALLOWED_USERS=your-telegram-user-id
EUROSCOPE_BRAVE_API_KEY=your-brave-api-key   # optional, for news
```

### 3. Run

```bash
python -m euroscope.main
```

## Architecture

```
euroscope/
├── config.py          # Environment-based configuration
├── main.py            # Entry point
├── bot/               # Telegram interface (12 commands)
├── brain/             # AI agent (LLM integration + self-learning memory)
├── data/              # Price provider, news, calendar, SQLite storage
├── analysis/          # Technical indicators, patterns, levels, signals
├── forecast/          # AI forecasting engine
└── utils/             # Charts, formatting
```

## Requirements

- Python 3.12+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- OpenRouter API key (or OpenAI-compatible)
- Brave Search API key (optional, for news)

## Tech Stack

- **Python** — AI/ML, data analysis, financial libraries
- **python-telegram-bot** — Telegram interface
- **OpenRouter/OpenAI** — LLM brain (Claude, GPT, etc.)
- **yfinance** — Real-time & historical price data
- **pandas + numpy** — Data processing & indicator calculations
- **mplfinance** — Professional chart generation
- **SQLite** — Prediction tracking & self-learning
- **httpx** — Async HTTP (news, LLM API)

## License

Private project.
