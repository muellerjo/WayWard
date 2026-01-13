"""
Routes Package - Alle Blueprints
"""

from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.main import main_bp
from routes.jobs import jobs_bp
from routes.machines import machines_bp

__all__ = [
    'auth_bp',
    'admin_bp', 
    'main_bp',
    'jobs_bp',
    'machines_bp'
]
