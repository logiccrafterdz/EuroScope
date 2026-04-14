import logging
from typing import Optional

from .config import Config
from .brain.llm_interface import LLMInterface
from .brain.memory import Memory
from .brain.orchestrator import Orchestrator
from .brain.llm_router import LLMRouter
from .brain.vector_memory import VectorMemory
from .learning.pattern_tracker import PatternTracker
from .learning.adaptive_tuner import AdaptiveTuner
from .data.multi_provider import MultiSourceProvider
from .data.news import NewsEngine
from .data.calendar import EconomicCalendar
from .data.fundamental import FundamentalDataProvider
from .data.storage import Storage
from .forecast.engine import Forecaster
from .trading.risk_manager import RiskManager
from .trading.capital_provider import CapitalProvider
from .trading.capital_ws import CapitalWebsocketClient
from .bot.rate_limiter import RateLimiter
from .bot.user_settings import UserSettings
from .bot.notification_manager import NotificationManager
from .brain.briefing_engine import BriefingEngine
from .analytics.evolution_tracker import EvolutionTracker
from .skills.registry import SkillsRegistry
from .workspace import WorkspaceManager
from .automation import EventBus, SmartAlerts, setup_default_alerts
from .automation.daily_tracker import DailyTracker

logger = logging.getLogger('euroscope.container')

_global_container = None

def get_container():
    global _global_container
    return _global_container

def set_container(container):
    global _global_container
    _global_container = container

class ServiceContainer:
    """Dependency injection container for EuroScope.
    
    Instantiates and holds all core services in topological order to
    solve circular dependencies and reduce code duplication.
    """
    
    def __init__(self, config: Config):
        self.config = config
        
        # 1. Base Infrastructure
        self.storage = Storage()
        self.bus = EventBus()
        self.registry = SkillsRegistry()
        self.alerts = SmartAlerts()
        setup_default_alerts(self.alerts)
        self.rate_limiter = RateLimiter(
            max_requests=config.rate_limit_requests,
            window_minutes=config.rate_limit_window_minutes
        )
        
        # 2. Core Brain Components
        self.memory = Memory(self.storage)
        self.vector_memory = VectorMemory(storage=self.storage)
        self.orchestrator = Orchestrator(storage=self.storage, registry=self.registry)
        
        self.router = LLMRouter.from_config(
            primary_key=config.llm.api_key, 
            primary_base=config.llm.api_base, 
            primary_model=config.llm.model, 
            fallback_key=config.llm.fallback_api_key, 
            fallback_base=config.llm.fallback_api_base, 
            fallback_model=config.llm.fallback_model
        )
        
        # 3. Intelligence Layers
        self.agent = LLMInterface(
            config.llm, 
            router=self.router, 
            vector_memory=self.vector_memory, 
            orchestrator=self.orchestrator
        )
        self.forecaster = Forecaster(
            self.agent, 
            self.memory, 
            self.orchestrator, 
            pattern_tracker=None # Set later to avoid circular dependency
        )
        self.agent.forecaster = self.forecaster
        
        # 4. Domain & Data Services
        self.price_provider = MultiSourceProvider(
            alphavantage_key=config.data.alphavantage_key,
            tiingo_key=config.data.tiingo_key,
            oanda_key=config.data.oanda_api_key,
            oanda_account=config.data.oanda_account_id,
            oanda_practice=config.data.oanda_practice,
            capital_key=config.data.capital_api_key,
            capital_identifier=config.data.capital_identifier,
            capital_password=config.data.capital_password
        )
        self.broker = CapitalProvider(
            api_key=config.data.capital_api_key,
            identifier=config.data.capital_identifier,
            password=config.data.capital_password
        ) if config.data.capital_api_key else None
        self.ws_client = CapitalWebsocketClient(self.broker) if self.broker else None
        
        self.news_engine = NewsEngine(config.data.brave_api_key, storage=self.storage)
        self.calendar = EconomicCalendar()
        self.macro_provider = FundamentalDataProvider(config.data.fred_api_key)
        self.risk_manager = RiskManager(storage=self.storage)
        
        # 5. Tracking & Analytics
        self.pattern_tracker = PatternTracker(storage=self.storage)
        self.adaptive_tuner = AdaptiveTuner(storage=self.storage, config=self.config)
        self.evolution_tracker = EvolutionTracker(storage=self.storage)
        self.daily_tracker = DailyTracker(storage=self.storage)
        self.briefing_engine = BriefingEngine(self.config, storage=self.storage, orchestrator=self.orchestrator)
        self.briefing_engine.agent = self.agent
        
        # Inject pattern tracker into forecaster now that it exists
        self.forecaster.pattern_tracker = self.pattern_tracker
        
        # 6. User Management & Notifications
        self.user_settings = UserSettings(self.storage)
        self.notifications = NotificationManager(self.storage)
        self.notifications.set_orchestrator(self.orchestrator)
        
        self.workspace = WorkspaceManager()
