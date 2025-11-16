"""
Machines Routes Blueprint for Wegewart System
"""
from flask import Blueprint, render_template, request, jsonify, g, redirect, url_for, session, flash
from functools import wraps

# Create Blueprint
machines_bp = Blueprint('machines', __name__)

# Decorator for login required
def login_required(f):
    """Decorator für geschützte Routen"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Bitte zuerst einloggen', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper functions
def get_user_roles(user):
    """Get list of roles for a user"""
    if not user or not user['roles']:
        return []
    return [role.strip() for role in user['roles'].split(',')]

def can_user_manage_machines(user):
    """Check if user can manage machines"""
    roles = get_user_roles(user)
    return 'admin' in roles or 'ortsvorsteher' in roles

# Routes

@machines_bp.route('/machines')
@login_required
def machines():
    """Display machines page"""
    from wayward_db import get_db
    db = get_db()
    
    roles = get_user_roles(g.user)
    
    # Determine user role
    if 'admin' in roles:
        user_role = 'admin'
    elif 'ortsvorsteher' in roles:
        user_role = 'ortsvorsteher'
    else:
        user_role = 'wegewart'
    
    # Build base query
    query = 'SELECT * FROM machines WHERE 1=1'
    params = []
    
    # Apply filters
    category_filter = request.args.get('category_filter')
    if category_filter:
        query += ' AND category = ?'
        params.append(category_filter)
    
    status_filter = request.args.get('status_filter')
    if status_filter == 'aktiv':
        query += ' AND aktiv = 1'
    elif status_filter == 'inaktiv':
        query += ' AND aktiv = 0'
    
    # Order by status and name
    query += ' ORDER BY aktiv DESC, name'
    
    cursor = db.execute(query, params)
    machines_list = cursor.fetchall()
    
    # Get unique categories for filter
    cursor = db.execute('SELECT DISTINCT category FROM machines WHERE category IS NOT NULL AND category != "" ORDER BY category')
    categories = [row['category'] for row in cursor.fetchall()]
    
    return render_template('machines.html',
                         user=g.user,
                         machines=machines_list,
                         categories=categories,
                         user_role=user_role)


@machines_bp.route('/machines/create', methods=['POST'])
@login_required
def create_machine():
    """Create a new machine"""
    from wayward_db import get_db
    db = get_db()
    
    try:
        # Check permissions
        if not can_user_manage_machines(g.user):
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'success': False, 'message': 'Name ist erforderlich'}), 400
        
        # Handle empty strings
        category = data.get('category', '').strip() or None
        valid_from = data.get('valid_from_datetime', '').strip() or None
        valid_to = data.get('valid_to_datetime', '').strip() or None
        aktiv = int(data.get('aktiv', 1))
        
        # Create machine
        cursor = db.execute('''
            INSERT INTO machines (name, category, aktiv, valid_from_datetime, valid_to_datetime)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data['name'].strip(),
            category,
            aktiv,
            valid_from,
            valid_to
        ))
        db.commit()
        
        return jsonify({'success': True, 'machine_id': cursor.lastrowid})
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@machines_bp.route('/machines/update', methods=['POST'])
@login_required
def update_machine():
    """Update an existing machine"""
    from wayward_db import get_db
    db = get_db()
    
    try:
        # Check permissions
        if not can_user_manage_machines(g.user):
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        data = request.get_json()
        machine_id = data.get('machine_id')
        
        # Get machine
        cursor = db.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
        machine = cursor.fetchone()
        
        if not machine:
            return jsonify({'success': False, 'message': 'Maschine nicht gefunden'}), 404
        
        # Build UPDATE query
        updates = []
        params = []
        
        if 'name' in data:
            updates.append('name = ?')
            params.append(data['name'].strip())
        
        if 'category' in data:
            category = data['category'].strip() or None
            updates.append('category = ?')
            params.append(category)
        
        if 'valid_from_datetime' in data:
            valid_from = data['valid_from_datetime'].strip() or None
            updates.append('valid_from_datetime = ?')
            params.append(valid_from)
        
        if 'valid_to_datetime' in data:
            valid_to = data['valid_to_datetime'].strip() or None
            updates.append('valid_to_datetime = ?')
            params.append(valid_to)
        
        if 'aktiv' in data:
            updates.append('aktiv = ?')
            params.append(int(data['aktiv']))
        
        if not updates:
            return jsonify({'success': False, 'message': 'Keine Änderungen'}), 400
        
        params.append(machine_id)
        query = f"UPDATE machines SET {', '.join(updates)} WHERE id = ?"
        
        db.execute(query, params)
        db.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@machines_bp.route('/machines/delete', methods=['POST'])
@login_required
def delete_machine():
    """Delete a machine"""
    from wayward_db import get_db
    db = get_db()
    
    try:
        # Check permissions
        if not can_user_manage_machines(g.user):
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        data = request.get_json()
        machine_id = data.get('machine_id')
        
        # Get machine
        cursor = db.execute('SELECT * FROM machines WHERE id = ?', (machine_id,))
        machine = cursor.fetchone()
        
        if not machine:
            return jsonify({'success': False, 'message': 'Maschine nicht gefunden'}), 404
        
        # Check if machine is used in any jobs
        cursor = db.execute('SELECT COUNT(*) as count FROM jobs WHERE machine_used = ?', (machine_id,))
        usage_count = cursor.fetchone()['count']
        
        if usage_count > 0:
            return jsonify({
                'success': False, 
                'message': f'Maschine kann nicht gelöscht werden. Sie wird in {usage_count} Einsatz/Einsätzen verwendet.'
            }), 400
        
        # Delete machine
        db.execute('DELETE FROM machines WHERE id = ?', (machine_id,))
        db.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400