from flask import Blueprint, render_template, current_app, session, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
from bson import ObjectId

bp = Blueprint('analytics', __name__)

@bp.route('/analytics')
def analytics():
    # 1. Security & Auth Check
    if 'user' not in session:
        flash('Please login to view analytics', 'warning')
        return redirect(url_for('auth.login'))
    
    if session.get('role') not in ['admin', 'operator']:
        flash('❌ Admin or operator access required', 'danger')
        return redirect(url_for('main.dashboard'))
    
    db = current_app.db
    
    try:
        # --- 2. OPTIMIZED DATA FETCHING (Using MongoDB Aggregation) ---

        # A. Get Total Counts (Instant)
        total_anomalies = db.anomalies.count_documents({})
        total_videos = db.videos.count_documents({})

        # B. Get Last 7 Days Trends (Aggregation)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        trend_pipeline = [
            {
                '$match': {
                    'detection_time': {'$gte': seven_days_ago}
                }
            },
            {
                '$group': {
                    '_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$detection_time'}},
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'_id': 1}}
        ]
        trend_results = list(db.anomalies.aggregate(trend_pipeline))
        
        # Fill in missing days with 0
        chart_data = []
        trend_dict = {item['_id']: item['count'] for item in trend_results}
        
        for i in range(6, -1, -1):
            date_str = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
            chart_data.append({
                'day': date_str, # Format: YYYY-MM-DD
                'count': trend_dict.get(date_str, 0)
            })

        # C. Get Anomalies by Type
        type_pipeline = [
            {'$group': {'_id': '$anomaly_type', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        type_results = list(db.anomalies.aggregate(type_pipeline))
        anomaly_types_data = [{'type': item['_id'], 'count': item['count']} for item in type_results]

        # D. Get Top Problematic Cameras
        video_pipeline = [
            {'$group': {'_id': '$video_id', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 5} # Top 5 only
        ]
        video_results = list(db.anomalies.aggregate(video_pipeline))
        
        video_data = []
        for v in video_results:
            # Fetch video name safely
            vid_info = db.videos.find_one({'_id': ObjectId(v['_id'])}) if ObjectId.is_valid(v['_id']) else None
            video_name = vid_info.get('location', f"Cam {str(v['_id'])[-4:]}") if vid_info else 'Unknown Camera'
            video_data.append({'video': video_name, 'count': v['count']})

        # E. Feedback Accuracy (Simplified)
        feedback_pipeline = [
            {'$group': {'_id': '$label', 'count': {'$sum': 1}}}
        ]
        # Assuming you have a 'feedback' collection
        feedback_results = list(db.feedback.aggregate(feedback_pipeline)) if 'feedback' in db.list_collection_names() else []
        feedback_map = {item['_id']: item['count'] for item in feedback_results}
        
        # --- 3. RENDER TEMPLATE ---
        return render_template('analytics.html', 
                             data={
                                 'chart_data': chart_data,
                                 'anomaly_types': anomaly_types_data,
                                 'video_data': video_data,
                                 'total_anomalies': total_anomalies,
                                 'total_videos': total_videos,
                                 'accuracy': _calculate_accuracy(feedback_map)
                             },
                             user=session.get('user'), # <--- Fixes Navbar "Guest" issue
                             role=session.get('role'))
    
    except Exception as e:
        print(f"❌ Analytics Error: {e}")
        import traceback
        traceback.print_exc()
        flash("Error loading analytics data", "danger")
        # Return empty data structure to prevent page crash
        return render_template('analytics.html', 
                             data={'chart_data': [], 'anomaly_types': [], 'video_data': [], 'total_anomalies': 0, 'total_videos': 0},
                             user=session.get('user'),
                             role=session.get('role'))

def _calculate_accuracy(feedback_map):
    """Helper to calculate accuracy %"""
    true_pos = feedback_map.get('True Positive', 0) + feedback_map.get('true_positive', 0)
    false_pos = feedback_map.get('False Alarm', 0) + feedback_map.get('false_alarm', 0)
    
    total = true_pos + false_pos
    if total == 0: 
        return 0.0
    return round((true_pos / total) * 100, 1)

# --- API ENDPOINTS (For AJAX charts if needed) ---

@bp.route('/api/analytics/summary')
def analytics_summary():
    if 'user' not in session: return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        db = current_app.db
        total_anomalies = db.anomalies.count_documents({})
        
        # Count today's anomalies
        start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_anomalies = db.anomalies.count_documents({'detection_time': {'$gte': start_of_day}})
        
        return jsonify({
            'total_anomalies': total_anomalies,
            'today_anomalies': today_anomalies,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500