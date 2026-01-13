"""
Auth Blueprint - Login, Logout, Passwort ändern
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from wayward_db import get_db
from utils.decorators import login_required, get_current_user

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login-Seite"""
    if request.method == 'POST':
        username = request.form.get('benutzername')
        passwort = request.form.get('passwort')
        
        db = get_db()
        user = db.execute(
            'SELECT * FROM user WHERE username = ? AND aktiv = 1', 
            (username,)
        ).fetchone()
        
        if user and check_password_hash(user['password_hash'], passwort):
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['roles'] = user['roles']
            flash(f'Willkommen, {user["vorname"]} {user["name"]}!', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Ungültige Zugangsdaten', 'danger')
    
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Logout"""
    session.clear()
    flash('Erfolgreich abgemeldet', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profil/passwort', methods=['GET', 'POST'])
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
            db.execute(
                'UPDATE user SET password_hash = ? WHERE id = ?',
                (generate_password_hash(neues_pw), user['id'])
            )
            db.commit()
            flash('Passwort erfolgreich geändert', 'success')
            return redirect(url_for('main.index'))
    
    return render_template('passwort_aendern.html', user=user)
