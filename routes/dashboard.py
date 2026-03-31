# routes/dashboard.py

from flask import Blueprint, render_template, current_app, redirect, url_for, session, request, flash
from models.video import get_all_videos, get_video_by_id
from datetime import datetime
from collections import defaultdict

bp = Blueprint('main', __name__)


@bp.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    user = session.get('user', {})
    role = session.get('role')
    user_id = user.get('_id')
    db = current_app.db

    # ========== GET VIDEOS ==========
    # Admin sees all videos
    # Client sees only videos assigned to them OR from their cameras
    if role == 'admin':
        videos = list(db.videos.find({}))
    else:
        # Get client's assigned cameras first
        client_cameras = list(db.cameras.find({'owner_id': user_id}))
        camera_ids = [str(c['_id']) for c in client_cameras]
        camera_names = [c.get('name', c.get('location', '')) for c in client_cameras]

        # Get videos that belong to this client OR linked to their cameras
        videos = list(db.videos.find({
            '$or': [
                {'owner_id': user_id},
                {'camera_id': {'$in': camera_ids}}
            ]
        }))

    # Convert _id to string
    for v in videos:
        v['_id'] = str(v['_id'])

    video_map = {v['_id']: v.get('location', 'Camera') for v in videos}

    # ========== GET CAMERAS FOR CLIENT ==========
    # Client also sees their assigned cameras (even without videos)
    assigned_cameras = []
    if role != 'admin':
        assigned_cameras = list(db.cameras.find({'owner_id': user_id}))
        for c in assigned_cameras:
            c['_id'] = str(c['_id'])

    # ========== SELECTED VIDEO ==========
    selected_video_id = request.args.get('video_id')
    current_video = None
    video_url = None

    if selected_video_id:
        current_video = get_video_by_id(db, selected_video_id)
        if current_video:
            # Security: client can only view their own videos
            if role != 'admin' and current_video.get('owner_id') != user_id:
                current_video = None
            else:
                video_url = url_for('video.stream_video', video_id=selected_video_id)

    # ========== ANOMALIES ==========
    query = {'$or': [{'is_live': {'$exists': False}}, {'is_live': False}]}

    if selected_video_id:
        query['video_id'] = selected_video_id
    elif role != 'admin':
        # Client only sees their own anomalies
        video_ids = [v['_id'] for v in videos]
        if video_ids:
            query['video_id'] = {'$in': video_ids}
        else:
            query['video_id'] = 'none'  # No videos = no anomalies

    filter_type = request.args.get('type')
    if filter_type:
        query['anomaly_type'] = filter_type

    anomalies = list(db.anomalies.find(query).sort('frame_timestamp', -1))
    for a in anomalies:
        a['_id'] = str(a['_id'])
        if 'video_id' in a:
            a['video_id'] = str(a['video_id'])

    # ========== CHART DATA ==========
    daily_counts = defaultdict(int)
    for a in anomalies:
        ts = a.get('timestamp') or a.get('created_at') or a.get('detection_time')
        if ts:
            if isinstance(ts, str):
                date_key = ts.split('T')[0]
            else:
                date_key = ts.strftime('%Y-%m-%d')
            daily_counts[date_key] += 1

    chart_data = [{'day': k, 'count': v} for k, v in daily_counts.items()]

    summary = {
        'today': len(anomalies),
        'week': len(anomalies),
        'cameras': len(videos) + len(assigned_cameras)
    }

    return render_template(
        'dashboard.html',
        videos=videos,
        video=current_video,
        video_url=video_url,
        anomalies=anomalies,
        video_map=video_map,
        assigned_cameras=assigned_cameras,
        summary=summary,
        chart_data=chart_data,
        filters={'type': filter_type},
        role=role,
        user=user
    )


@bp.route('/subscription')
def subscription():
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    return render_template('subscription.html', user=session.get('user'))


@bp.route('/support', methods=['GET', 'POST'])
def support():
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    db = current_app.db

    if request.method == 'POST':
        subject = request.form.get('subject')
        message = request.form.get('message')
        ticket = {
            'user_id': session['user']['_id'],
            'user_email': session['user']['email'],
            'subject': subject,
            'message': message,
            'status': 'open',
            'created_at': datetime.now()
        }
        db.support.insert_one(ticket)
        flash('Ticket submitted!', 'success')
        return redirect(url_for('main.support'))

    my_tickets = list(db.support.find({'user_id': session['user']['_id']}).sort('created_at', -1))
    return render_template('support.html', tickets=my_tickets, user=session.get('user'))