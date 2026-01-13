"""
Decorators für Authentifizierung und Autorisierung
"""

from functools import wraps
from flask import session, redirect, url_for, flash, g

from wayward_db import get_db


def login_required(f):
    """Decorator für geschützte Routen"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bitte zuerst einloggen', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def rolle_required(*allowed_roles):
    """Decorator für rollenbasierte Zugriffskontrolle"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Bitte zuerst einloggen', 'warning')
                return redirect(url_for('auth.login'))
            
            db = get_db()
            user = db.execute(
                'SELECT roles FROM user WHERE id = ?', 
                (session['user_id'],)
            ).fetchone()
            
            # Prüfe ob User mindestens eine der erlaubten Rollen hat
            user_roles = user['roles'].split(',') if user['roles'] else []
            user_roles = [role.strip() for role in user_roles]
            
            has_permission = any(role in allowed_roles for role in user_roles)
            
            if not has_permission:
                flash('Keine Berechtigung für diese Aktion', 'danger')
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_current_user():
    """Aktuell eingeloggten Benutzer holen"""
    if 'user_id' not in session:
        return None
    db = get_db()
    return db.execute(
        'SELECT * FROM user WHERE id = ?', 
        (session['user_id'],)
    ).fetchone()


def load_logged_in_user():
    """Load logged in user into g before each request"""
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute(
            'SELECT * FROM user WHERE id = ?', 
            (user_id,)
        ).fetchone()
