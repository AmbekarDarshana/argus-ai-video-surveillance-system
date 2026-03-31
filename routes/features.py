"""Routes for export, alerts, and client features."""
# At the top of routes/features.py, ADD this import:
from models.alert_rule import get_alert_rules, create_alert_rule, delete_alert_rule
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file, jsonify, current_app
from models.anomaly import get_anomalies
from models.video import get_all_videos
from models.api_key import (
    get_api_keys,
    create_api_key as model_create_api_key,
    delete_api_key as model_delete_api_key,
    get_client_usage
)

from models.camera import (
    get_client_cameras,
    create_camera as model_create_camera,
    update_camera,
    delete_camera
)
from services.export_service import export_anomalies_csv, export_anomalies_pdf, export_analytics_summary
from datetime import datetime, timedelta
import io

bp = Blueprint('features', __name__)


# ============= EXPORT ROUTES =============

@bp.route('/export/anomalies')
def export_anomalies():
    """Export anomalies to CSV or PDF."""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    role = session.get('role')
    user_id = session.get('user', {}).get('_id')
    format_type = request.args.get('format', 'csv')
    
    # Get anomalies (scoped by owner)
    if role == 'admin':
        anomalies = get_anomalies(current_app.db)
    else:
        anomalies = get_anomalies(current_app.db, owner_id=user_id)
    
    # Get video map
    if role == 'admin':
        videos = get_all_videos(current_app.db)
    else:
        videos = get_all_videos(current_app.db, owner_id=user_id)
    video_map = {v['_id']: v.get('location', v['_id']) for v in videos}
    
    if format_type == 'pdf':
        try:
            pdf_bytes = export_anomalies_pdf(anomalies, video_map, title="Anomaly Detection Report")
            return send_file(
                io.BytesIO(pdf_bytes),
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f"anomalies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )
        except Exception as e:
            flash(f"❌ PDF export failed: {str(e)}", 'danger')
            return redirect(url_for('anomaly.event_logs'))
    else:  # CSV
        csv_data = export_anomalies_csv(anomalies, video_map)
        return send_file(
            io.StringIO(csv_data),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"anomalies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )


# ============= ALERT RULES ROUTES =============

@bp.route('/alerts')
def view_alerts():
    """View alert rules for current user."""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user', {}).get('_id')
    rules = get_alert_rules(current_app.db, owner_id=user_id)
    return render_template('alerts.html', rules=rules)


@bp.route('/alerts/create', methods=['POST'])
def create_alert():
    """Create a new alert rule."""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user', {}).get('_id')
    rule_data = {
        'name': request.form.get('name'),
        'owner_id': user_id,
        'trigger_type': request.form.get('trigger_type'),
        'condition': {
            'anomaly_type': request.form.get('anomaly_type'),
            'anomalies_per_hour': int(request.form.get('threshold', 5))
        },
        'action': {
            'type': 'email',
            'email': request.form.get('email')
        },
        'enabled': request.form.get('enabled') == 'on'
    }
    
    try:
        create_alert_rule(current_app.db, rule_data)
        flash('✅ Alert rule created!', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'danger')
    
    return redirect(url_for('features.view_alerts'))


@bp.route('/alerts/<alert_id>/delete', methods=['POST'])
def delete_alert(alert_id):
    """Delete an alert rule."""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    try:
        delete_alert_rule(current_app.db, alert_id)
        flash('✅ Alert rule deleted', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'danger')
    
    return redirect(url_for('features.view_alerts'))


# ============= CLIENT USAGE DASHBOARD =============

@bp.route('/usage')
def client_usage():
    """Show client usage statistics."""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user', {}).get('_id')
    usage = get_client_usage(current_app.db, user_id, days=30)
    keys = get_api_keys(current_app.db, user_id)
    
    return render_template('usage_dashboard.html', usage=usage, api_keys=keys)


# ============= API KEY MANAGEMENT =============

@bp.route('/api-keys')
def api_keys():
    """Manage API keys."""
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user', {}).get('_id')
    keys = get_api_keys(current_app.db, user_id)
    return render_template('api_keys.html', keys=keys)


@bp.route('/api-keys/create', methods=['POST'])
def create_new_api_key():   # RENAMED route function
    """Create a new API key."""
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    user_id = session.get('user', {}).get('_id')
    name = request.form.get('name', 'New Key')

    try:
        # FIXED: Call the MODEL function, not itself
        key = model_create_api_key(current_app.db, user_id, name)
        flash(f'API key created! Save it: {key["key"]}', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('features.api_keys'))


@bp.route('/api-keys/<key_id>/delete', methods=['POST'])
def remove_api_key(key_id):   # RENAMED route function
    """Delete an API key."""
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    try:
        # FIXED: Call the MODEL function
        model_delete_api_key(current_app.db, key_id)
        flash('API key deleted', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')

    return redirect(url_for('features.api_keys'))


# ============= CAMERA MANAGEMENT (ADMIN) =============

@bp.route('/admin/cameras')
def manage_cameras():
    """Admin: manage camera assignments."""
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))
    
    cameras = list(current_app.db.cameras.find())
    users = list(current_app.db.users.find({}, {'email': 1, '_id': 1}))
    
    for c in cameras:
        c['_id'] = str(c['_id'])
    for u in users:
        u['_id'] = str(u['_id'])
    
    return render_template('admin_cameras.html', cameras=cameras, users=users)


@bp.route('/admin/cameras/assign', methods=['POST'])
def assign_camera():
    """Assign a camera to a client."""
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))
    
    camera_id = request.form.get('camera_id')
    owner_id = request.form.get('owner_id')
    
    try:
        model_update_camera(current_app.db, camera_id, {'owner_id': owner_id})
        flash('✅ Camera assigned!', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'danger')
    
    return redirect(url_for('features.manage_cameras'))


@bp.route('/admin/cameras/create', methods=['POST'])
def create_new_camera():
    """Create a new camera."""
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))
    
    camera_data = {
        'name': request.form.get('name'),
        'location': request.form.get('location'),
        'owner_id': request.form.get('owner_id'),
        'resolution': request.form.get('resolution', '1920x1080'),
        'status': 'active'
    }
    
    try:
        create_camera(current_app.db, camera_data)
        flash('✅ Camera created!', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'danger')
    
    return redirect(url_for('features.manage_cameras'))
