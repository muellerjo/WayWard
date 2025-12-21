#!/usr/bin/env python3
"""
Wegewart Abrechnung - Lightweight Web Application
Erfassung von Arbeitsstunden und Maschineneinsätzen
"""

import secrets

from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash

from wayward_db import get_db, close_db, init_db

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Wird bei jedem Start neu generiert - in Produktion aus Config laden!


# Register the teardown handler
app.teardown_appcontext(close_db)


# Import the jobs blueprint
from routes_jobs import jobs_bp
app.register_blueprint(jobs_bp)

from routes_machines import machines_bp
app.register_blueprint(machines_bp)


# ==================== Init DB on first startup ====================
# Initialize database WITH application context
with app.app_context():
    init_db()
            
# ==================== Authentifizierung ====================

def login_required(f):
    """Decorator für geschützte Routen"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bitte zuerst einloggen', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def rolle_required(*allowed_roles):
    """Decorator für rollenbasierte Zugriffskontrolle"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Bitte zuerst einloggen', 'warning')
                return redirect(url_for('login'))
            
            db = get_db()
            user = db.execute('SELECT roles FROM user WHERE id = ?', (session['user_id'],)).fetchone()
            
            # Prüfe ob User mindestens eine der erlaubten Rollen hat
            user_roles = user['roles'].split(',') if user['roles'] else []
            user_roles = [role.strip() for role in user_roles]  # Whitespace entfernen
            
            has_permission = any(role in allowed_roles for role in user_roles)
            
            if not has_permission:
                flash('Keine Berechtigung für diese Aktion', 'danger')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_current_user():
    """Aktuell eingeloggten Benutzer holen"""
    if 'user_id' not in session:
        return None
    db = get_db()
    return db.execute('SELECT * FROM user WHERE id = ?', (session['user_id'],)).fetchone()

@app.template_filter('has_role')
def has_role(user_roles, role):
    """Prüft ob User eine bestimmte Rolle hat"""
    if not user_roles:
        return False
    roles = [r.strip() for r in user_roles.split(',')]
    return role in roles

@app.before_request
def load_logged_in_user():
    """Load logged in user into g before each request"""
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone()


# ==================== Routen ====================

@app.route('/')
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
            ORDER BY a.datum DESC
            LIMIT 10
        ''', (user['id'],)).fetchall()
        
        stats = {
            'gesamt': db.execute('SELECT COUNT(*) as c FROM jobs WHERE user_id = ?', (user['id'],)).fetchone()['c'],
            'erfasst': db.execute('SELECT COUNT(*) as c FROM jobs WHERE user_id = ? AND status = "erfasst"', (user['id'],)).fetchone()['c'],
            'abgelehnt': db.execute('SELECT COUNT(*) as c FROM jobs WHERE user_id = ? AND status = "abgelehnt"', (user['id'],)).fetchone()['c']
        }
        
    elif user_has_role('ortsvorsteher'):
        # Einträge des eigenen Ortsteils
        einsaetze = db.execute('''
            SELECT a.*, u.name, u.vorname
            FROM jobs a
            JOIN user u ON a.user_id = u.id
            WHERE u.ortsteil = ? AND a.status = 'erfasst'
            ORDER BY a.datum DESC
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
            ORDER BY a.datum DESC
        ''').fetchall()
        
        stats = {
            'zur_abrechnung': len(einsaetze),
            'gesamt': db.execute('SELECT COUNT(*) as c FROM jobs').fetchone()['c'],
            'abgerechnet': db.execute('SELECT COUNT(*) as c FROM jobs WHERE status = "abgerechnet"').fetchone()['c']
        }
    
    return render_template('index.html', user=user, einsaetze=einsaetze, stats=stats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login-Seite"""
    if request.method == 'POST':
        username = request.form.get('benutzername')
        passwort = request.form.get('passwort')
        
        db = get_db()
        user = db.execute('SELECT * FROM user WHERE username = ? AND aktiv = 1', 
                         (username,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], passwort):
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['roles'] = user['roles']
            flash(f'Willkommen, {user["vorname"]} {user["name"]}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Ungültige Zugangsdaten', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    flash('Erfolgreich abgemeldet', 'info')
    return redirect(url_for('login'))


# ==================== Benutzerverwaltung ====================

@app.route('/admin/user')
@rolle_required('admin', 'verwaltung', 'ortsvorsteher')
def admin_user():
    """Benutzerverwaltung"""
    db = get_db()
    benutzer = db.execute('SELECT * FROM user ORDER BY ortsteil, name').fetchall()
    return render_template('admin_user.html', user=get_current_user(), benutzer=benutzer)

@app.route('/admin/user/new', methods=['GET', 'POST'])
@rolle_required('admin', 'verwaltung')
def admin_user_new():
    """Neuen Benutzer anlegen"""
    if request.method == 'POST':
        benutzername = request.form.get('benutzername', '').strip().lower()
        passwort = request.form.get('passwort')
        vorname = request.form.get('vorname', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        ortsteil = request.form.get('ortsteil')
        rolle = request.form.get('rolle')
        aktiv = 1 if request.form.get('aktiv') == 'on' else 0
        
        # Validierung
        if not all([benutzername, passwort, vorname, name, ortsteil, rolle]):
            flash('Bitte alle Pflichtfelder ausfüllen', 'danger')
            return render_template('admin_user_new.html', user=get_current_user())
        
        if len(passwort) < 6:
            flash('Passwort muss mindestens 6 Zeichen lang sein', 'danger')
            return render_template('admin_user_new.html', user=get_current_user())
        
        # Benutzername-Format prüfen
        import re
        if not re.match(r'^[a-z0-9._]+$', benutzername):
            flash('Benutzername darf nur Kleinbuchstaben, Zahlen, Punkt und Unterstrich enthalten', 'danger')
            return render_template('admin_user_new.html', user=get_current_user())
        
        db = get_db()
        
        # Prüfen ob Benutzername schon existiert
        existing = db.execute('SELECT id FROM user WHERE username = ?', (benutzername,)).fetchone()
        if existing:
            flash(f'Benutzername "{benutzername}" existiert bereits', 'danger')
            return render_template('admin_user_new.html', user=get_current_user())
        
        # Benutzer anlegen
        passwort_hash = generate_password_hash(passwort)
        current_user = get_current_user()
        
        try:
            db.execute('''
                INSERT INTO user (username, password_hash, name, vorname, ortsteil, roles, email, aktiv, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (benutzername, passwort_hash, name, vorname, ortsteil, rolle, email, aktiv, current_user['id']))
            db.commit()
            flash(f'Benutzer "{benutzername}" erfolgreich angelegt', 'success')
            return redirect(url_for('admin_user'))
        except Exception as e:
            flash(f'Fehler beim Anlegen des Benutzers: {e}', 'danger')
    
    return render_template('admin_user_new.html', user=get_current_user())

