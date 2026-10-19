# Routes initialization
from .auth_routes import auth_bp
from .item_routes import item_bp
from .claim_routes import claim_bp
from .dashboard_routes import dashboard_bp
from .admin_routes import admin_bp

__all__ = ["auth_bp", "item_bp", "claim_bp", "dashboard_bp", "admin_bp"]
