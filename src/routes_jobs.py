from flask import render_template, request, jsonify, session, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime
from models import db, Job, User
from functools import wraps

def role_required(*roles):
    """Decorator to check if user has required role"""
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            
            user_roles = current_user.role.split(',') if current_user.role else []
            if not any(role in user_roles for role in roles):
                return "Keine Berechtigung", 403
            return f(*args, **kwargs)
        return decorated_function
    return wrapper


def get_user_villages(user):
    """Get list of villages the user has access to"""
    if not user.villages:
        return []
    return [v.strip() for v in user.villages.split(',')]


def get_available_wegewarten(user):
    """Get list of Wegewarten the user can see/manage"""
    user_roles = user.role.split(',') if user.role else []
    user_villages = get_user_villages(user)
    
    if 'admin' in user_roles:
        # Admin sees all Wegewarten
        return User.query.filter(User.role.contains('wegewart')).all()
    elif 'ortsvorsteher' in user_roles:
        # Ortsvorsteher sees all Wegewarten in their villages
        wegewarten = []
        for village in user_villages:
            wegewarten.extend(
                User.query.filter(
                    User.role.contains('wegewart'),
                    User.villages.contains(village)
                ).all()
            )
        return list(set(wegewarten))  # Remove duplicates
    else:
        # Regular Wegewart only sees themselves
        return [user]


@app.route('/jobs')
@login_required
def jobs():
    """Display jobs based on user role and filters"""
    user_roles = current_user.role.split(',') if current_user.role else []
    user_villages = get_user_villages(current_user)
    
    # Base query
    query = Job.query
    
    # Role-based filtering
    if 'admin' in user_roles:
        # Admin sees everything (no additional filter)
        pass
    elif 'ortsvorsteher' in user_roles:
        # Ortsvorsteher sees jobs from their villages
        query = query.filter(Job.village.in_(user_villages))
    else:
        # Regular Wegewart only sees their own jobs
        query = query.filter(Job.wegewart_id == current_user.id)
    
    # Apply filters from request
    wegewart_filter = request.args.get('wegewart_filter')
    if wegewart_filter and 'admin' in user_roles or 'ortsvorsteher' in user_roles:
        query = query.filter(Job.wegewart_id == wegewart_filter)
    
    date_from = request.args.get('date_from')
    if date_from:
        query = query.filter(Job.date >= datetime.strptime(date_from, '%Y-%m-%d').date())
    
    date_to = request.args.get('date_to')
    if date_to:
        query = query.filter(Job.date <= datetime.strptime(date_to, '%Y-%m-%d').date())
    
    village_filter = request.args.get('village_filter')
    if village_filter:
        query = query.filter(Job.village == village_filter)
    
    # Order by date descending
    jobs_list = query.order_by(Job.date.desc()).all()
    
    # Prepare jobs with wegewart names
    jobs_with_names = []
    for job in jobs_list:
        job_dict = {
            'id': job.id,
            'date': job.date,
            'wegewart_id': job.wegewart_id,
            'wegewart_name': job.wegewart.name if job.wegewart else 'Unbekannt',
            'village': job.village,
            'description': job.description,
            'hours': job.hours,
            'status': job.status,
            'approved': job.approved
        }
        jobs_with_names.append(job_dict)
    
    # Get available Wegewarten for filters and dropdowns
    available_wegewarten = get_available_wegewarten(current_user)
    
    # Determine user role for template (highest privilege)
    if 'admin' in user_roles:
        user_role = 'admin'
    elif 'ortsvorsteher' in user_roles:
        user_role = 'ortsvorsteher'
    else:
        user_role = 'wegewart'
    
    return render_template('jobs.html',
                         jobs=jobs_with_names,
                         user_role=user_role,
                         user_villages=user_villages,
                         available_wegewarten=available_wegewarten,
                         current_user_id=current_user.id,
                         current_user_name=current_user.name)


@app.route('/jobs/create', methods=['POST'])
@login_required
def create_job():
    """Create a new job entry"""
    try:
        data = request.get_json()
        
        # Check permissions
        user_roles = current_user.role.split(',') if current_user.role else []
        wegewart_id = data.get('wegewart_id', current_user.id)
        
        # Only admin and ortsvorsteher can create jobs for others
        if wegewart_id != current_user.id and not any(r in user_roles for r in ['admin', 'ortsvorsteher']):
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        # Create new job
        new_job = Job(
            wegewart_id=int(wegewart_id),
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            village=data['village'],
            description=data['description'],
            hours=float(data['hours']),
            status=data.get('status', 'eingereicht'),
            approved=False,
            created_at=datetime.now()
        )
        
        db.session.add(new_job)
        db.session.commit()
        
        return jsonify({'success': True, 'job_id': new_job.id})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/jobs/update', methods=['POST'])
@login_required
def update_job():
    """Update an existing job"""
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        
        job = Job.query.get_or_404(job_id)
        
        # Check permissions
        user_roles = current_user.role.split(',') if current_user.role else []
        user_villages = get_user_villages(current_user)
        
        # Check if user can edit this job
        can_edit = False
        if 'admin' in user_roles:
            can_edit = True
        elif 'ortsvorsteher' in user_roles and job.village in user_villages:
            can_edit = True
        elif job.wegewart_id == current_user.id:
            can_edit = True
        
        if not can_edit:
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        # Update fields
        if 'date' in data:
            job.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        if 'wegewart_id' in data and ('admin' in user_roles or 'ortsvorsteher' in user_roles):
            job.wegewart_id = int(data['wegewart_id'])
        if 'village' in data:
            job.village = data['village']
        if 'description' in data:
            job.description = data['description']
        if 'hours' in data:
            job.hours = float(data['hours'])
        if 'status' in data:
            job.status = data['status']
        
        job.updated_at = datetime.now()
        
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/jobs/delete', methods=['POST'])
@login_required
def delete_job():
    """Delete a job"""
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        
        job = Job.query.get_or_404(job_id)
        
        # Check permissions
        user_roles = current_user.role.split(',') if current_user.role else []
        user_villages = get_user_villages(current_user)
        
        # Check if user can delete this job
        can_delete = False
        if 'admin' in user_roles:
            can_delete = True
        elif 'ortsvorsteher' in user_roles and job.village in user_villages:
            can_delete = True
        elif job.wegewart_id == current_user.id and not job.approved:
            # Wegewart can only delete their own unapproved jobs
            can_delete = True
        
        if not can_delete:
            return jsonify({'success': False, 'message': 'Keine Berechtigung'}), 403
        
        db.session.delete(job)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/jobs/approve', methods=['POST'])
@role_required('admin', 'ortsvorsteher')
def approve_jobs():
    """Approve multiple jobs (batch approval)"""
    try:
        data = request.get_json()
        job_ids = data.get('job_ids', [])
        
        if not job_ids:
            return jsonify({'success': False, 'message': 'Keine Jobs ausgewählt'}), 400
        
        user_roles = current_user.role.split(',') if current_user.role else []
        user_villages = get_user_villages(current_user)
        
        approved_count = 0
        
        for job_id in job_ids:
            job = Job.query.get(job_id)
            if not job:
                continue
            
            # Check permissions
            can_approve = False
            if 'admin' in user_roles:
                can_approve = True
            elif 'ortsvorsteher' in user_roles and job.village in user_villages:
                can_approve = True
            
            if can_approve:
                job.approved = True
                job.status = 'freigegeben'
                job.approved_by = current_user.id
                job.approved_at = datetime.now()
                approved_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'{approved_count} Einsatz/Einsätze freigegeben'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400