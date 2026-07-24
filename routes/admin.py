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
# MOVED: camera management now lives entirely in routes/features.py
# (see features.manage_cameras / assign_camera / create_new_camera /
# toggle_camera_route / delete_camera_route). This file used to register
# its own /admin/cameras routes that used raw dict inserts instead of the
# models/camera.py functions - that collided with features.py's routes on
# the same URL, and one silently shadowed the other. features.py's version
# is now the single source of truth.
#
# If any templates still link to url_for('admin.config_panel'),
# url_for('admin.add_camera'), url_for('admin.assign_camera'),
# url_for('admin.toggle_camera', ...), or url_for('admin.delete_camera', ...)
# update them to the features.* equivalents:
#   admin.config_panel  -> features.manage_cameras
#   admin.add_camera    -> features.create_new_camera
#   admin.assign_camera -> features.assign_camera
#   admin.toggle_camera -> features.toggle_camera_route
#   admin.delete_camera -> features.delete_camera_route