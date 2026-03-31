from flask import Blueprint, jsonify, current_app, session
from models.anomaly import get_anomalies
from models.video import get_all_videos

bp = Blueprint('api', __name__)

@bp.route('/anomalies')
def api_anomalies():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    role = session.get('role')
    user_id = session.get('user', {}).get('_id')
    if role == 'admin':
        anomalies = get_anomalies(current_app.db)
    else:
        anomalies = get_anomalies(current_app.db, owner_id=user_id)
    return jsonify(anomalies)

@bp.route('/videos')
def api_videos():
    if 'user' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    role = session.get('role')
    user_id = session.get('user', {}).get('_id')
    if role == 'admin':
        videos = get_all_videos(current_app.db)
    else:
        videos = get_all_videos(current_app.db, owner_id=user_id)
    return jsonify(videos)
