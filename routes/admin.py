# routes/admin.py

from flask import Blueprint, render_template, current_app, redirect, url_for, flash, session, request
from bson import ObjectId
from datetime import datetime

bp = Blueprint('admin', __name__, url_prefix='/admin')


def list_users(db):
    users = list(db.users.find({}))
    for u in users:
        u['_id'] = str(u['_id'])
    return users


def set_user_disabled(db, user_id, disabled=True):
    db.users.update_one(
        {'_id': ObjectId(user_id)},
        {'$set': {'disabled': disabled}}
    )


# ============= USER MANAGEMENT =============

@bp.route('/users')
def manage_users():
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    users = list_users(current_app.db)
    return render_template('admin_users.html', users=users, user=session.get('user'))


@bp.route('/users/toggle/<user_id>')
def toggle_user(user_id):
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    try:
        should_disable = request.args.get('disable', '1') == '1'
        set_user_disabled(current_app.db, user_id, disabled=should_disable)

        if should_disable:
            flash('User disabled successfully', 'warning')
        else:
            flash('User enabled successfully', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')

    return redirect(url_for('admin.manage_users'))


# ============= ANALYTICS =============

@bp.route('/stats')
def global_stats():
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    db = current_app.db
    total_videos = db.videos.count_documents({})
    total_anomalies = db.anomalies.count_documents({})

    per_client = list(db.anomalies.aggregate([
        {'$group': {'_id': '$owner_id', 'count': {'$sum': 1}}}
    ]))

    return render_template(
        'admin_stats.html',
        total_videos=total_videos,
        total_anomalies=total_anomalies,
        per_client=per_client,
        user=session.get('user')
    )


# ============= SETTINGS =============

@bp.route('/config', methods=['GET', 'POST'])
def config():
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    db = current_app.db
    settings = db.settings.find_one({}) or {}

    if request.method == 'POST':
        crowd_thresh = float(request.form.get('crowd_threshold') or settings.get('crowd_threshold', 0.8))
        db.settings.update_one({}, {'$set': {'crowd_threshold': crowd_thresh}}, upsert=True)
        flash('Settings updated', 'success')
        settings['crowd_threshold'] = crowd_thresh

    return render_template('admin_config.html', settings=settings, user=session.get('user'))


# ============= CAMERA MANAGEMENT =============

@bp.route('/cameras')
def config_panel():
    """Admin camera management page."""
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    db = current_app.db

    # Get all cameras from cameras collection
    cameras = list(db.cameras.find({}))
    for c in cameras:
        c['_id'] = str(c['_id'])
        # Lookup owner email
        if c.get('owner_id'):
            try:
                owner = db.users.find_one({'_id': ObjectId(c['owner_id'])})
                c['owner_email'] = owner.get('email', '') if owner else ''
            except:
                c['owner_email'] = ''

    # Get all users for assignment dropdown
    users = list(db.users.find({}, {'email': 1, 'role': 1, '_id': 1}))
    for u in users:
        u['_id'] = str(u['_id'])

    return render_template(
        'admin_cameras.html',
        cameras=cameras,
        users=users,
        user=session.get('user')
    )


@bp.route('/cameras/add', methods=['POST'])
def add_camera():
    """Add a new camera."""
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    db = current_app.db

    camera_data = {
        'name': request.form.get('name', 'New Camera'),
        'location': request.form.get('location', 'Unknown'),
        'resolution': request.form.get('resolution', '1920x1080'),
        'rtsp_url': request.form.get('rtsp_url', ''),
        'owner_id': request.form.get('owner_id') or None,
        'status': 'active',
        'created_at': datetime.now(),
        'updated_at': datetime.now()
    }

    db.cameras.insert_one(camera_data)
    flash(f'Camera "{camera_data["name"]}" added successfully!', 'success')

    return redirect(url_for('admin.config_panel'))


@bp.route('/cameras/assign', methods=['POST'])
def assign_camera():
    """Assign a camera to a client."""
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    db = current_app.db
    camera_id = request.form.get('camera_id')
    owner_id = request.form.get('owner_id')

    try:
        update_data = {'owner_id': owner_id if owner_id else None, 'updated_at': datetime.now()}
        db.cameras.update_one({'_id': ObjectId(camera_id)}, {'$set': update_data})

        if owner_id:
            owner = db.users.find_one({'_id': ObjectId(owner_id)})
            owner_email = owner.get('email', 'Unknown') if owner else 'Unknown'
            flash(f'Camera assigned to {owner_email}!', 'success')
        else:
            flash('Camera unassigned.', 'info')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('admin.config_panel'))


@bp.route('/cameras/toggle/<camera_id>', methods=['POST'])
def toggle_camera(camera_id):
    """Toggle camera active/offline status."""
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    db = current_app.db
    new_status = request.form.get('status', 'active')

    try:
        db.cameras.update_one(
            {'_id': ObjectId(camera_id)},
            {'$set': {'status': new_status, 'updated_at': datetime.now()}}
        )
        flash(f'Camera set to {new_status}', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('admin.config_panel'))


@bp.route('/cameras/delete/<camera_id>', methods=['POST'])
def delete_camera(camera_id):
    """Delete a camera."""
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    db = current_app.db

    try:
        db.cameras.delete_one({'_id': ObjectId(camera_id)})
        flash('Camera deleted.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('admin.config_panel'))