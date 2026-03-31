# routes/video.py
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, current_app, session, send_file, abort, Response
)
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename
from models.video import (
    create_video, get_all_videos, update_video_status, get_video_by_id
)
from anomaly_engine.detector import process_video
from datetime import datetime
import os

bp = Blueprint('video', __name__)


def find_video_file(stored_path):
    """
    Find a video file on disk given a stored path.
    Searches all possible locations.
    """
    if not stored_path:
        return None

    root = current_app.root_path

    # If absolute path exists
    if os.path.isabs(stored_path) and os.path.isfile(stored_path):
        return stored_path

    # Clean path
    clean = stored_path.strip().replace('\\', '/')
    while clean.startswith('/'):
        clean = clean[1:]

    filename = os.path.basename(clean)

    # Search all possible locations
    candidates = [
        os.path.join(root, clean),
        os.path.join(root, 'uploads', filename),
        os.path.join(root, 'static', 'videos', filename),
        os.path.join(root, 'static', 'recordings', filename),
        os.path.join(os.getcwd(), clean),
        os.path.join(os.getcwd(), 'uploads', filename),
        os.path.join(os.getcwd(), 'static', 'videos', filename),
        os.path.join(os.getcwd(), 'static', 'recordings', filename),
    ]

    for path in candidates:
        normalized = os.path.normpath(path)
        if os.path.isfile(normalized):
            return normalized

    print(f"[find_video_file] NOT FOUND: '{stored_path}'")
    for p in candidates:
        print(f"  {'YES' if os.path.isfile(os.path.normpath(p)) else 'NO '}: {os.path.normpath(p)}")

    return None


# ---------------- VIDEO MANAGEMENT ----------------
@bp.route('/video_management')
def video_management():
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    role = session.get('role')
    user_id = session.get('user', {}).get('_id')

    videos = (get_all_videos(current_app.db)
              if role == 'admin'
              else get_all_videos(current_app.db, owner_id=user_id))

    anomalies = list(current_app.db.anomalies.find({}))
    return render_template('video_management.html', videos=videos, anomalies=anomalies)


# ---------------- ADD VIDEO ----------------
@bp.route('/add_video', methods=['POST'])
def add_video():
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    file = request.files.get('file')
    location = request.form.get('location')
    resolution = request.form.get('resolution')

    if not file or file.filename == "":
        flash("No file selected", "warning")
        return redirect(url_for("video.video_management"))

    filename = secure_filename(file.filename)
    upload_dir = os.path.join(current_app.root_path, 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, filename)
    file.save(save_path)

    rel_path = 'uploads/' + filename

    video_doc = {
        "location": location,
        "resolution": resolution,
        "file_path": rel_path,
        "owner_id": session["user"]["_id"],
        "status": "uploaded",
        "created_at": datetime.now()
    }

    current_app.db.videos.insert_one(video_doc)
    flash("Video uploaded! Click 'Process' to analyze.", "success")
    return redirect(url_for("video.video_management"))


# ---------------- PROCESS ROUTES ----------------
@bp.route('/process_video/<video_id>', methods=['POST'])
def process_video_route(video_id):
    return _run_processing(video_id)


@bp.route('/reprocess/<video_id>', methods=['POST'])
def reprocess_video_route(video_id):
    current_app.db.anomalies.delete_many({'video_id': str(video_id)})
    flash('Old logs cleared. Restarting AI...', 'info')
    return _run_processing(video_id)


@bp.route('/delete/<video_id>')
def delete_video(video_id):
    if 'user' not in session:
        return redirect(url_for('auth.login'))
    try:
        current_app.db.videos.delete_one({'_id': ObjectId(video_id)})
        current_app.db.anomalies.delete_many({'video_id': str(video_id)})
        flash('Video and detection logs deleted.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('video.video_management'))


# ---------------- STREAM VIDEO ----------------
@bp.route('/stream/<video_id>')
def stream_video(video_id):
    """Serve a video file with range request support for seeking."""
    try:
        try:
            query_id = ObjectId(video_id)
        except Exception:
            query_id = video_id

        video = current_app.db.videos.find_one({'_id': query_id})
        if not video:
            print(f"[STREAM] Video not in DB: {video_id}")
            abort(404, "Video not found in database")

        stored_path = video.get('file_path', '')
        print(f"[STREAM] DB path: {stored_path}")

        abs_path = find_video_file(stored_path)
        if abs_path is None:
            # List all files for debugging
            print("[STREAM] === ALL VIDEO FILES ===")
            for folder in ['uploads', 'static/videos', 'static/recordings']:
                full = os.path.join(current_app.root_path, folder)
                if os.path.isdir(full):
                    print(f"  {folder}/: {os.listdir(full)}")
            abort(404, f"File not found: {stored_path}")

        file_size = os.path.getsize(abs_path)
        print(f"[STREAM] Serving: {abs_path} ({file_size} bytes)")

        # Detect MIME type
        ext = os.path.splitext(abs_path)[1].lower()
        mime_map = {
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.webm': 'video/webm',
            '.mkv': 'video/x-matroska',
            '.mov': 'video/quicktime',
        }
        mimetype = mime_map.get(ext, 'video/mp4')

        # Handle Range requests for video seeking
        range_header = request.headers.get('Range')

        if range_header:
            byte_start = 0
            byte_end = file_size - 1

            range_match = range_header.replace('bytes=', '').split('-')
            if range_match[0]:
                byte_start = int(range_match[0])
            if len(range_match) > 1 and range_match[1]:
                byte_end = int(range_match[1])

            content_length = byte_end - byte_start + 1

            def generate_chunks():
                with open(abs_path, 'rb') as f:
                    f.seek(byte_start)
                    remaining = content_length
                    while remaining > 0:
                        chunk = min(8192, remaining)
                        data = f.read(chunk)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            resp = Response(
                generate_chunks(),
                status=206,
                mimetype=mimetype,
                direct_passthrough=True
            )
            resp.headers['Content-Range'] = f'bytes {byte_start}-{byte_end}/{file_size}'
            resp.headers['Accept-Ranges'] = 'bytes'
            resp.headers['Content-Length'] = content_length
            return resp

        return send_file(abs_path, mimetype=mimetype)

    except Exception as e:
        print(f"[STREAM ERROR] {e}")
        import traceback
        traceback.print_exc()
        abort(404, str(e))


# ---------------- INTERNAL HELPER ----------------
def _run_processing(video_id):
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    video = get_video_by_id(current_app.db, video_id)
    if not video:
        flash('Video not found', 'danger')
        return redirect(url_for('video.video_management'))

    if session.get('role') != 'admin':
        user_id = session.get('user', {}).get('_id')
        if video.get('owner_id') != user_id:
            flash('Not authorized', 'danger')
            return redirect(url_for('video.video_management'))

    try:
        update_video_status(current_app.db, video_id, 'processing')

        abs_path = find_video_file(video['file_path'])
        if abs_path is None:
            raise ValueError(f"Video file not found: {video['file_path']}")

        print(f"[PROCESS] Processing: {abs_path}")
        anomalies = process_video(current_app.db, abs_path, video_id=str(video['_id']))
        update_video_status(current_app.db, video_id, 'processed', datetime.now())

        if anomalies:
            flash(f'AI found {len(anomalies)} anomalies.', 'success')
        else:
            flash('Video is safe (0 anomalies).', 'success')

    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        update_video_status(current_app.db, video_id, 'error')
        import traceback
        traceback.print_exc()

    return redirect(url_for('video.video_management'))