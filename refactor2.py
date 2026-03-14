import re

filepath = r"c:\Users\Hp\Desktop\EuroScope\euroscope\bot\telegram_bot.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Add ServiceContainer import
if "from ..container import ServiceContainer" not in content:
    content = content.replace(
        "from ..config import Config",
        "from ..config import Config\nfrom ..container import ServiceContainer"
    )

new_init = """    def __init__(self, container: ServiceContainer):
        self.container = container
        self.config = container.config
        
        # 1. Base Infrastructure (Shared Storage)
        self.storage = container.storage
        self.bus = container.bus
        self.registry = container.registry
        self.alerts = container.alerts
        self.rate_limiter = container.rate_limiter
        
        # 2. Core Brain Components
        self.memory = container.memory
        self.vector_memory = container.vector_memory
        self.orchestrator = container.orchestrator
        self.router = container.router
        
        # 3. Intelligence Layers
        self.agent = container.agent
        self.forecaster = container.forecaster
        
        # 4. Domain & Data Services
        self.price_provider = container.price_provider
        self.broker = container.broker
        self.ws_client = container.ws_client
        self.news_engine = container.news_engine
        self.calendar = container.calendar
        self.macro_provider = container.macro_provider
        self.risk_manager = container.risk_manager
        
        # 5. Tracking & Analytics
        self.pattern_tracker = container.pattern_tracker
        self.adaptive_tuner = container.adaptive_tuner
        self.evolution_tracker = container.evolution_tracker
        self.daily_tracker = container.daily_tracker
        self.briefing_engine = container.briefing_engine
        
        # 6. User Management & Notifications
        self.user_settings = container.user_settings
        self.notifications = container.notifications
        self.workspace = container.workspace
        
        # 7. UI, Interface & Scheduling
        self.api = APIServer(self)
        self.commands = CommandHandlers(self)
        self.tasks = BotTasks(self)
        self.heartbeat = HeartbeatService(interval=300, event_bus=self.bus)
        self.cron = CronScheduler(config=self.config, bot=self, storage=self.storage)
        
        # 8. Subscription Handlers
        self.alerts.register_handler(AlertChannel.TELEGRAM, self._on_alert_triggered)"""

old_init_regex = re.compile(r"    def __init__\(self, config: Config\):.*?self\.alerts\.register_handler\(AlertChannel\.TELEGRAM, self\._on_alert_triggered\)", re.DOTALL)
content = old_init_regex.sub(new_init, content)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

# Refactor main.py
main_fp = r"c:\Users\Hp\Desktop\EuroScope\euroscope\main.py"
with open(main_fp, "r", encoding="utf-8") as f:
    main_content = f.read()

if "ServiceContainer" not in main_content:
    main_content = main_content.replace(
        "from .bot.telegram_bot import EuroScopeBot",
        "from .bot.telegram_bot import EuroScopeBot\nfrom .container import ServiceContainer"
    )
    main_content = main_content.replace(
        "bot = EuroScopeBot(config)",
        "container = ServiceContainer(config)\n    bot = EuroScopeBot(container)"
    )

with open(main_fp, "w", encoding="utf-8") as f:
    f.write(main_content)

print("Refactored telegram_bot.py and main.py")
