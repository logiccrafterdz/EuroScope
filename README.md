# 🌐 EuroScope

**AI-powered expert bot specialized exclusively in the EUR/USD forex pair.**

EuroScope is an advanced multi-agent system that provides institutional-grade technical analysis, classical pattern detection, fundamental macro data, and AI-powered forecasting with vector memory — all focused 100% on EUR/USD.

## 🚀 Key Features

| Category | Features |
|:---|:---|
| 🧠 **AI Brain** | **Multi-Agent Architecture** (Specialists for Tech, Fund, Sent, Risk), **Vector Memory** (ChromaDB) for long-term learning, LLM Router with fallback support. |
| 🛡️ **Trading Brain** | **Risk Management** (Position sizing, ATR stop-loss, drawdown control), **Strategy Engine** (Trend Following, Mean Reversion, Breakouts). |
| 📊 **Analytics** | **Performance Metrics** (Sharpe, Sortino, Equity Curve), **Backtesting Engine** (historical candle replay), **System Health** monitor. |
| 🔍 **Market Analysis** | RSI, MACD, Patterns (H&S, Double Top), Fibonacci & Pivot levels, Brave Search News Sentiment. |
| 📰 **Macro Data** | Real-time FRED & ECB data integration (Rate differentials, CPI, GDP). |
| 🤖 **Telegram V2** | **Interactive UI** (Inline keyboards), **Notification Manager** (Scheduled reports + Real-time Alerts), **User Settings** portal. |

## 🤖 Bot Commands (V2)

| Primary Commands | Secondary & Trading |
|:---|:---|
| `/menu` — Main interactive dashboard | `/strategy` — Current strategy recommendation |
| `/price` — Real-time quotes & stats | `/risk` — Risk assessment for next trade |
| `/analysis` — Full TA report | `/trades` — Active & historical paper trades |
| `/chart` — Dark-themed candlesticks | `/performance` — Detailed ROI & Sharpe stats |
| `/forecast` — AI directional outlook | `/settings` — Your personal alert preferences |
| `/news` — Live sentiment & headlines | `/health` — System status & API connectivity |

## 🛠️ Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/logiccrafterdz/EuroScope.git
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
- `EUROSCOPE_LLM_API_KEY`: OpenRouter (primary LLM)
- `EUROSCOPE_TELEGRAM_TOKEN`: From [@BotFather](https://t.me/BotFather)
- `EUROSCOPE_BRAVE_API_KEY`: For news sentiment (optional)

### 3. Run
```bash
python -m euroscope.main
```

## 🏗️ Architecture (Multi-Agent)

```
euroscope/
├── analytics/         # Performance metrics, Backtesting & Health Monitor
├── bot/               # Telegram V2 (Inline keyboards & Notifications)
├── brain/             # Specialists (Technical, Fundamental, Sentiment, Risk)
│   └── memory.py      # Vector Memory (ChromaDB)
├── trading/           # Risk Management, Strategy Engine & Signal Execution
├── data/              # Multi-source Providers & SQLite Storage
├── analysis/          # Technical indicators & Pattern detection
└── forecast/          # AI Forecasting & LLM Routing
```

## 🧪 Testing
The project includes a robust test suite with **300+ passed tests** covering all core logic.
```bash
python -m pytest tests/
```

## 🧰 Tech Stack
- **Python 3.12+**
- **python-telegram-bot** (Async V2)
- **OpenRouter & OpenAI** (Multi-LLM)
- **ChromaDB** (Vector Memory)
- **yfinance** & **pandas**
- **SQLite** (Persistence)

## ⚖️ License
Private project.