@app.route('/admin/user/<int:benutzer_id>/modify', methods=['GET', 'POST'])
@rolle_required('admin', 'verwaltung')
def admin_user_modify(benutzer_id):
    """Benutzer bearbeiten"""
    db = get_db()
    benutzer_edit = db.execute('SELECT * FROM user WHERE id = ?', (benutzer_id,)).fetchone()
    
    if not benutzer_edit:
        flash('Benutzer nicht gefunden', 'danger')
        return redirect(url_for('admin_user'))
    
    if request.method == 'POST':
        vorname = request.form.get('vorname', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        ortsteil = request.form.get('ortsteil')
        
        # Get ALL selected roles as a list and join them with commas
        selected_roles = request.form.getlist('rolle')  # Changed from get to getlist
        rolle = ','.join(selected_roles)  # Join multiple roles with comma
        
        aktiv = 1 if request.form.get('aktiv') == 'on' else 0
        neues_passwort = request.form.get('neues_passwort', '').strip()
        neues_passwort_confirm = request.form.get('neues_passwort_confirm', '').strip()
        
        # Validierung - check that at least one role is selected
        if not all([vorname, name, ortsteil]) or not selected_roles:
            flash('Bitte alle Pflichtfelder ausfüllen und mindestens eine Rolle auswählen', 'danger')
            return render_template('admin_user_modify.html', user=get_current_user(), benutzer_edit=benutzer_edit)
        
        # Passwort ändern (falls angegeben)
        if neues_passwort:
            if len(neues_passwort) < 6:
                flash('Passwort muss mindestens 6 Zeichen lang sein', 'danger')
                return render_template('admin_user_modify.html', user=get_current_user(), benutzer_edit=benutzer_edit)
            
            if neues_passwort != neues_passwort_confirm:
                flash('Passwörter stimmen nicht überein', 'danger')
                return render_template('admin_user_modify.html', user=get_current_user(), benutzer_edit=benutzer_edit)
            
            passwort_hash = generate_password_hash(neues_passwort)
            db.execute('''
                UPDATE user 
                SET name = ?, vorname = ?, email = ?, ortsteil = ?, roles = ?, aktiv = ?, password_hash = ?
                WHERE id = ?
            ''', (name, vorname, email, ortsteil, rolle, aktiv, passwort_hash, benutzer_id))
        else:
            db.execute('''
                UPDATE user 
                SET name = ?, vorname = ?, email = ?, ortsteil = ?, roles = ?, aktiv = ?
                WHERE id = ?
            ''', (name, vorname, email, ortsteil, rolle, aktiv, benutzer_id))
        
        db.commit()
        flash('Benutzer erfolgreich aktualisiert', 'success')
        return redirect(url_for('admin_user'))
    
    return render_template('admin_user_modify.html', user=get_current_user(), benutzer_edit=benutzer_edit)

@app.route('/admin/benutzer/<int:benutzer_id>/deaktivieren', methods=['POST'])
@rolle_required('admin', 'verwaltung')
def admin_benutzer_deaktivieren(benutzer_id):
    """Benutzer deaktivieren"""
    db = get_db()
    db.execute('UPDATE user SET aktiv = 0 WHERE id = ?', (benutzer_id,))
    db.commit()
    flash('Benutzer deaktiviert', 'warning')
    return redirect(url_for('admin_user'))

@app.route('/admin/benutzer/<int:benutzer_id>/aktivieren', methods=['POST'])
@rolle_required('admin', 'verwaltung')
def admin_benutzer_aktivieren(benutzer_id):
    """Benutzer aktivieren"""
    db = get_db()
    db.execute('UPDATE user SET aktiv = 1 WHERE id = ?', (benutzer_id,))
    db.commit()
    flash('Benutzer aktiviert', 'success')
    return redirect(url_for('admin_user'))


@app.route('/profil/passwort', methods=['GET', 'POST'])
@login_required
def passwort_aendern():
    """Passwort ändern"""
    user = get_current_user()
    
    if request.method == 'POST':
        altes_pw = request.form.get('altes_passwort')
        neues_pw = request.form.get('neues_passwort')
        neues_pw_confirm = request.form.get('neues_passwort_confirm')
        
        if not check_password_hash(user['password_hash'], altes_pw):
            flash('Altes Passwort falsch', 'danger')
        elif neues_pw != neues_pw_confirm:
            flash('Neue Passwörter stimmen nicht überein', 'danger')
        elif len(neues_pw) < 6:
            flash('Passwort muss mindestens 6 Zeichen lang sein', 'danger')
        else:
            db = get_db()
            db.execute('UPDATE user SET password_hash = ? WHERE id = ?',
                      (generate_password_hash(neues_pw), user['id']))
            db.commit()
            flash('Passwort erfolgreich geändert', 'success')
            return redirect(url_for('index'))
    
    return render_template('passwort_aendern.html', user=user)

# ==================== Hilfsfunktionen ====================

@app.template_filter('status_badge')
def status_badge(status):
    """Status als farbiges Badge formatieren"""
    badges = {
        'erfasst': 'warning',
        'freigegeben_ov': 'info',
        'abgerechnet': 'success',
        'abgelehnt': 'danger'
    }
    return badges.get(status, 'secondary')

@app.template_filter('status_text')
def status_text(status):
    """Status als Text formatieren"""
    texts = {
        'erfasst': 'Erfasst',
        'freigegeben_ov': 'Freigegeben (OV)',
        'abgerechnet': 'Abgerechnet',
        'abgelehnt': 'Abgelehnt'
    }
    return texts.get(status, status)

#role badges, as used in the users list, showing multiple badges for multiple roles
@app.template_filter('role_badge')
def role_badge(role_code):
    """Formatiert eine Rolle als farbiges Badge mit Namen aus der Datenbank"""
    role_code = role_code.strip()  # Remove whitespace
    
    # Badge-Farben für verschiedene Rollen
    badge_classes = {
        'admin': 'bg-danger',
        'verwaltung': 'bg-primary',
        'ortsvorsteher': 'bg-info',
        'wegewart': 'bg-success'
    }
    
    # Try to get role name from database
    db = get_db()
    role = db.execute(
        "SELECT role_name FROM roles WHERE role_code = ?", 
        (role_code,)
    ).fetchone()
    
    role_name = role['role_name'] if role else role_code.title()
    badge_class = badge_classes.get(role_code, 'bg-secondary')
    
    return f'<span class="badge {badge_class}">{role_name}</span>'

# ==================== Start ====================

if __name__ == '__main__':
    with app.app_context():
        init_db()
    
    print("\n" + "="*50)
    print("Wegewart-Abrechnungssystem gestartet")
    print("="*50)
    print("\nÖffne im Browser: http://localhost:5000")
    print("Standard-Login: admin / admin123")
    print("\nZum Beenden: Ctrl+C\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)