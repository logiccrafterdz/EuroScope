# Trade Journal Skill

> Full context trade logging and performance analysis

## Actions

| Action | Description | Parameters |
|--------|-------------|------------|
| `log_trade` | Record a new trade with full context | `direction`, `entry_price`, `stop_loss`, `take_profit`, `strategy`, `timeframe`, `regime`, `confidence`, `indicators`, `patterns`, `reasoning` |
| `close_trade` | Close a trade with outcome | `trade_id`, `exit_price`, `pnl_pips`, `is_win` |
| `get_journal` | Retrieve trade history | `strategy?`, `status?`, `limit?` |
| `get_stats` | Aggregate performance stats | `strategy?` |
