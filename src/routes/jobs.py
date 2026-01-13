"""
Jobs Blueprint - Arbeitseinsätze verwalten
"""

from flask import Blueprint, render_template, request, jsonify, session

from wayward_db import get_db
from utils.decorators import login_required, rolle_required, get_current_user
from utils.filters import has_role

jobs_bp = Blueprint('jobs', __name__, url_prefix='/jobs')


def row_to_dict(row):
    """Konvertiert eine SQLite Row zu einem Dictionary"""
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    """Konvertiert eine Liste von SQLite Rows zu einer Liste von Dictionaries"""
    return [dict(row) for row in rows]


def get_user_role():
    """Ermittelt die primäre Rolle des Users für die Anzeige"""
    user = get_current_user()
    if not user:
        return None
    
    roles = user['roles'].split(',') if user['roles'] else []
    roles = [r.strip() for r in roles]
    
    # Priorität: admin > ortsvorsteher > wegewart
    if 'admin' in roles:
        return 'admin'
    elif 'ortsvorsteher' in roles:
        return 'ortsvorsteher'
    elif 'wegewart' in roles:
        return 'wegewart'
    return roles[0] if roles else None


def get_user_villages(user):
    """Gibt die Ortschaften zurück, auf die der User Zugriff hat"""
    roles = user['roles'].split(',') if user['roles'] else []
    roles = [r.strip() for r in roles]
    
    if 'admin' in roles:
        # Admin sieht alle Ortschaften
        db = get_db()
        villages = db.execute('SELECT DISTINCT ortsteil FROM user WHERE ortsteil IS NOT NULL').fetchall()
        return [v['ortsteil'] for v in villages]
    else:
        # Andere sehen nur ihre eigene Ortschaft
        return [user['ortsteil']] if user['ortsteil'] else []


