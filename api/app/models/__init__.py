"""Import all models so Alembic and SQLAlchemy can discover them."""

from app.models.user import User, Subscription  # noqa: F401
from app.models.watchlist import WatchlistItem  # noqa: F401
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
