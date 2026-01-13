#!/usr/bin/env python3
"""
Wegewart Abrechnung - Lightweight Web Application
Erfassung von Arbeitsstunden und Maschineneinsätzen
"""

import secrets
from flask import Flask

from wayward_db import close_db, init_db
from utils.decorators import load_logged_in_user
from utils.filters import register_filters


def create_app():
    """Application Factory"""
    app = Flask(__name__)
    
    # Konfiguration
    app.secret_key = secrets.token_hex(32)  # In Produktion aus Config/Env laden!
    app.config['SESSION_PERMANENT'] = True
    
    # Database teardown
    app.teardown_appcontext(close_db)
    
    # Before request - User laden
    app.before_request(load_logged_in_user)
    
    # Template-Filter registrieren
    register_filters(app)
    
    # Blueprints registrieren
    from routes import auth_bp, admin_bp, main_bp, jobs_bp, machines_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(machines_bp)
    
    return app


# App erstellen
app = create_app()


if __name__ == '__main__':
    with app.app_context():
        init_db()
    
    print("\n" + "=" * 50)
    print("Wegewart-Abrechnungssystem gestartet")
    print("=" * 50)
    print("\nÖffne im Browser: http://localhost:5000")
    print("Standard-Login: admin / admin123")
    print("\nZum Beenden: Ctrl+C\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
