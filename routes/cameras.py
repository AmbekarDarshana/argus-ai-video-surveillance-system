# routes/cameras.py
"""
Self-service camera management for regular users.
Any logged-in user can add their own camera (RTSP URL) and it starts
being watched automatically by the AI - no admin approval needed.
This is the "home user sets up their own camera" flow.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, Response, jsonify
from bson import ObjectId
from datetime import datetime
from models.camera import create_camera, get_client_cameras, delete_camera as model_delete_camera
from services.live_camera_service import live_camera_manager

bp = Blueprint('cameras', __name__, url_prefix='/my-cameras')


@bp.route('/')
def my_cameras():
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user']['_id']
    cameras = get_client_cameras(current_app.db, user_id)

    # attach live running status for each camera so the template can show
    # "Live" vs "Offline" and only render the MJPEG <img> for running ones
    for cam in cameras:
        cam['is_live'] = live_camera_manager.is_running(cam['_id'])

    return render_template('my_cameras.html', cameras=cameras)


@bp.route('/add', methods=['POST'])
def add_camera():
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user']['_id']
    name = request.form.get('name', 'My Camera').strip() or 'My Camera'
    location = request.form.get('location', 'Home').strip() or 'Home'
    camera_type = request.form.get('camera_type', 'rtsp')

    if camera_type == 'webcam':
        # No real IP camera needed - use the machine's built-in/USB webcam
        # (device index 0) as the video source for testing the pipeline.
        rtsp_url = '0'
    else:
        rtsp_url = request.form.get('rtsp_url', '').strip()
        if not rtsp_url:
            flash("Please provide your camera's RTSP URL.", 'danger')
            return redirect(url_for('cameras.my_cameras'))

    camera_data = {
        'name': name,
        'location': location,
        'owner_id': user_id,
        'rtsp_url': rtsp_url,
        'resolution': 'auto',
        'status': 'active'
    }

    try:
        camera = create_camera(current_app.db, camera_data)
        # Start continuous AI detection on this camera immediately -
        # no manual "process" step, this is the whole point of the
        # self-service model.
        started = live_camera_manager.start_camera(
            camera_id=camera['_id'],
            rtsp_url=rtsp_url,
            owner_id=user_id
        )
        if started:
            flash(f'✅ "{name}" added and is now being watched by the AI!', 'success')
        else:
            flash(
                f'Camera "{name}" was saved, but the stream could not be reached yet. '
                f'Double check the RTSP URL - it will keep retrying in the background.',
                'warning'
            )
    except Exception as e:
        flash(f'❌ Error adding camera: {str(e)}', 'danger')

    return redirect(url_for('cameras.my_cameras'))


@bp.route('/<camera_id>/remove', methods=['POST'])
def remove_camera(camera_id):
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user']['_id']

    try:
        # Only allow a user to remove their own camera
        cam = current_app.db.cameras.find_one({'_id': ObjectId(camera_id)})
        if not cam or cam.get('owner_id') != user_id:
            flash('❌ Not authorized to remove this camera', 'danger')
            return redirect(url_for('cameras.my_cameras'))

        live_camera_manager.stop_camera(camera_id)
        model_delete_camera(current_app.db, camera_id)
        flash('Camera removed.', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'danger')

    return redirect(url_for('cameras.my_cameras'))


@bp.route('/<camera_id>/feed')
def camera_feed(camera_id):
    """MJPEG live view for a single camera this user owns."""
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    def generate():
        import cv2
        import time
        while live_camera_manager.is_running(camera_id):
            frame = live_camera_manager.get_latest_frame(camera_id)
            if frame is not None:
                ok, buffer = cv2.imencode('.jpg', frame)
                if ok:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.1)

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


# ============= IN-APP NOTIFICATIONS =============
# Simple polling endpoint - the browser calls this every few seconds
# (see base.html) and shows a toast for anything new. No external push
# service needed, works anywhere the app is deployed.

@bp.route('/notifications/poll')
def poll_notifications():
    """Return anomalies detected on this user's cameras since a given time."""
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    user_id = session['user']['_id']
    since_str = request.args.get('since')

    query = {'owner_id': user_id}
    if since_str:
        try:
            since_dt = datetime.fromisoformat(since_str)
            query['created_at'] = {'$gt': since_dt}
        except ValueError:
            pass
    else:
        # first poll of the session - don't dump the entire history as
        # "new" notifications, just start watching from now
        query['created_at'] = {'$gt': datetime.now()}

    anomalies = list(
        current_app.db.anomalies.find(query).sort('created_at', -1).limit(10)
    )
    for a in anomalies:
        a['_id'] = str(a['_id'])
        if a.get('created_at'):
            a['created_at'] = a['created_at'].isoformat()

    return jsonify({'anomalies': anomalies, 'server_time': datetime.now().isoformat()})