"""
Main Blueprint - Dashboard und Startseite
"""

from flask import Blueprint, render_template

from wayward_db import get_db
from utils.decorators import login_required, get_current_user
from utils.filters import has_role

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    """Dashboard / Startseite"""
    user = get_current_user()
    db = get_db()
    
    # Hilfsfunktion zum Rollen-Check
    def user_has_role(role):
        return has_role(user['roles'], role)
    
    # Statistiken je nach Rolle
    if user_has_role('wegewart'):
        # Eigene Einträge
        einsaetze = db.execute('''
            SELECT a.*, u.name, u.vorname
            FROM jobs a
            JOIN user u ON a.user_id = u.id
            WHERE a.user_id = ?
            ORDER BY a.date DESC
            LIMIT 10
        ''', (user['id'],)).fetchall()
        
        stats = {
            'gesamt': db.execute(
                'SELECT COUNT(*) as c FROM jobs WHERE user_id = ?', 
                (user['id'],)
            ).fetchone()['c'],
            'erfasst': db.execute(
                'SELECT COUNT(*) as c FROM jobs WHERE user_id = ? AND status = "erfasst"', 
                (user['id'],)
            ).fetchone()['c'],
            'abgelehnt': db.execute(
                'SELECT COUNT(*) as c FROM jobs WHERE user_id = ? AND status = "abgelehnt"', 
                (user['id'],)
            ).fetchone()['c']
        }
        
    elif user_has_role('ortsvorsteher'):
        # Einträge des eigenen Ortsteils
        einsaetze = db.execute('''
            SELECT a.*, u.name, u.vorname
            FROM jobs a
            JOIN user u ON a.user_id = u.id
            WHERE u.ortsteil = ? AND a.status = 'erfasst'
            ORDER BY a.date DESC
        ''', (user['ortsteil'],)).fetchall()
        
        stats = {
            'zu_pruefen': len(einsaetze),
            'freigegeben': db.execute('''
                SELECT COUNT(*) as c FROM jobs a
                JOIN user u ON a.user_id = u.id
                WHERE u.ortsteil = ? AND a.status = 'freigegeben_ov'
            ''', (user['ortsteil'],)).fetchone()['c']
        }
        
    else:  # admin / verwaltung
        # Alle Einträge zur Abrechnung
        einsaetze = db.execute('''
            SELECT a.*, u.name, u.vorname, u.ortsteil
            FROM jobs a
            JOIN user u ON a.user_id = u.id
            WHERE a.status = 'freigegeben_ov'
            ORDER BY a.date DESC
        ''').fetchall()
        
        stats = {
            'zur_abrechnung': len(einsaetze),
            'gesamt': db.execute('SELECT COUNT(*) as c FROM jobs').fetchone()['c'],
            'abgerechnet': db.execute(
                'SELECT COUNT(*) as c FROM jobs WHERE status = "abgerechnet"'
            ).fetchone()['c']
        }
    
    return render_template('index.html', user=user, einsaetze=einsaetze, stats=stats)
