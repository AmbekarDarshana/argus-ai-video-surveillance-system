from flask import Blueprint, render_template, request, current_app, redirect, url_for, flash, jsonify, session
from models.anomaly import get_anomalies, get_anomaly_by_id
from services.notification_service import send_alert
from anomaly_engine.detector import process_video
from models.feedback import add_feedback

bp = Blueprint('anomaly', __name__)

@bp.route('/event_logs')
def event_logs():
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    role = session.get('role')
    user_id = session.get('user', {}).get('_id')

    # read filter/search parameters
    anomaly_type = request.args.get('type') or None
    start_dt = request.args.get('start')
    end_dt = request.args.get('end')
    camera = request.args.get('camera')

    # convert dates to datetime if present
    from datetime import datetime
    start_obj = datetime.fromisoformat(start_dt) if start_dt else None
    end_obj = datetime.fromisoformat(end_dt) if end_dt else None

    # determine base filters (tenant scoping)
    kwargs = {}
    if role != 'admin':
        kwargs['owner_id'] = user_id
    # extra search filters
    if anomaly_type:
        kwargs['anomaly_type'] = anomaly_type
    if camera:
        kwargs['video_id'] = camera
    if start_obj or end_obj:
        kwargs['start_time'] = start_obj
        kwargs['end_time'] = end_obj

    anomalies = get_anomalies(current_app.db, **kwargs)

    # build video name map for display and camera selector
    video_map = {}
    video_query = {}
    if role != 'admin':
        video_query['owner_id'] = user_id
    vids = list(current_app.db.videos.find(video_query))
    for v in vids:
        vidstr = str(v['_id'])
        video_map[vidstr] = v.get('location', vidstr)

    return render_template('event_logs.html', anomalies=anomalies,
                           video_map=video_map,
                           filters={'type': anomaly_type, 'start': start_dt,
                                    'end': end_dt, 'camera': camera})

@bp.route('/trigger_process', methods=['POST'])
def trigger_process():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    videos = list(current_app.db.videos.find({}))
    if not videos:
        return jsonify({'error': 'No videos found'}), 404
    
    video = videos[0]
    try:
        anomalies = process_video(current_app.db, video['file_path'], video_id=str(video['_id']))
        for a in anomalies:
            send_alert(a)
        return jsonify({'status': f'✅ Found {len(anomalies)} anomalies using AI'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/feedback/<anomaly_id>')
def feedback_page(anomaly_id):
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    anomaly = get_anomaly_by_id(current_app.db, anomaly_id)
    if not anomaly:
        flash('❌ Anomaly not found', 'danger')
        return redirect(url_for('anomaly.event_logs'))
    return render_template('feedback.html', anomaly=anomaly)

@bp.route('/feedback/submit', methods=['POST'])
def submit_feedback():
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    add_feedback(current_app.db, dict(request.form))
    flash('✅ Feedback submitted!', 'success')
    return redirect(url_for('anomaly.event_logs'))
