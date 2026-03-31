
from .auth import bp as auth_bp
from .dashboard import bp as dashboard_bp
from .anomaly import bp as anomaly_bp
from .video import bp as video_bp
from .subscription import bp as subscription_bp
from .support import bp as support_bp
from .analytics import bp as analytics_bp
from .api import bp as api_bp

# Export all blueprints
__all__ = [
    'auth_bp',
    'dashboard_bp',
    'anomaly_bp',
    'video_bp',
    'subscription_bp',
    'support_bp',
    'analytics_bp',
    'api_bp'
]