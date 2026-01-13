"""
Admin Blueprint - Benutzerverwaltung
"""

import re
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash

from wayward_db import get_db
from utils.decorators import rolle_required, get_current_user

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/user')
@rolle_required('admin', 'verwaltung', 'ortsvorsteher')
def user_list():
    """Benutzerverwaltung - Liste"""
    db = get_db()
    benutzer = db.execute(
        'SELECT * FROM user ORDER BY ortsteil, name'
    ).fetchall()
    return render_template('admin_user.html', user=get_current_user(), benutzer=benutzer)


@admin_bp.route('/user/new', methods=['GET', 'POST'])
@rolle_required('admin', 'verwaltung')
def user_new():
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
        if not re.match(r'^[a-z0-9._]+$', benutzername):
            flash('Benutzername darf nur Kleinbuchstaben, Zahlen, Punkt und Unterstrich enthalten', 'danger')
            return render_template('admin_user_new.html', user=get_current_user())
        
        db = get_db()
        
        # Prüfen ob Benutzername schon existiert
        existing = db.execute(
            'SELECT id FROM user WHERE username = ?', 
            (benutzername,)
        ).fetchone()
        
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
            return redirect(url_for('admin.user_list'))
        except Exception as e:
            flash(f'Fehler beim Anlegen des Benutzers: {e}', 'danger')
    
    return render_template('admin_user_new.html', user=get_current_user())


@admin_bp.route('/user/<int:benutzer_id>/modify', methods=['GET', 'POST'])
@rolle_required('admin', 'verwaltung')
def user_modify(benutzer_id):
    """Benutzer bearbeiten"""
    db = get_db()
    benutzer_edit = db.execute(
        'SELECT * FROM user WHERE id = ?', 
        (benutzer_id,)
    ).fetchone()
    
    if not benutzer_edit:
        flash('Benutzer nicht gefunden', 'danger')
        return redirect(url_for('admin.user_list'))
    
    if request.method == 'POST':
        vorname = request.form.get('vorname', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        ortsteil = request.form.get('ortsteil')
        
        # Get ALL selected roles as a list and join them with commas
        selected_roles = request.form.getlist('rolle')
        rolle = ','.join(selected_roles)
        
        aktiv = 1 if request.form.get('aktiv') == 'on' else 0
        neues_passwort = request.form.get('neues_passwort', '').strip()
        neues_passwort_confirm = request.form.get('neues_passwort_confirm', '').strip()
        
        # Validierung
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
        return redirect(url_for('admin.user_list'))
    
    return render_template('admin_user_modify.html', user=get_current_user(), benutzer_edit=benutzer_edit)


@admin_bp.route('/user/<int:benutzer_id>/deaktivieren', methods=['POST'])
@rolle_required('admin', 'verwaltung')
def user_deaktivieren(benutzer_id):
    """Benutzer deaktivieren"""
    db = get_db()
    db.execute('UPDATE user SET aktiv = 0 WHERE id = ?', (benutzer_id,))
    db.commit()
    flash('Benutzer deaktiviert', 'warning')
    return redirect(url_for('admin.user_list'))


@admin_bp.route('/user/<int:benutzer_id>/aktivieren', methods=['POST'])
@rolle_required('admin', 'verwaltung')
def user_aktivieren(benutzer_id):
    """Benutzer aktivieren"""
    db = get_db()
    db.execute('UPDATE user SET aktiv = 1 WHERE id = ?', (benutzer_id,))
    db.commit()
    flash('Benutzer aktiviert', 'success')
    return redirect(url_for('admin.user_list'))
