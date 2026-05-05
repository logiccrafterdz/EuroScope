# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.0.0] - 2026-05-05

### Added
- **Debate Engine Integration**: Implemented a comprehensive Multi-Agent Debate framework (Bull vs. Bear) with a Risk Manager and Conflict Arbiter.
- **Self-Learning Loop**: Added `Reflector` and `Decision Log` to autonomously evaluate past trades and improve future decision-making.
- Implemented dual-layer Spread Kill Switches and disk-persisted Emergency Modes to survive extreme market volatility and server crashes.

### Changed
- Migrated state persistence to PostgreSQL via SQLAlchemy 2.0.
- Integrated NVIDIA NIM (DeepSeek V4 Flash) as the primary intelligence engine.
- Replaced Brave Search API with DuckDuckGo for news retrieval.

### Security
- Revoked leaked API keys and improved secrets handling.
- Added explicit SECURITY and CONTRIBUTING guidelines for public launch.

## [4.0.0] - 2026-03-10

### Added
- Core multi-timeframe analysis capabilities.
- Telegram bot interface for real-time monitoring and control.
- Event Bus architecture for pub-sub inter-process communication.

*(Historical changes prior to v5.0.0 are available in the git commit history)*
