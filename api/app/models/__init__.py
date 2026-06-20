"""Import all models so Alembic and SQLAlchemy can discover them."""

from app.models.user import User, Subscription  # noqa: F401
from app.models.watchlist import WatchlistGroup, WatchlistItem  # noqa: F401
from app.models.alert import Alert, ActiveEntry, Cooldown  # noqa: F401
from app.models.trade import (  # noqa: F401
    Trade1099,
    TradeMonthly,
    MatchedTrade,
    AccountSummary,
    TradeAnnotation,
)
from app.models.paper_trade import PaperTrade, RealTrade  # noqa: F401
from app.models.chart import ChartLevel, MonitorStatus  # noqa: F401
from app.models.import_record import ImportRecord  # noqa: F401
from app.models.device_token import DeviceToken  # noqa: F401
from app.models.alert_prefs import UserAlertCategoryPref  # noqa: F401
from app.models.usage import UsageLimit  # noqa: F401
from app.models.telegram_link import TelegramLinkToken  # noqa: F401
from app.models.referral import Referral  # noqa: F401
from app.models.password_reset import PasswordResetToken  # noqa: F401
from app.models.chart_analysis import ChartAnalysis  # noqa: F401
from app.models.auto_trade import AIAutoTrade  # noqa: F401
from app.models.focus_list import FocusList  # noqa: F401
from app.models.alert_type_config import AlertTypeConfig  # noqa: F401
from app.models.alert_type_pref import UserAlertTypePref  # noqa: F401
from app.models.earnings import Earnings, EarningsHistory, EarningsNotificationSent  # noqa: F401
from app.models.fundamentals import SymbolFundamentals  # noqa: F401
from app.models.strategy_analysis import StrategyAnalysisCache  # noqa: F401
from app.models.strategy_week_ai import StrategyWeekAICache  # noqa: F401
from app.models.social_buzz import SocialBuzzSnapshot  # noqa: F401
from app.models.premarket_gap import PremarketGapSnapshot  # noqa: F401
from app.models.site_visit import SiteVisit  # noqa: F401