@jobs_bp.route('')
@login_required
def jobs():
    """Arbeitseinsätze anzeigen"""
    user = get_current_user()
    user_role = get_user_role()
    db = get_db()
    
    # Filter aus Request
    wegewart_filter = request.args.get('wegewart_filter', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    village_filter = request.args.get('village_filter', '')
    
    # Basis-Query
    query = '''
        SELECT 
            j.*,
            u.name || ', ' || u.vorname as wegewart_name,
            u.ortsteil,
            m.name as machine_name
        FROM jobs j
        JOIN user u ON j.user_id = u.id
        LEFT JOIN machines m ON j.machine_id = m.id
        WHERE 1=1
    '''
    params = []
    
    # Rollenbasierte Filterung
    if user_role == 'wegewart':
        query += ' AND j.user_id = ?'
        params.append(user['id'])
    elif user_role == 'ortsvorsteher':
        query += ' AND u.ortsteil = ?'
        params.append(user['ortsteil'])
    
    # Zusätzliche Filter
    if wegewart_filter:
        query += ' AND j.user_id = ?'
        params.append(wegewart_filter)
    
    if date_from:
        query += ' AND j.date >= ?'
        params.append(date_from)
    
    if date_to:
        query += ' AND j.date <= ?'
        params.append(date_to)
    
    if village_filter:
        query += ' AND u.ortsteil = ?'
        params.append(village_filter)
    
    query += ' ORDER BY j.date DESC, j.time_start DESC'
    
    jobs_rows = db.execute(query, params).fetchall()
    
    # Verfügbare Wegewarten für Filter und Dropdown
    if user_role in ['admin', 'ortsvorsteher']:
        if user_role == 'admin':
            wegewarten_rows = db.execute('''
                SELECT id, vorname, name, ortsteil 
                FROM user 
                WHERE roles LIKE '%wegewart%' AND aktiv = 1
                ORDER BY ortsteil, name
            ''').fetchall()
        else:
            wegewarten_rows = db.execute('''
                SELECT id, vorname, name, ortsteil 
                FROM user 
                WHERE roles LIKE '%wegewart%' AND aktiv = 1 AND ortsteil = ?
                ORDER BY name
            ''', (user['ortsteil'],)).fetchall()
    else:
        wegewarten_rows = [user]
    
    # Maschinen laden
    machines_rows = db.execute('SELECT id, name FROM machines WHERE aktiv = 1 ORDER BY name').fetchall()
    
    # User villages
    user_villages = get_user_villages(user)
    
    # *** WICHTIG: SQLite Rows zu Dictionaries konvertieren für tojson ***
    machines_list = rows_to_list(machines_rows)
    wegewarten_list = rows_to_list(wegewarten_rows)
    jobs_list = rows_to_list(jobs_rows)
    
    return render_template('jobs.html',
        user=user,
        jobs=jobs_list,
        machines=machines_list,
        available_wegewarten=wegewarten_list,
        user_role=user_role,
        user_villages=user_villages,
        current_user_id=user['id'],
        current_user_ortsteil=user['ortsteil'] or ''
    )


@jobs_bp.route('/create', methods=['POST'])
@login_required
def create_job():
    """Neuen Arbeitseinsatz erstellen"""
    user = get_current_user()
    data = request.get_json()
    
    # User-ID: Admin/OV können für andere erfassen
    user_role = get_user_role()
    if user_role in ['admin', 'ortsvorsteher'] and data.get('user_id'):
        target_user_id = data['user_id']
    else:
        target_user_id = user['id']
    
    db = get_db()
    
    try:
        db.execute('''
            INSERT INTO jobs (user_id, date, time_start, time_end, pause_hours, work_hours, 
                            work_comment, machine_id, machine_hours, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            target_user_id,
            data.get('date'),
            data.get('time_start'),
            data.get('time_end'),
            data.get('pause_hours', 0),
            data.get('work_hours', 0),
            data.get('work_comment', ''),
            data.get('machine_id') or None,
            data.get('machine_hours', 0),
            data.get('status', 'erfasst')
        ))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@jobs_bp.route('/update', methods=['POST'])
@login_required
def update_job():
    """Arbeitseinsatz aktualisieren"""
    user = get_current_user()
    user_role = get_user_role()
    data = request.get_json()
    job_id = data.get('job_id')
    
    db = get_db()
    
    # Prüfen ob User berechtigt ist
    job = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not job:
        return jsonify({'success': False, 'message': 'Einsatz nicht gefunden'})
    
    # Nur eigene oder als Admin/OV
    if job['user_id'] != user['id'] and user_role not in ['admin', 'ortsvorsteher']:
        return jsonify({'success': False, 'message': 'Keine Berechtigung'})
    
    try:
        # Status nur für Admin/OV änderbar
        if user_role in ['admin', 'ortsvorsteher']:
            db.execute('''
                UPDATE jobs SET 
                    date = ?, time_start = ?, time_end = ?, pause_hours = ?, work_hours = ?,
                    work_comment = ?, machine_id = ?, machine_hours = ?, status = ?
                WHERE id = ?
            ''', (
                data.get('date'),
                data.get('time_start'),
                data.get('time_end'),
                data.get('pause_hours', 0),
                data.get('work_hours', 0),
                data.get('work_comment', ''),
                data.get('machine_id') or None,
                data.get('machine_hours', 0),
                data.get('status', 'erfasst'),
                job_id
            ))
        else:
            # Wegewart kann nur nicht-freigegebene Einträge ändern
            if job['status'] == 'freigegeben':
                return jsonify({'success': False, 'message': 'Freigegebene Einträge können nicht geändert werden'})
            
            db.execute('''
                UPDATE jobs SET 
                    date = ?, time_start = ?, time_end = ?, pause_hours = ?, work_hours = ?,
                    work_comment = ?, machine_id = ?, machine_hours = ?
                WHERE id = ?
            ''', (
                data.get('date'),
                data.get('time_start'),
                data.get('time_end'),
                data.get('pause_hours', 0),
                data.get('work_hours', 0),
                data.get('work_comment', ''),
                data.get('machine_id') or None,
                data.get('machine_hours', 0),
                job_id
            ))
        
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@jobs_bp.route('/delete', methods=['POST'])
@login_required
def delete_job():
    """Arbeitseinsatz löschen"""
    user = get_current_user()
    user_role = get_user_role()
    data = request.get_json()
    job_id = data.get('job_id')
    
    db = get_db()
    
    job = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not job:
        return jsonify({'success': False, 'message': 'Einsatz nicht gefunden'})
    
    # Berechtigungsprüfung
    if job['user_id'] != user['id'] and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Keine Berechtigung'})
    
    # Freigegebene nur als Admin löschbar
    if job['status'] == 'freigegeben' and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Freigegebene Einträge können nicht gelöscht werden'})
    
    try:
        db.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@jobs_bp.route('/approve', methods=['POST'])
@rolle_required('admin', 'ortsvorsteher')
def approve_jobs():
    """Mehrere Arbeitseinsätze freigeben"""
    data = request.get_json()
    job_ids = data.get('job_ids', [])
    
    if not job_ids:
        return jsonify({'success': False, 'message': 'Keine Einsätze ausgewählt'})
    
    db = get_db()
    
    try:
        placeholders = ','.join(['?' for _ in job_ids])
        db.execute(f'''
            UPDATE jobs SET status = 'freigegeben', approved_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders}) AND status = 'erfasst'
        ''', job_ids)
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@jobs_bp.route('/reject', methods=['POST'])
@rolle_required('admin', 'ortsvorsteher')
def reject_jobs():
    """Mehrere Arbeitseinsätze ablehnen"""
    data = request.get_json()
    job_ids = data.get('job_ids', [])
    reason = data.get('rejection_reason', '')
    
    if not job_ids:
        return jsonify({'success': False, 'message': 'Keine Einsätze ausgewählt'})
    
    db = get_db()
    
    try:
        for job_id in job_ids:
            db.execute('''
                UPDATE jobs SET status = 'abgelehnt', rejection_reason = ?
                WHERE id = ? AND status = 'erfasst'
            ''', (reason, job_id))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})