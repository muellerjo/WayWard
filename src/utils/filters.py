"""
Template-Filter für Jinja2
"""

from wayward_db import get_db


def has_role(user_roles, role):
    """Prüft ob User eine bestimmte Rolle hat"""
    if not user_roles:
        return False
    roles = [r.strip() for r in user_roles.split(',')]
    return role in roles


def status_badge(status):
    """Status als Bootstrap Badge-Klasse"""
    badges = {
        'erfasst': 'warning',
        'freigegeben_ov': 'info',
        'freigegeben': 'success',
        'abgerechnet': 'success',
        'abgelehnt': 'danger'
    }
    return badges.get(status, 'secondary')


def status_text(status):
    """Status als lesbarer Text"""
    texts = {
        'erfasst': 'Erfasst',
        'freigegeben_ov': 'Freigegeben (OV)',
        'freigegeben': 'Freigegeben',
        'abgerechnet': 'Abgerechnet',
        'abgelehnt': 'Abgelehnt'
    }
    return texts.get(status, status)


def role_badge(role_code):
    """Formatiert eine Rolle als farbiges Badge mit Namen aus der Datenbank"""
    role_code = role_code.strip()
    
    badge_classes = {
        'admin': 'bg-danger',
        'verwaltung': 'bg-primary',
        'ortsvorsteher': 'bg-info',
        'wegewart': 'bg-success'
    }
    
    # Role-Name aus Datenbank holen
    db = get_db()
    role = db.execute(
        "SELECT role_name FROM roles WHERE role_code = ?", 
        (role_code,)
    ).fetchone()
    
    role_name = role['role_name'] if role else role_code.title()
    badge_class = badge_classes.get(role_code, 'bg-secondary')
    
    return f'<span class="badge {badge_class}">{role_name}</span>'


def register_filters(app):
    """Registriert alle Template-Filter bei der Flask-App"""
    app.template_filter('has_role')(has_role)
    app.template_filter('status_badge')(status_badge)
    app.template_filter('status_text')(status_text)
    app.template_filter('role_badge')(role_badge)
