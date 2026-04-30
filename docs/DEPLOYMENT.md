# EuroScope Deployment Guide

This guide covers environment configuration, LLM provider setup, local execution, and production deployment via Docker.

## 1. Environment Configuration Reference

EuroScope is configured via environment variables. Copy `.env.example` to `.env` and adjust as needed. The configuration is validated strictly by Pydantic models at startup (`euroscope/config.py`).

| Variable | Type | Required | Default | Description |
|:---|:---|:---:|:---|:---|
| `EUROSCOPE_LLM_API_KEY` | string | ✅ | - | Primary LLM Provider API Key (NVIDIA NIM). |
| `EUROSCOPE_LLM_API_BASE` | string | - | `https://integrate.api.nvidia.com/v1` | Primary LLM Base URL. |
| `EUROSCOPE_LLM_MODEL` | string | - | `deepseek-ai/deepseek-v4-flash` | Primary LLM Model name. |
| `EUROSCOPE_LLM_FALLBACK_API_KEY` | string | - | - | Fallback LLM API Key (OpenAI). |
| `EUROSCOPE_TELEGRAM_TOKEN` | string | ✅ | - | Telegram Bot token from @BotFather. |
| `EUROSCOPE_TELEGRAM_ALLOWED_USERS`| list | - | `[]` | Comma-separated list of Telegram User IDs allowed to interact. |
| `EUROSCOPE_TELEGRAM_WEB_APP_URL` | string | - | - | URL to the Zenith TMA (Telegram Mini App). |
| `EUROSCOPE_ALPHAVANTAGE_KEY` | string | - | - | Alpha Vantage API key for fundamental data. |
| `EUROSCOPE_DATABASE_URL` | string | - | - | PostgreSQL URI. If unset, falls back to SQLite `data/euroscope.db`. |
| `EUROSCOPE_LOG_LEVEL` | string | - | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `EUROSCOPE_PROACTIVE_CHAT_IDS` | list | - | `[]` | Telegram Chat IDs to receive proactive market insights. |

## 2. LLM Provider Setup & Failover

EuroScope relies on LLMs for parsing, reasoning, and context generation. To ensure high availability, it implements an `LLMRouter`.

### 2.1 Primary Provider: NVIDIA NIM (DeepSeek V4)
The default configuration uses NVIDIA's optimized API for fast, cheap inference using `deepseek-v4-flash`.
- Generate an API key from `build.nvidia.com`.

### 2.2 Fallback Provider: OpenAI
If the primary provider experiences a timeout or 5xx error, the `LLMRouter` automatically fails over to the fallback provider.
- Configure `EUROSCOPE_LLM_FALLBACK_API_KEY` with an OpenAI key.
- The default fallback model is `gpt-4o-mini`.

## 3. Local Execution

For development and local paper trading:

1. **Install Dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure `.env`:**
   Ensure `EUROSCOPE_TELEGRAM_TOKEN` and `EUROSCOPE_LLM_API_KEY` are set.

3. **Run the Bot:**
   ```bash
   python main.py
   ```
   At startup, `container.py` resolves the topological dependency graph, initializing the `EventBus`, `Storage`, `SkillsRegistry`, and the `EuroScopeBot` polling loop.

## 4. Production Deployment (Docker / Northflank)

EuroScope is packaged in a highly optimized, multi-stage Docker image, running as a secure, unprivileged user.

### 4.1 Building the Image
```bash
docker build -t euroscope-v5 .
```

### 4.2 Docker Compose (with PostgreSQL)
For full production deployment, use `docker-compose.yml` to spin up both the bot and a PostgreSQL database.

```yaml
version: '3.8'
services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: euroscope
      POSTGRES_PASSWORD: your-secure-password
      POSTGRES_DB: euroscopedb
    volumes:
      - pgdata:/var/lib/postgresql/data

  bot:
    build: .
    environment:
      - EUROSCOPE_DATABASE_URL=postgresql+asyncpg://euroscope:your-secure-password@db:5432/euroscopedb
    env_file:
      - .env
    depends_on:
      - db
    volumes:
      - ./data:/app/data

volumes:
  pgdata:
```

### 4.3 Platform specific Notes (e.g., Northflank / Heroku)
- The integrated API server (for the Telegram Mini App and Healthchecks) runs on port `8080`.
- Ensure the deployment platform exposes port `8080` if webhooks or the TMA are used.
- Mount a persistent volume to `/app/data` to preserve logs and SQLite database (if PostgreSQL is not used).
