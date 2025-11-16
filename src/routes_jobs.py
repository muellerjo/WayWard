"""
Jobs Routes Blueprint for Wegewart System
"""
from flask import Blueprint, render_template, request, jsonify, g
from functools import wraps

# Create Blueprint
jobs_bp = Blueprint('jobs', __name__)

# Decorator for login required
def login_required(f):
    """Decorator to check if user is logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.get('user'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper functions
def get_user_roles(user):
    """Get list of roles for a user"""
    if not user or not user['roles']:
        return []
    return [role.strip() for role in user['roles'].split(',')]

def get_user_villages(user):
    """Get list of villages the user has access to"""
    if not user:
        return []
    return [user['ortsteil']]

def get_available_wegewarten(user):
    """Get list of Wegewarten that the user can assign jobs to"""
    from wayward_db import get_db
    db = get_db()
    
    roles = get_user_roles(user)
    villages = get_user_villages(user)
    
    if 'admin' in roles:
        # Admin sees all wegewarten
        cursor = db.execute("""
            SELECT id, username, name, vorname, ortsteil, roles
            FROM user
            WHERE roles LIKE '%wegewart%' AND aktiv = 1
            ORDER BY name, vorname
        """)
        return cursor.fetchall()
    
    elif 'ortsvorsteher' in roles:
        # Ortsvorsteher sees wegewarten from their villages
        placeholders = ','.join('?' * len(villages))
        cursor = db.execute(f"""
            SELECT id, username, name, vorname, ortsteil, roles
            FROM user
            WHERE roles LIKE '%wegewart%' 
            AND aktiv = 1
            AND ortsteil IN ({placeholders})
            ORDER BY name, vorname
        """, villages)
        return cursor.fetchall()
    
    else:
        # Regular user only sees themselves
        return [user]

def get_machines():
    """Get all active machines"""
    from wayward_db import get_db
    db = get_db()
    cursor = db.execute("SELECT id, bezeichnung FROM machines WHERE aktiv = 1 ORDER BY bezeichnung")
    return cursor.fetchall()

# Routes

@jobs_bp.route('/jobs')
@login_required
def jobs():
    """Display jobs page"""
    from wayward_db import get_db
    db = get_db()
    
    roles = get_user_roles(g.user)
    villages = get_user_villages(g.user)
    
    # Build base query
    query = '''
        SELECT 
            j.*,
            u.name || ' ' || u.vorname as wegewart_name,
            u.ortsteil,
            m.bezeichnung as machine_name
        FROM jobs j
        JOIN user u ON j.user_id = u.id
        LEFT JOIN machines m ON j.machine_used = m.id
        WHERE 1=1
    '''
    params = []
    
    # Role-based filtering
    if 'admin' in roles:
        # Admin sees everything
        pass
    elif 'ortsvorsteher' in roles:
        # Ortsvorsteher sees jobs from their villages
        placeholders = ','.join('?' * len(villages))
        query += f' AND u.ortsteil IN ({placeholders})'
        params.extend(villages)
    else:
        # Regular wegewart sees only their own jobs
        query += ' AND j.user_id = ?'
        params.append(g.user['id'])
    
    # Apply filters
    wegewart_filter = request.args.get('wegewart_filter')
    if wegewart_filter and ('admin' in roles or 'ortsvorsteher' in roles):
        query += ' AND j.user_id = ?'
        params.append(wegewart_filter)
    
    date_from = request.args.get('date_from')
    if date_from:
        query += ' AND j.datum >= ?'
        params.append(date_from)
    
    date_to = request.args.get('date_to')
    if date_to:
        query += ' AND j.datum <= ?'
        params.append(date_to)
    
    village_filter = request.args.get('village_filter')
    if village_filter:
        query += ' AND u.ortsteil = ?'
        params.append(village_filter)
    
    # Order by date descending
    query += ' ORDER BY j.datum DESC, j.created_at DESC'
    
    cursor = db.execute(query, params)
    jobs_list = cursor.fetchall()
    
    # Get available wegewarten
    available_wegewarten = get_available_wegewarten(g.user)
    
    # Get machines
    machines_list = get_machines()
    
    # Determine user role
    if 'admin' in roles:
        user_role = 'admin'
    elif 'ortsvorsteher' in roles:
        user_role = 'ortsvorsteher'
    else:
        user_role = 'wegewart'
    
    return render_template('jobs.html',
                         jobs=jobs_list,
                         user_role=user_role,
                         user_villages=villages,
                         available_wegewarten=available_wegewarten,
                         machines=machines_list,
                         current_user_id=g.user['id'],
                         current_user_name=f"{g.user['vorname']} {g.user['name']}",
                         current_user_ortsteil=g.user['ortsteil'])


@jobs_bp.route('/jobs/create', methods=['POST'])
@login_required
def create_job():
    """Create a new job"""
    from wayward_db import get_db
    db = get_db()
    
    try:
        data = request.get_json()
        
        # Check permissions
        roles = get_user_roles(g.user)
        user_id = int(data.get('user_id', g.user['id']))
        
        # Only admin and ortsvorsteher can create jobs for others
        if user_id != g.user['id'] and not any(r in roles for r in ['admin', 'ortsvorsteher']):
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        # Create job
        machine_used = data.get('machine_used')
        if machine_used == '':
            machine_used = None
        
        cursor = db.execute('''
            INSERT INTO jobs (user_id, datum, arbeitsstunden, taetigkeitsbeschreibung, machine_used, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            data['datum'],
            float(data['arbeitsstunden']),
            data['taetigkeitsbeschreibung'],
            machine_used,
            data.get('status', 'erfasst')
        ))
        db.commit()
        
        return jsonify({'success': True, 'job_id': cursor.lastrowid})
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@jobs_bp.route('/jobs/update', methods=['POST'])
@login_required
def update_job():
    """Update an existing job"""
    from wayward_db import get_db
    db = get_db()
    
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        
        # Get job
        cursor = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
        job = cursor.fetchone()
        
        if not job:
            return jsonify({'success': False, 'message': 'Job nicht gefunden'}), 404
        
        # Check permissions
        roles = get_user_roles(g.user)
        villages = get_user_villages(g.user)
        
        # Get job's village
        cursor = db.execute('SELECT ortsteil FROM user WHERE id = ?', (job['user_id'],))
        job_user = cursor.fetchone()
        
        can_edit = False
        if 'admin' in roles:
            can_edit = True
        elif 'ortsvorsteher' in roles and job_user['ortsteil'] in villages:
            can_edit = True
        elif job['user_id'] == g.user['id'] and job['status'] != 'freigegeben':
            can_edit = True
        
        if not can_edit:
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        # Build UPDATE query
        updates = []
        params = []
        
        if 'datum' in data:
            updates.append('datum = ?')
            params.append(data['datum'])
        
        if 'user_id' in data and ('admin' in roles or 'ortsvorsteher' in roles):
            updates.append('user_id = ?')
            params.append(int(data['user_id']))
        
        if 'taetigkeitsbeschreibung' in data:
            updates.append('taetigkeitsbeschreibung = ?')
            params.append(data['taetigkeitsbeschreibung'])
        
        if 'arbeitsstunden' in data:
            updates.append('arbeitsstunden = ?')
            params.append(float(data['arbeitsstunden']))
        
        if 'machine_used' in data:
            machine_used = data['machine_used']
            if machine_used == '':
                machine_used = None
            updates.append('machine_used = ?')
            params.append(machine_used)
        
        if 'status' in data and ('admin' in roles or 'ortsvorsteher' in roles):
            updates.append('status = ?')
            params.append(data['status'])
            
            # If status changed to freigegeben/abgelehnt, set checked fields
            if data['status'] in ['freigegeben', 'abgelehnt']:
                updates.append('checked_by = ?')
                params.append(g.user['id'])
                updates.append('checked_time = CURRENT_TIMESTAMP')
        
        if not updates:
            return jsonify({'success': False, 'message': 'Keine Änderungen'}), 400
        
        params.append(job_id)
        query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"
        
        db.execute(query, params)
        db.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@jobs_bp.route('/jobs/delete', methods=['POST'])
@login_required
def delete_job():
    """Delete a job"""
    from wayward_db import get_db
    db = get_db()
    
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        
        # Get job
        cursor = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
        job = cursor.fetchone()
        
        if not job:
            return jsonify({'success': False, 'message': 'Job nicht gefunden'}), 404
        
        # Check permissions
        roles = get_user_roles(g.user)
        villages = get_user_villages(g.user)
        
        # Get job's village
        cursor = db.execute('SELECT ortsteil FROM user WHERE id = ?', (job['user_id'],))
        job_user = cursor.fetchone()
        
        can_delete = False
        if 'admin' in roles:
            can_delete = True
        elif 'ortsvorsteher' in roles and job_user['ortsteil'] in villages:
            can_delete = True
        elif job['user_id'] == g.user['id'] and job['status'] != 'freigegeben':
            can_delete = True
        
        if not can_delete:
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        db.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
        db.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@jobs_bp.route('/jobs/approve', methods=['POST'])
@login_required
def approve_jobs():
    """Approve multiple jobs"""
    from wayward_db import get_db
    db = get_db()
    
    try:
        data = request.get_json()
        job_ids = data.get('job_ids', [])
        
        # Check permissions
        roles = get_user_roles(g.user)
        if not any(r in roles for r in ['admin', 'ortsvorsteher']):
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        if not job_ids:
            return jsonify({'success': False, 'message': 'Keine Jobs ausgewählt'}), 400
        
        villages = get_user_villages(g.user)
        approved_count = 0
        
        for job_id in job_ids:
            # Get job
            cursor = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
            job = cursor.fetchone()
            
            if not job:
                continue
            
            # Get job's village
            cursor = db.execute('SELECT ortsteil FROM user WHERE id = ?', (job['user_id'],))
            job_user = cursor.fetchone()
            
            # Check permissions
            can_approve = False
            if 'admin' in roles:
                can_approve = True
            elif 'ortsvorsteher' in roles and job_user['ortsteil'] in villages:
                can_approve = True
            
            if can_approve and job['status'] == 'erfasst':
                db.execute('''
                    UPDATE jobs 
                    SET status = 'freigegeben',
                        checked_by = ?,
                        checked_time = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (g.user['id'], job_id))
                approved_count += 1
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': f'{approved_count} Einsatz/Einsätze freigegeben'
        })
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@jobs_bp.route('/jobs/reject', methods=['POST'])
@login_required
def reject_jobs():
    """Reject multiple jobs"""
    from wayward_db import get_db
    db = get_db()
    
    try:
        data = request.get_json()
        job_ids = data.get('job_ids', [])
        rejection_reason = data.get('rejection_reason', '')
        
        # Check permissions
        roles = get_user_roles(g.user)
        if not any(r in roles for r in ['admin', 'ortsvorsteher']):
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        if not job_ids:
            return jsonify({'success': False, 'message': 'Keine Jobs ausgewählt'}), 400
        
        villages = get_user_villages(g.user)
        rejected_count = 0
        
        for job_id in job_ids:
            # Get job
            cursor = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
            job = cursor.fetchone()
            
            if not job:
                continue
            
            # Get job's village
            cursor = db.execute('SELECT ortsteil FROM user WHERE id = ?', (job['user_id'],))
            job_user = cursor.fetchone()
            
            # Check permissions
            can_reject = False
            if 'admin' in roles:
                can_reject = True
            elif 'ortsvorsteher' in roles and job_user['ortsteil'] in villages:
                can_reject = True
            
            if can_reject and job['status'] == 'erfasst':
                db.execute('''
                    UPDATE jobs 
                    SET status = 'abgelehnt',
                        rejection_reason = ?,
                        checked_by = ?,
                        checked_time = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (rejection_reason, g.user['id'], job_id))
                rejected_count += 1
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': f'{rejected_count} Einsatz/Einsätze abgelehnt'
        })
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400