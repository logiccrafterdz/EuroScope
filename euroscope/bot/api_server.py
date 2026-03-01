"""
API Server Module for EuroScope Zenith.

Handles the AIOHTTP web server and API routes for the Mini App dashboard.
Extracted from telegram_bot.py to improve modularity.
"""

import os
import json
import logging
import asyncio
import traceback
from datetime import datetime
from aiohttp import web

from ..skills.base import SkillContext

logger = logging.getLogger("euroscope.api")


class APIServer:
    """
    Handles all API endpoints and the local web server for the Mini App.
    Delegates complex logic back to the main bot instance.
    """

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.config = bot_instance.config

    @web.middleware
    async def _cors_middleware(self, request, handler):
        """Middleware to handle CORS headers and preflight requests."""
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            try:
                response = await handler(request)
            except Exception as e:
                logger.error(f"API Error ({request.path}): {e}")
                response = web.json_response({"success": False, "error": str(e)}, status=500)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        return response

    async def _api_summary(self, request):
        """API endpoint for live price and sentiment summary."""
        logger.debug("API: Fetching market summary...")
        result = await self.bot.orchestrator.run_skill("market_data", "get_price")
        if not result.success:
            return web.json_response({"success": False, "error": result.error})
        data = result.data
        resp = {
            "success": True,
            "symbol": "EUR/USD",
            "price": data.get("price", 0),
            "change": data.get("change", 0),
            "change_pct": data.get("change_pct", 0),
            "high": data.get("high"),
            "low": data.get("low"),
            "open": data.get("open"),
            "range_pips": data.get("spread_pips", 0),
            "sentiment": "bullish" if data.get("change", 0) >= 0 else "bearish",
            "timestamp": datetime.now().isoformat(),
        }
        return web.json_response(resp)

    async def _api_status(self, request):
        """API endpoint for market status, sessions and trading hours."""
        logger.debug("API: Fetching market status and session context...")
        ctx = SkillContext()
        result_mkt = await self.bot.orchestrator.run_skill("market_data", "check_market_status")
        mkt_data = result_mkt.data if result_mkt.success else {"status": "Closed"}
        res_session = await self.bot.orchestrator.run_skill("session_context", "detect", context=ctx)
        session_data = res_session.data if res_session.success else {"session_regime": "unknown"}
        # Check WebSocket connection status
        ws_status = "DISCONNECTED"
        if hasattr(self.bot, "ws_client") and self.bot.ws_client:
            import websockets
            if self.bot.ws_client.ws and self.bot.ws_client.ws.state.name == "OPEN":
                ws_status = "CONNECTED"

        return web.json_response({
            "success": True,
            "data": {
                "status": mkt_data.get("status", "Closed"),
                "ws_status": ws_status,
                "session": session_data.get("session_regime", "unknown").upper(),
                "rules": session_data.get("session_rules", {}),
                "timestamp": datetime.now().isoformat(),
            }
        })

    async def _api_forecast(self, request):
        """API endpoint for deep AI forecasting and reasoning."""
        logger.debug("API: Running deep AI forecast...")
        try:
            tf = request.query.get("timeframe", "24 hours")
            result = await self.bot.forecaster.generate_forecast(tf)
            return web.json_response({
                "success": True,
                "data": {
                    "direction": result.get("direction", "NEUTRAL"),
                    "confidence": result.get("confidence", 0) / 100,
                    "reasoning": result.get("text", ""),
                    "timeframe": tf,
                    "price": result.get("price"),
                    "timestamp": datetime.now().isoformat(),
                }
            })
        except Exception as e:
            logger.error(f"API forecast error: {e}")
            return web.json_response({
                "success": False,
                "error": str(e),
                "data": {
                    "direction": "NEUTRAL",
                    "confidence": 0,
                    "reasoning": "Forecasting engine error.",
                },
            })

    async def _api_macro(self, request):
        """API endpoint for fundamental macro data (FRED/ECB)."""
        logger.debug("API: Fetching fundamental macro overview...")
        ctx = SkillContext()
        res = await self.bot.orchestrator.run_skill("fundamental_analysis", "get_macro", context=ctx)
        if not res.success:
            return web.json_response({
                "success": False,
                "partial": True,
                "error": res.error,
                "data": {"macro_impact": "NEUTRAL", "macro_data": {}},
            })
        return web.json_response({
            "success": True,
            "data": res.data,
            "formatted": res.metadata.get("formatted", ""),
        })

    async def _api_signals(self, request):
        """API endpoint for recent trading signals."""
        logger.debug("API: Fetching recent signals...")
        # Await the storage method since we migrated Storage to async
        signals = await self.bot.storage.get_signals(limit=5)
        return web.json_response({"success": True, "signals": signals})

    async def _api_trades(self, request):
        """API endpoint for active open trades."""
        logger.debug("API: Fetching open trades...")
        res = await self.bot.orchestrator.run_skill("signal_executor", "list_trades")
        if not res.success:
            return web.json_response({"success": False, "error": res.error, "trades": []})
        return web.json_response({"success": True, "trades": res.data})

    async def _api_history(self, request):
        """API endpoint for closed trade history."""
        logger.debug("API: Fetching closed trade history...")
        res = await self.bot.orchestrator.run_skill("signal_executor", "trade_history")
        if not res.success:
            return web.json_response({"success": False, "error": res.error, "history": []})
        history = res.data[-20:] if res.data else []
        history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return web.json_response({"success": True, "history": history})

    async def _api_scan_signals(self, request):
        """API endpoint to actively scan for and generate new trading signals."""
        logger.debug("API: Actively scanning for new signals (Mini App request)...")
        try:
            if self.bot.bot_settings.get("emergency_mode"):
                return web.json_response({"success": False, "error": "SYSTEM IS IN EMERGENCY MODE. TRADING AND SCANNING HALTED."})

            ctx = SkillContext()
            
            # 1. Fetch live market price
            mkt_res = await self.bot.orchestrator.run_skill("market_data", "get_price", context=ctx)
            if not mkt_res.success:
                return web.json_response({"success": False, "error": f"Market data failed: {mkt_res.error}"})
                
            ta_res = await self.bot.orchestrator.run_skill("technical_analysis", "analyze", context=ctx, timeframe="H1")
            if not ta_res.success:
                return web.json_response({"success": False, "error": f"TA failed: {ta_res.error}"})
                
            strat_res = await self.bot.orchestrator.run_skill("trading_strategy", "detect_signal", context=ctx)
            if not strat_res.success:
                return web.json_response({"success": False, "error": f"Strategy failed: {strat_res.error}"})
                
            signal_data = strat_res.data
            direction = signal_data.get("direction", "WAIT")
            confidence = signal_data.get("confidence", 0)
            
            if direction in ("BUY", "SELL") and confidence >= 50:
                # 3. Calculate Risk Parameters
                risk_res = await self.bot.orchestrator.run_skill("risk_management", "assess_trade", context=ctx)
                if not risk_res.success:
                    return web.json_response({"success": False, "error": f"Risk calculation failed: {risk_res.error}"})
                    
                # 4. Execute the paper trade IF auto-trading is enabled
                if self.bot.bot_settings.get("auto_trading_enabled"):
                    exec_res = await self.bot.orchestrator.run_skill("signal_executor", "open_trade", context=ctx)
                    if exec_res.success:
                        return web.json_response({"success": True, "signal": exec_res.data, "message": f"Found {direction} opportunity and execution successful!"})
                    else:
                        return web.json_response({"success": False, "error": f"Signal generation aborted by guardrails: {exec_res.error}", "signal": signal_data})
                else:
                    return web.json_response({"success": True, "signal": signal_data, "execution_skipped": True, "message": f"Found {direction} opportunity! (Auto-trading is DISABLED)"})
            else:
                return web.json_response({"success": False, "message": "No high-confidence opportunities currently available. Please exercise patience."})
        except Exception as e:
            logger.error(f"API: Error scanning signals: {e}\n{traceback.format_exc()}")
            return web.json_response({"success": False, "error": str(e)})

    async def _api_alerts(self, request):
        """API endpoint for active price alerts."""
        logger.debug("API: Fetching active alerts...")
        # Since storage is async now
        alerts = await self.bot.storage.get_active_alerts()
        return web.json_response({"success": True, "alerts": alerts})

    async def _api_analysis(self, request):
        """API endpoint for technical analysis snapshot."""
        logger.debug("API: Running real-time technical analysis...")
        ctx = SkillContext()
        res_ta = await self.bot.orchestrator.run_skill("technical_analysis", "analyze", context=ctx, timeframe="H1")
        ta_data = res_ta.data if res_ta.success and res_ta.data else {"indicators": {}, "overall_bias": "NEUTRAL"}
        
        # Add Real-time Sentiment (Optimized ONNX)
        sentiment_data = {"label": "NEUTRAL", "score": 0.5}
        try:
            from ..data.sentiment import analyze_sentiment_onnx
            if res_ta.success:
                mood_phrase = f"EURUSD is currently {ta_data.get('overall_bias', 'neutral')}."
            else:
                mood_phrase = "EURUSD market status is unknown."
            
            res_sent = analyze_sentiment_onnx(mood_phrase)
            sentiment_data = {
                "label": res_sent["label"],
                "score": res_sent["score"],
                "provider": res_sent["provider"]
            }
        except Exception as e:
            logger.warning(f"API: Sentiment analysis failed: {e}")

        return web.json_response({
            "success": res_ta.success,
            "partial": not res_ta.success,
            "error": res_ta.error if not res_ta.success else None,
            "data": ta_data,
            "sentiment": sentiment_data,
            "formatted": res_ta.metadata.get("formatted") if res_ta.metadata else None
        })

    async def _api_candles(self, request):
        """API endpoint for chart data (OHLC) with strict time sorting."""
        timeframe = request.query.get("timeframe", "H1")
        logger.debug(f"API: Fetching {timeframe} candles for chart...")
        try:
            result = await self.bot.orchestrator.run_skill("market_data", "get_candles", timeframe=timeframe, count=100)
            if not result.success:
                return web.json_response({"success": False, "candles": [], "error": result.error})
            
            df = result.data
            if df is None or df.empty:
                return web.json_response({"success": False, "candles": [], "error": "Empty data"})
                
            df = df.sort_index()
            candles = []
            for idx, row in df.iterrows():
                try:
                    candles.append({
                        "time": int(idx.timestamp()),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                    })
                except (ValueError, TypeError, AttributeError) as e:
                    logger.debug(f"API: Skipping malformed candle at {idx}: {e}")
                    continue
            return web.json_response({"success": True, "candles": candles, "count": len(candles)})
        except Exception as e:
            logger.error(f"API: Critical error in _api_candles: {e}")
            return web.json_response({"success": False, "error": str(e), "candles": []})

    async def _api_backtest(self, request):
        """API endpoint for backtesting dashboard data."""
        logger.debug("API: Running backtest...")
        strategy = request.query.get("strategy", None)
        timeframe = request.query.get("timeframe", "H1")
        try:
            ctx = SkillContext()
            result = await self.bot.orchestrator.run_skill("market_data", "get_candles", context=ctx, timeframe=timeframe, count=500)
            if not result.success or result.data is None or result.data.empty:
                return web.json_response({"success": False, "error": "No candle data available"})
                
            df = result.data
            candles = []
            for _, row in df.iterrows():
                try:
                    candles.append({
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0)),
                    })
                except (ValueError, TypeError):
                    continue
            if len(candles) < 60:
                return web.json_response({"success": False, "error": f"Need 60+ candles, have {len(candles)}"})
                
            from ..analytics.backtest_engine import BacktestEngine
            engine = BacktestEngine()
            bt_result = engine.run(candles, strategy_filter=strategy)
            
            return web.json_response({
                "success": True,
                "data": {
                    "strategy": bt_result.strategy,
                    "total_trades": bt_result.total_trades,
                    "wins": bt_result.wins,
                    "losses": bt_result.losses,
                    "win_rate": round(bt_result.win_rate, 1),
                    "total_pnl": round(bt_result.total_pnl, 1),
                    "avg_pnl": round(bt_result.avg_pnl, 1),
                    "max_drawdown": round(bt_result.max_drawdown, 1),
                    "profit_factor": round(bt_result.profit_factor, 2),
                    "sharpe_ratio": round(bt_result.sharpe_ratio, 2),
                    "best_trade": round(bt_result.best_trade, 1),
                    "worst_trade": round(bt_result.worst_trade, 1),
                    "equity_curve": bt_result.equity_curve[-50:],
                    "bars_tested": bt_result.bars_tested,
                }
            })
        except Exception as e:
            logger.error(f"API: Backtest error: {e}")
            return web.json_response({"success": False, "error": str(e)})

    async def _api_performance(self, request):
        """API endpoint for trading performance dashboard."""
        logger.debug("API: Fetching performance data...")
        try:
            # Await async storage method
            stats = await self.bot.storage.get_trade_journal_stats()
            
            # Add RiskManager persisted state
            risk_state = {}
            try:
                risk_skill = self.bot.orchestrator.registry.get("risk_management")
                if risk_skill and hasattr(risk_skill, "manager"):
                    rm = risk_skill.manager
                    risk_state = {
                        "daily_pnl": rm._daily_pnl,
                        "daily_pnl_date": rm._daily_pnl_date,
                        "consecutive_losses": rm._consecutive_losses,
                        "max_daily_loss_limit": rm.config.max_daily_loss
                    }
            except Exception as e:
                logger.warning(f"API: Failed to get risk state: {e}")

            # AdaptiveTuner analyze is async now
            tuning = await self.bot.adaptive_tuner.analyze()
            return web.json_response({
                "success": True, 
                "data": {
                    "stats": stats, 
                    "risk": risk_state,
                    "tuning": tuning
                }
            })
        except Exception as e:
            logger.error(f"API: Performance error: {e}")
            return web.json_response({"success": False, "error": str(e)})

    async def _api_account(self, request):
        """API endpoint for Capital.com account balance and equity."""
        logger.debug("API: Fetching account info...")
        if not hasattr(self.bot, "broker") or not self.bot.broker:
            return web.json_response({"success": False, "error": "Broker not configured"})
        
        try:
            acc_info = await self.bot.broker.get_account_info()
            return web.json_response(acc_info)
        except Exception as e:
            logger.error(f"API: Account info error: {e}")
            return web.json_response({"success": False, "error": str(e)})

    async def _api_briefing(self, request):
        """API endpoint for voice briefing."""
        logger.debug("API: Generating market briefing...")
        try:
            from ..analytics.voice_briefing import VoiceBriefingEngine
            engine = VoiceBriefingEngine(orchestrator=self.bot.orchestrator, storage=self.bot.storage)
            briefing = await engine.generate_briefing()
            return web.json_response({"success": True, "data": engine.format_for_api(briefing)})
        except Exception as e:
            logger.error(f"API: Briefing error: {e}")
            return web.json_response({"success": False, "error": str(e)})

    async def _api_patterns(self, request):
        """API endpoint for detected chart patterns."""
        logger.debug("API: Fetching active patterns...")
        try:
            ctx = SkillContext()
            await self.bot.orchestrator.run_skill("market_data", "get_price", context=ctx)
            result = await self.bot.orchestrator.run_skill("technical_analysis", "detect_patterns", context=ctx, timeframe="H1")
            if not result.success:
                return web.json_response({"success": False, "error": result.error})
            return web.json_response({"success": True, "data": result.data})
        except Exception as e:
            logger.error(f"API: Patterns error: {e}")
            return web.json_response({"success": False, "error": str(e)})

    async def _api_levels(self, request):
        """API endpoint for support/resistance levels."""
        logger.debug("API: Fetching key levels...")
        try:
            ctx = SkillContext()
            await self.bot.orchestrator.run_skill("market_data", "get_price", context=ctx)
            result = await self.bot.orchestrator.run_skill("technical_analysis", "find_levels", context=ctx, timeframe="H1")
            if not result.success:
                return web.json_response({"success": False, "error": result.error})
            return web.json_response({"success": True, "data": result.data})
        except Exception as e:
            logger.error(f"API: Levels error: {e}")
            return web.json_response({"success": False, "error": str(e)})
            
    async def _api_settings(self, request):
        """API endpoint to get user settings/risk parameters."""
        try:
            settings_path = os.path.join(self.config.data_dir, "bot_settings.json")
            data = {
                "risk_per_trade": 1.0,
                "max_daily_loss": 3.0,
                "auto_trading_enabled": False
            }
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    data.update(json.load(f))
            return web.json_response({"success": True, "data": data})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)})

    async def _api_settings_update(self, request):
        """API endpoint to update user settings/risk parameters."""
        try:
            new_data = await request.json()
            settings_path = os.path.join(self.config.data_dir, "bot_settings.json")
            data = {
                "risk_per_trade": 1.0,
                "max_daily_loss": 3.0,
                "auto_trading_enabled": False
            }
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    data.update(json.load(f))
                    
            data.update(new_data)
            self.bot.bot_settings.update(data)
            
            os.makedirs(self.config.data_dir, exist_ok=True)
            with open(settings_path, "w") as f:
                json.dump(data, f)
                
            try:
                risk_skill = self.bot.orchestrator.registry.get("risk_management")
                if risk_skill and hasattr(risk_skill, "manager"):
                    risk_skill.manager.config.risk_per_trade = float(data.get("risk_per_trade", 1.0))
                    risk_skill.manager.config.max_daily_loss = float(data.get("max_daily_loss", 3.0))
            except Exception as e:
                logger.warning(f"API: Failed to hot-reload risk manager config: {e}")

            return web.json_response({"success": True, "data": data})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)})

    async def _api_health(self, request):
        """Standard health check endpoint."""
        return web.Response(text="OK", content_type="text/plain")

    async def _api_emergency(self, request):
        """API endpoint to trigger the Emergency Kill Switch."""
        logger.warning("🚨 EMERGENCY KILL SWITCH TRIGGERED VIA API 🚨")
        try:
            data = await request.json()
            is_active = data.get("active", True)
            
            settings_path = os.path.join(self.config.data_dir, "bot_settings.json")
            s_data = {
                "risk_per_trade": 1.0,
                "max_daily_loss": 3.0,
                "auto_trading_enabled": False,
                "emergency_mode": False
            }
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    s_data.update(json.load(f))
                    
            s_data["emergency_mode"] = is_active
            if is_active:
                s_data["auto_trading_enabled"] = False
                
            self.bot.bot_settings.update(s_data)
            
            os.makedirs(self.config.data_dir, exist_ok=True)
            with open(settings_path, "w") as f:
                json.dump(s_data, f)
                
            status = "ACTIVATED (Trading Halted)" if is_active else "DEACTIVATED"
            logger.info(f"Emergency Mode: {status}")
            
            chat_ids = self.config.proactive_alert_chat_ids
            if chat_ids:
                asyncio.create_task(
                    self.bot.notifications.broadcast_message(
                        f"⚠️ *EMERGENCY KILL SWITCH {status}*\nTriggered via Zenith Dashboard.",
                        chat_ids=chat_ids,
                        parse_mode="Markdown"
                    )
                )

            return web.json_response({"success": True, "emergency_mode": is_active, "message": f"Emergency Mode {status}"})
        except Exception as e:
            logger.error(f"API: Emergency trigger failed: {e}")
            return web.json_response({"success": False, "error": str(e)})

    async def _serve_mini_app(self, request):
        """Serve the Zenith Terminal Mini App directly from the bot server."""
        # Note: adjust path relative to current file vs telegram_bot
        mini_app_path = os.path.join(os.path.dirname(__file__), "mini_app", "index.html")
        if os.path.exists(mini_app_path):
            return web.FileResponse(mini_app_path, headers={"Content-Type": "text/html; charset=utf-8"})
        return web.Response(text="Mini App not found", status=404)

    async def start(self):
        """Run the AIOHTTP server as a background task."""
        try:
            app = web.Application(middlewares=[self._cors_middleware])
            app.add_routes([
                web.get("/", self._serve_mini_app), 
                web.get("/app", self._serve_mini_app), 
                web.get("/healthz", self._api_health), 
                web.get("/api/summary", self._api_summary), 
                web.get("/api/signals", self._api_signals), 
                web.get("/api/scan_signals", self._api_scan_signals), 
                web.get("/api/alerts", self._api_alerts), 
                web.get("/api/analysis", self._api_analysis), 
                web.get("/api/candles", self._api_candles), 
                web.get("/api/status", self._api_status), 
                web.get("/api/forecast", self._api_forecast), 
                web.get("/api/macro", self._api_macro), 
                web.get("/api/backtest", self._api_backtest), 
                web.get("/api/performance", self._api_performance), 
                web.get("/api/account", self._api_account),
                web.get("/api/briefing", self._api_briefing), 
                web.get("/api/trades", self._api_trades), 
                web.get("/api/history", self._api_history),
                web.get("/api/patterns", self._api_patterns),
                web.get("/api/levels", self._api_levels),
                web.get("/api/settings", self._api_settings),
                web.post("/api/settings", self._api_settings_update),
                web.post("/api/emergency", self._api_emergency)
            ])
            port = int(os.getenv("PORT", 8080))
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            logger.info(f"📡 Zenith API + Mini App at: http://0.0.0.0:{port}")
            logger.info(f"📱 Mini App URL: http://0.0.0.0:{port}/app")
            await site.start()
        except Exception as e:
            logger.error(f"❌ API Server CRASH: {e}")
            logger.error(traceback.format_exc())
