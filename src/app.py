#!/usr/bin/env python3
"""
Wegewart Abrechnung - Lightweight Web Application
Erfassung von Arbeitsstunden und Maschineneinsätzen
"""

import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Wird bei jedem Start neu generiert - in Produktion aus Config laden!
app.config['DATABASE'] = 'wegewart.db'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# ==================== Datenbank ====================

def get_db():
    """Datenbankverbindung herstellen"""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Datenbankverbindung schließen"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Datenbank initialisieren"""
    db = get_db()
    
    # Tabelle: Benutzer
    db.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            vorname TEXT NOT NULL,
            ortsteil TEXT NOT NULL,
            roles TEXT NOT NULL,
            email TEXT,
            aktiv INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER NOT NULL,
            FOREIGN KEY (created_by) REFERENCES user (id)
        )
    ''')
    
    # Tabelle: Maschinen (vereinfacht - nur Name)
    db.execute('''
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bezeichnung TEXT NOT NULL,
            aktiv INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabelle: Arbeitseinsätze
    db.execute('''
        CREATE TABLE IF NOT EXISTS arbeitseinsaetze (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            datum DATE NOT NULL,
            arbeitsstunden REAL NOT NULL,
            taetigkeitsbeschreibung TEXT NOT NULL,
            machine_used INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'erfasst',
            rejection_reason TEXT,
            checked_time TIMESTAMP,
            checked_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user (id),
            FOREIGN KEY (checked_by) REFERENCES user (id),
            FOREIGN KEY (machine_used) REFERENCES machines (id)
        )
    ''')
    
    db.commit()
    
    # Standard-Admin anlegen falls nicht vorhanden
    cursor = db.execute("""
                        SELECT COUNT(*) as count FROM user WHERE roles LIKE '%admin%'
                        """)
    if cursor.fetchone()['count'] == 0:
        admin_hash = generate_password_hash('admin123')
        db.execute('''
            INSERT INTO user (username, password_hash, name, vorname, ortsteil, roles, email, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('admin', admin_hash, 'Administrator', 'System', 'Verwaltung', 'admin', 'admin@gemeinde.de', 0))
        db.commit()
        print("Standard-Admin erstellt: admin / admin123 (BITTE PASSWORT ÄNDERN!)")

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
            FROM arbeitseinsaetze a
            JOIN user u ON a.user_id = u.id
            WHERE a.user_id = ?
            ORDER BY a.datum DESC
            LIMIT 10
        ''', (user['id'],)).fetchall()
        
        stats = {
            'gesamt': db.execute('SELECT COUNT(*) as c FROM arbeitseinsaetze WHERE user_id = ?', (user['id'],)).fetchone()['c'],
            'erfasst': db.execute('SELECT COUNT(*) as c FROM arbeitseinsaetze WHERE user_id = ? AND status = "erfasst"', (user['id'],)).fetchone()['c'],
            'abgelehnt': db.execute('SELECT COUNT(*) as c FROM arbeitseinsaetze WHERE user_id = ? AND status = "abgelehnt"', (user['id'],)).fetchone()['c']
        }
        
    elif user_has_role('ortsvorsteher'):
        # Einträge des eigenen Ortsteils
        einsaetze = db.execute('''
            SELECT a.*, u.name, u.vorname
            FROM arbeitseinsaetze a
            JOIN user u ON a.user_id = u.id
            WHERE u.ortsteil = ? AND a.status = 'erfasst'
            ORDER BY a.datum DESC
        ''', (user['ortsteil'],)).fetchall()
        
        stats = {
            'zu_pruefen': len(einsaetze),
            'freigegeben': db.execute('''
                SELECT COUNT(*) as c FROM arbeitseinsaetze a
                JOIN user u ON a.user_id = u.id
                WHERE u.ortsteil = ? AND a.status = 'freigegeben_ov'
            ''', (user['ortsteil'],)).fetchone()['c']
        }
        
    else:  # admin / verwaltung
        # Alle Einträge zur Abrechnung
        einsaetze = db.execute('''
            SELECT a.*, u.name, u.vorname, u.ortsteil
            FROM arbeitseinsaetze a
            JOIN user u ON a.user_id = u.id
            WHERE a.status = 'freigegeben_ov'
            ORDER BY a.datum DESC
        ''').fetchall()
        
        stats = {
            'zur_abrechnung': len(einsaetze),
            'gesamt': db.execute('SELECT COUNT(*) as c FROM arbeitseinsaetze').fetchone()['c'],
            'abgerechnet': db.execute('SELECT COUNT(*) as c FROM arbeitseinsaetze WHERE status = "abgerechnet"').fetchone()['c']
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

@app.route('/einsaetze')
@login_required
def einsaetze_liste():
    """Liste aller Arbeitseinsätze (gefiltert nach Rolle)"""
    user = get_current_user()
    db = get_db()
    
    # Hilfsfunktion zum Rollen-Check
    def user_has_role(role):
        return has_role(user['roles'], role)
    
    # Filter-Parameter
    von_filter = request.args.get('von', '')
    bis_filter = request.args.get('bis', '')
    status_filter = request.args.get('status', '')
    wegewart_filter = request.args.get('wegewart', '')
    
    query = '''
        SELECT a.*, u.name, u.vorname, u.ortsteil
        FROM arbeitseinsaetze a
        JOIN user u ON a.user_id = u.id
        WHERE 1=1
    '''
    params = []
    
    # Rollenbasierte Filter
    if user_has_role('wegewart'):
        query += ' AND a.user_id = ?'
        params.append(user['id'])
    elif user_has_role('ortsvorsteher'):
        query += ' AND u.ortsteil = ?'
        params.append(user['ortsteil'])
    
    # Datumsfilter
    if von_filter:
        query += ' AND a.datum >= ?'
        params.append(von_filter)
    
    if bis_filter:
        query += ' AND a.datum <= ?'
        params.append(bis_filter)
    
    # Wegewart-Filter
    if wegewart_filter:
        query += ' AND a.user_id = ?'
        params.append(wegewart_filter)
    
    # Status-Filter
    if status_filter:
        query += ' AND a.status = ?'
        params.append(status_filter)
    
    query += ' ORDER BY a.datum DESC'
    
    einsaetze = db.execute(query, params).fetchall()
    
    # Wegewarte laden (für Filter-Dropdown)
    wegewarte = []
    if user_has_role('ortsvorsteher') or user_has_role('admin') or user_has_role('verwaltung'):
        if user_has_role('ortsvorsteher'):
            wegewarte = db.execute('''
                SELECT id, name, vorname FROM user 
                WHERE roles LIKE '%wegewart%' AND ortsteil = ? AND aktiv = 1
                ORDER BY name
            ''', (user['ortsteil'],)).fetchall()
        else:
            wegewarte = db.execute('''
                SELECT id, name, vorname FROM user 
                WHERE roles LIKE '%wegewart%' AND aktiv = 1
                ORDER BY name
            ''').fetchall()
    
    return render_template('einsaetze_liste.html', user=user, einsaetze=einsaetze,
                         von_filter=von_filter, bis_filter=bis_filter,
                         status_filter=status_filter, wegewart_filter=wegewart_filter,
                         wegewarte=wegewarte)

@app.route('/einsatz/neu', methods=['GET', 'POST'])
@login_required
def einsatz_neu():
    """Neue Arbeitseinsätze erfassen (mehrere gleichzeitig möglich)"""
    user = get_current_user()
    db = get_db()
    
    if request.method == 'POST':
        # Arrays von Formulardaten holen
        datums = request.form.getlist('datum[]')
        arbeitszeiten = request.form.getlist('arbeitszeit[]')
        bemerkungen = request.form.getlist('bemerkungen[]')
        
        erfolgreich = 0
        fehler = 0
        
        # Jede Zeile durchgehen
        for i in range(len(datums)):
            try:
                datum = datums[i]
                arbeitszeit = arbeitszeiten[i]
                bemerkung = bemerkungen[i]
                
                # Validierung
                if not datum or not arbeitszeit or not bemerkung:
                    fehler += 1
                    continue
                
                # Arbeitseinsatz speichern
                db.execute('''
                    INSERT INTO arbeitseinsaetze (user_id, datum, arbeitsstunden, taetigkeitsbeschreibung)
                    VALUES (?, ?, ?, ?)
                ''', (user['id'], datum, float(arbeitszeit), bemerkung))

                erfolgreich += 1
                
            except Exception as e:
                print(f"Fehler bei Zeile {i+1}: {e}")
                fehler += 1
                continue
        
        db.commit()
        
        # Erfolgsmeldung
        if erfolgreich > 0:
            if erfolgreich == 1:
                flash(f'1 Arbeitseinsatz erfolgreich erfasst', 'success')
            else:
                flash(f'{erfolgreich} Arbeitseinsätze erfolgreich erfasst', 'success')
        
        if fehler > 0:
            flash(f'{fehler} Einträge konnten nicht gespeichert werden (fehlende Pflichtfelder)', 'warning')
        
        return redirect(url_for('index'))
    
    # Maschinen für Formular laden
    maschinen = db.execute('SELECT * FROM machines WHERE aktiv = 1 ORDER BY bezeichnung').fetchall()
    
    return render_template('einsatz_neu.html', user=user, maschinen=maschinen)


@app.route('/einsatz/<int:einsatz_id>')
@login_required
def einsatz_detail(einsatz_id):
    """Details eines Arbeitseinsatzes"""
    user = get_current_user()
    db = get_db()
    
    # Hilfsfunktion zum Rollen-Check
    def user_has_role(role):
        return has_role(user['roles'], role)
    
    einsatz = db.execute('''
        SELECT a.*, u.name, u.vorname, u.ortsteil
        FROM arbeitseinsaetze a
        JOIN user u ON a.user_id = u.id
        WHERE a.id = ?
    ''', (einsatz_id,)).fetchone()
    
    if not einsatz:
        flash('Einsatz nicht gefunden', 'danger')
        return redirect(url_for('index'))
    
    # Zugriffskontrolle
    if user_has_role('wegewart') and einsatz['user_id'] != user['id']:
        flash('Keine Berechtigung', 'danger')
        return redirect(url_for('index'))
    elif user_has_role('ortsvorsteher') and einsatz['ortsteil'] != user['ortsteil']:
        flash('Keine Berechtigung', 'danger')
        return redirect(url_for('index'))
    
    return render_template('einsatz_detail.html', user=user, einsatz=einsatz)

@app.route('/einsatz/<int:einsatz_id>/freigeben', methods=['POST'])
@rolle_required('ortsvorsteher', 'admin', 'verwaltung')
def einsatz_freigeben(einsatz_id):
    """Arbeitseinsatz freigeben (Ortsvorsteher)"""
    user = get_current_user()
    db = get_db()
    
    # Hilfsfunktion zum Rollen-Check
    def user_has_role(role):
        return has_role(user['roles'], role)
    
    if user_has_role('ortsvorsteher'):
        db.execute('''
            UPDATE arbeitseinsaetze
            SET status = 'freigegeben_ov', checked_time = CURRENT_TIMESTAMP, checked_by = ?
            WHERE id = ?
        ''', (user['id'], einsatz_id))
        flash('Einsatz freigegeben', 'success')
    elif user_has_role('admin') or user_has_role('verwaltung'):
        db.execute('''
            UPDATE arbeitseinsaetze
            SET status = 'abgerechnet', checked_time = CURRENT_TIMESTAMP, checked_by = ?
            WHERE id = ?
        ''', (user['id'], einsatz_id))
        flash('Einsatz abgerechnet', 'success')
    
    db.commit()
    return redirect(url_for('einsatz_detail', einsatz_id=einsatz_id))

@app.route('/einsatz/<int:einsatz_id>/ablehnen', methods=['POST'])
@rolle_required('ortsvorsteher', 'admin', 'verwaltung')
def einsatz_ablehnen(einsatz_id):
    """Arbeitseinsatz ablehnen"""
    db = get_db()
    
    grund = request.form.get('ablehnungsgrund', '')
    
    db.execute('''
        UPDATE arbeitseinsaetze
        SET status = 'abgelehnt', rejection_reason = ?
        WHERE id = ?
    ''', (grund, einsatz_id))
    
    db.commit()
    flash('Einsatz abgelehnt', 'warning')
    return redirect(url_for('einsatz_detail', einsatz_id=einsatz_id))

@app.route('/einsaetze/freigeben', methods=['GET'])
@rolle_required('ortsvorsteher', 'admin', 'verwaltung')
def einsaetze_freigeben():
    """Massen-Freigabe für Ortsvorsteher"""
    user = get_current_user()
    db = get_db()
    
    # Hilfsfunktion zum Rollen-Check
    def user_has_role(role):
        return has_role(user['roles'], role)
    
    # Filter-Parameter
    datum_von = request.args.get('datum_von', '')
    datum_bis = request.args.get('datum_bis', '')
    wegewart_filter = request.args.get('wegewart', '')
    
    # Query aufbauen
    query = '''
        SELECT a.*, u.name, u.vorname
        FROM arbeitseinsaetze a
        JOIN user u ON a.user_id = u.id
        WHERE a.status = 'erfasst'
    '''
    params = []
    
    # Rollenbasierte Filter
    if user_has_role('ortsvorsteher'):
        query += ' AND u.ortsteil = ?'
        params.append(user['ortsteil'])
    
    # Datumsfilter
    if datum_von:
        query += ' AND a.datum >= ?'
        params.append(datum_von)
    
    if datum_bis:
        query += ' AND a.datum <= ?'
        params.append(datum_bis)
    
    # Wegewart-Filter
    if wegewart_filter:
        query += ' AND a.user_id = ?'
        params.append(int(wegewart_filter))
    
    query += ' ORDER BY a.datum DESC, u.name'
    
    einsaetze = db.execute(query, params).fetchall()
    
    # Wegewarte für Filter laden
    if user_has_role('ortsvorsteher'):
        wegewarte = db.execute('''
            SELECT DISTINCT id, vorname, name FROM user 
            WHERE ortsteil = ? AND roles LIKE '%wegewart%' AND aktiv = 1
            ORDER BY name
        ''', (user['ortsteil'],)).fetchall()
    else:
        wegewarte = db.execute('''
            SELECT DISTINCT id, vorname, name FROM user 
            WHERE roles LIKE '%wegewart%' AND aktiv = 1
            ORDER BY name
        ''').fetchall()
    
    return render_template('einsaetze_freigeben.html', 
                         user=user, 
                         einsaetze=einsaetze,
                         wegewarte=wegewarte,
                         datum_von=datum_von,
                         datum_bis=datum_bis,
                         wegewart_filter=wegewart_filter)

@app.route('/einsaetze/massenfreigabe', methods=['POST'])
@rolle_required('ortsvorsteher', 'admin', 'verwaltung')
def einsaetze_massenfreigabe():
    """Mehrere Einsätze auf einmal freigeben"""
    user = get_current_user()
    db = get_db()
    
    # Hilfsfunktion zum Rollen-Check
    def user_has_role(role):
        return has_role(user['roles'], role)
    
    einsatz_ids = request.form.getlist('einsatz_ids[]')
    
    if not einsatz_ids:
        flash('Keine Einsätze ausgewählt', 'warning')
        return redirect(url_for('einsaetze_freigeben'))
    
    erfolg = 0
    for einsatz_id in einsatz_ids:
        try:
            if user_has_role('ortsvorsteher'):
                db.execute('''
                    UPDATE arbeitseinsaetze
                    SET status = 'freigegeben_ov', 
                        checked_time = CURRENT_TIMESTAMP, 
                        checked_by = ?
                    WHERE id = ?
                ''', (user['id'], int(einsatz_id)))
            else:  # admin / verwaltung
                db.execute('''
                    UPDATE arbeitseinsaetze
                    SET status = 'abgerechnet', 
                        checked_time = CURRENT_TIMESTAMP, 
                        checked_by = ?
                    WHERE id = ?
                ''', (user['id'], int(einsatz_id)))
            erfolg += 1
        except:
            continue
    
    db.commit()
    
    if erfolg == 1:
        flash(f'1 Einsatz freigegeben', 'success')
    else:
        flash(f'{erfolg} Einsätze freigegeben', 'success')
    
    return redirect(url_for('einsaetze_freigeben'))

@app.route('/einsaetze/massenablehnung', methods=['POST'])
@rolle_required('ortsvorsteher', 'admin', 'verwaltung')
def einsaetze_massenablehnung():
    """Mehrere Einsätze auf einmal ablehnen"""
    db = get_db()
    
    einsatz_ids_str = request.form.get('einsatz_ids', '')
    ablehnungsgrund = request.form.get('ablehnungsgrund', '')
    
    if not einsatz_ids_str or not ablehnungsgrund:
        flash('Fehler: Keine Einsätze oder kein Ablehnungsgrund angegeben', 'danger')
        return redirect(url_for('einsaetze_freigeben'))
    
    einsatz_ids = einsatz_ids_str.split(',')
    
    erfolg = 0
    for einsatz_id in einsatz_ids:
        try:
            db.execute('''
                UPDATE arbeitseinsaetze
                SET status = 'abgelehnt', rejection_reason = ?
                WHERE id = ?
            ''', (ablehnungsgrund, int(einsatz_id)))
            erfolg += 1
        except:
            continue
    
    db.commit()
    
    if erfolg == 1:
        flash(f'1 Einsatz abgelehnt', 'warning')
    else:
        flash(f'{erfolg} Einsätze abgelehnt', 'warning')
    
    return redirect(url_for('einsaetze_freigeben'))

@app.route('/maschinen')
@login_required
def maschinen_liste():
    """Liste aller Maschinen"""
    db = get_db()
    user = get_current_user()
    
    # Hilfsfunktion zum Rollen-Check
    def user_has_role(role):
        return has_role(user['roles'], role)
    
    # Admin/Verwaltung sehen alle, andere nur aktive
    if user_has_role('admin') or user_has_role('verwaltung'):
        maschinen = db.execute('SELECT * FROM machines ORDER BY aktiv DESC, bezeichnung').fetchall()
    else:
        maschinen = db.execute('SELECT * FROM machines WHERE aktiv = 1 ORDER BY bezeichnung').fetchall()
    
    return render_template('maschinen_liste.html', user=user, maschinen=maschinen)

@app.route('/maschinen/neu', methods=['GET', 'POST'])
@rolle_required('admin', 'verwaltung')
def maschine_neu():
    """Neue Maschine anlegen"""
    if request.method == 'POST':
        bezeichnung = request.form.get('bezeichnung', '').strip()
        aktiv = 1 if request.form.get('aktiv') == 'on' else 0
        
        # Validierung
        if not bezeichnung:
            flash('Bitte Bezeichnung eingeben', 'danger')
            return render_template('maschine_neu.html', user=get_current_user())
        
        db = get_db()
        try:
            db.execute('''
                INSERT INTO machines (bezeichnung, aktiv)
                VALUES (?, ?)
            ''', (bezeichnung, aktiv))
            db.commit()
            flash(f'Maschine "{bezeichnung}" erfolgreich angelegt', 'success')
            return redirect(url_for('maschinen_liste'))
        except Exception as e:
            flash(f'Fehler beim Anlegen der Maschine: {e}', 'danger')
    
    return render_template('maschine_neu.html', user=get_current_user())

@app.route('/maschinen/<int:maschine_id>/bearbeiten', methods=['GET', 'POST'])
@rolle_required('admin', 'verwaltung')
def maschine_bearbeiten(maschine_id):
    """Maschine bearbeiten"""
    db = get_db()
    maschine_edit = db.execute('SELECT * FROM machines WHERE id = ?', (maschine_id,)).fetchone()
    
    if not maschine_edit:
        flash('Maschine nicht gefunden', 'danger')
        return redirect(url_for('maschinen_liste'))
    
    if request.method == 'POST':
        bezeichnung = request.form.get('bezeichnung', '').strip()
        aktiv = 1 if request.form.get('aktiv') == 'on' else 0
        
        if not bezeichnung:
            flash('Bitte Bezeichnung eingeben', 'danger')
            return render_template('maschine_bearbeiten.html', user=get_current_user(), maschine_edit=maschine_edit)
        
        try:
            db.execute('''
                UPDATE machines 
                SET bezeichnung = ?, aktiv = ?
                WHERE id = ?
            ''', (bezeichnung, aktiv, maschine_id))
            db.commit()
            flash('Maschine erfolgreich aktualisiert', 'success')
            return redirect(url_for('maschinen_liste'))
        except Exception as e:
            flash(f'Fehler beim Aktualisieren: {e}', 'danger')
    
    return render_template('maschine_bearbeiten.html', user=get_current_user(), maschine_edit=maschine_edit)

@app.route('/maschinen/<int:maschine_id>/deaktivieren', methods=['POST'])
@rolle_required('admin', 'verwaltung')
def maschine_deaktivieren(maschine_id):
    """Maschine deaktivieren"""
    db = get_db()
    db.execute('UPDATE machines SET aktiv = 0 WHERE id = ?', (maschine_id,))
    db.commit()
    flash('Maschine deaktiviert', 'warning')
    return redirect(url_for('maschinen_liste'))

@app.route('/maschinen/<int:maschine_id>/aktivieren', methods=['POST'])
@rolle_required('admin', 'verwaltung')
def maschine_aktivieren(maschine_id):
    """Maschine aktivieren"""
    db = get_db()
    db.execute('UPDATE machines SET aktiv = 1 WHERE id = ?', (maschine_id,))
    db.commit()
    flash('Maschine aktiviert', 'success')
    return redirect(url_for('maschinen_liste'))

@app.route('/admin/benutzer')
@rolle_required('admin', 'verwaltung')
def admin_benutzer():
    """Benutzerverwaltung"""
    db = get_db()
    benutzer = db.execute('SELECT * FROM user ORDER BY ortsteil, name').fetchall()
    return render_template('admin_benutzer.html', user=get_current_user(), benutzer=benutzer)

@app.route('/admin/benutzer/neu', methods=['GET', 'POST'])
@rolle_required('admin', 'verwaltung')
def admin_benutzer_neu():
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
            return render_template('admin_benutzer_neu.html', user=get_current_user())
        
        if len(passwort) < 6:
            flash('Passwort muss mindestens 6 Zeichen lang sein', 'danger')
            return render_template('admin_benutzer_neu.html', user=get_current_user())
        
        # Benutzername-Format prüfen
        import re
        if not re.match(r'^[a-z0-9._]+$', benutzername):
            flash('Benutzername darf nur Kleinbuchstaben, Zahlen, Punkt und Unterstrich enthalten', 'danger')
            return render_template('admin_benutzer_neu.html', user=get_current_user())
        
        db = get_db()
        
        # Prüfen ob Benutzername schon existiert
        existing = db.execute('SELECT id FROM user WHERE username = ?', (benutzername,)).fetchone()
        if existing:
            flash(f'Benutzername "{benutzername}" existiert bereits', 'danger')
            return render_template('admin_benutzer_neu.html', user=get_current_user())
        
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
            return redirect(url_for('admin_benutzer'))
        except Exception as e:
            flash(f'Fehler beim Anlegen des Benutzers: {e}', 'danger')
    
    return render_template('admin_benutzer_neu.html', user=get_current_user())

@app.route('/admin/benutzer/<int:benutzer_id>/bearbeiten', methods=['GET', 'POST'])
@rolle_required('admin', 'verwaltung')
def admin_benutzer_bearbeiten(benutzer_id):
    """Benutzer bearbeiten"""
    db = get_db()
    benutzer_edit = db.execute('SELECT * FROM user WHERE id = ?', (benutzer_id,)).fetchone()
    
    if not benutzer_edit:
        flash('Benutzer nicht gefunden', 'danger')
        return redirect(url_for('admin_benutzer'))
    
    if request.method == 'POST':
        vorname = request.form.get('vorname', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        ortsteil = request.form.get('ortsteil')
        rolle = request.form.get('rolle')
        aktiv = 1 if request.form.get('aktiv') == 'on' else 0
        neues_passwort = request.form.get('neues_passwort', '').strip()
        neues_passwort_confirm = request.form.get('neues_passwort_confirm', '').strip()
        
        # Validierung
        if not all([vorname, name, ortsteil, rolle]):
            flash('Bitte alle Pflichtfelder ausfüllen', 'danger')
            return render_template('admin_benutzer_bearbeiten.html', user=get_current_user(), benutzer_edit=benutzer_edit)
        
        # Passwort ändern (falls angegeben)
        if neues_passwort:
            if len(neues_passwort) < 6:
                flash('Passwort muss mindestens 6 Zeichen lang sein', 'danger')
                return render_template('admin_benutzer_bearbeiten.html', user=get_current_user(), benutzer_edit=benutzer_edit)
            
            if neues_passwort != neues_passwort_confirm:
                flash('Passwörter stimmen nicht überein', 'danger')
                return render_template('admin_benutzer_bearbeiten.html', user=get_current_user(), benutzer_edit=benutzer_edit)
            
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
        return redirect(url_for('admin_benutzer'))
    
    return render_template('admin_benutzer_bearbeiten.html', user=get_current_user(), benutzer_edit=benutzer_edit)

@app.route('/admin/benutzer/<int:benutzer_id>/deaktivieren', methods=['POST'])
@rolle_required('admin', 'verwaltung')
def admin_benutzer_deaktivieren(benutzer_id):
    """Benutzer deaktivieren"""
    db = get_db()
    db.execute('UPDATE user SET aktiv = 0 WHERE id = ?', (benutzer_id,))
    db.commit()
    flash('Benutzer deaktiviert', 'warning')
    return redirect(url_for('admin_benutzer'))

@app.route('/admin/benutzer/<int:benutzer_id>/aktivieren', methods=['POST'])
@rolle_required('admin', 'verwaltung')
def admin_benutzer_aktivieren(benutzer_id):
    """Benutzer aktivieren"""
    db = get_db()
    db.execute('UPDATE user SET aktiv = 1 WHERE id = ?', (benutzer_id,))
    db.commit()
    flash('Benutzer aktiviert', 'success')
    return redirect(url_for('admin_benutzer'))


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