# routes/live.py
"""
Live Camera Routes (Behavior Anomaly Enabled + VIDEO RECORDING)
Includes FFmpeg conversion for browser-playable videos.
"""
from flask import Blueprint, render_template, request, jsonify, Response, current_app, session
import cv2
import time
import threading
import os
import shutil
import subprocess
from datetime import datetime
from anomaly_engine.detector import get_detector, process_video
from config import Config
from bson import ObjectId
from models.video import create_video, get_video_by_id
from models.recording import (
    start_recording, stop_recording, update_recording_frame_count,
    add_anomaly_to_recording, mark_recording_error, get_all_recordings
)

live_bp = Blueprint('live', __name__, url_prefix='/live')


# ===================== FFMPEG CONVERTER =====================

def get_ffmpeg_path():
    """Get FFmpeg executable path. Tries imageio-ffmpeg first, then system."""
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.exists(path):
            return path
    except ImportError:
        pass

    # Try system ffmpeg
    import shutil as sh
    system_ffmpeg = sh.which('ffmpeg')
    if system_ffmpeg:
        return system_ffmpeg

    return None


def convert_to_browser_format(input_path):
    """Convert mp4v codec to h264 so browsers can play it."""
    ffmpeg_path = get_ffmpeg_path()

    if ffmpeg_path is None:
        print("[CONVERT] FFmpeg not found!")
        print("[CONVERT] Install it: pip install imageio-ffmpeg")
        return False

    output_path = input_path + '.tmp_web.mp4'

    try:
        cmd = [
            ffmpeg_path, '-y',
            '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-movflags', '+faststart',
            output_path
        ]
        print(f"[CONVERT] Converting: {input_path}")
        print(f"[CONVERT] Using: {ffmpeg_path}")

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=300
        )

        # Replace original with converted version
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            os.remove(input_path)
            os.rename(output_path, input_path)
            print(f"[CONVERT] Success! Browser-playable: {input_path}")
            return True
        else:
            print("[CONVERT] Output file is empty or missing")
            return False

    except subprocess.CalledProcessError as e:
        print(f"[CONVERT] FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False
    except Exception as e:
        print(f"[CONVERT] Error: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return False


# ===================== GLOBAL CAMERA STATE =====================

camera_state = {
    'cap': None,
    'is_running': False,
    'lock': threading.Lock(),
    'latest_detections': [],
    'latest_anomalies': [],
    # Recording state
    'is_recording': False,
    'video_writer': None,
    'recording_id': None,
    'recording_filename': None,
    'recording_frame_count': 0,
    'recording_lock': threading.Lock(),
}


# ===================== VIDEO STREAMING GENERATOR =====================

def generate_frames():
    """Video streaming generator function with Behavior Detection + Recording."""
    global camera_state

    # Load AI Models
    yolo, classifier = get_detector()

    frame_counter = 0
    prev_detections = []
    alert_cooldowns = {}
    last_db_update = time.time()

    while camera_state['is_running'] and camera_state['cap']:
        success, frame = camera_state['cap'].read()
        if not success:
            break

        # Resize for speed
        frame = cv2.resize(frame, (640, 480))
        frame_counter += 1
        current_time = time.time()

        # Write frame to video file if recording
        with camera_state['recording_lock']:
            if camera_state['is_recording'] and camera_state['video_writer'] is not None:
                try:
                    camera_state['video_writer'].write(frame)
                    camera_state['recording_frame_count'] += 1

                    # Update DB every 5 seconds
                    if (current_time - last_db_update) > 5.0:
                        try:
                            db = current_app.db
                            update_recording_frame_count(
                                db,
                                camera_state['recording_id'],
                                camera_state['recording_frame_count']
                            )
                            last_db_update = current_time
                        except Exception as e:
                            print(f"DB frame count update error: {e}")
                except Exception as e:
                    print(f"Video write error: {e}")

        # AI Processing every 3rd frame
        if frame_counter % 3 == 0:
            try:
                # Object Detection
                raw_detections = yolo.detect(frame)
                detections = [d for d in raw_detections if d.confidence > 0.40]

                # Behavior Classification
                anomalies = classifier.classify(detections, current_time, prev_detections)

                # Handle each anomaly
                valid_anomalies = []
                for anomaly in anomalies:
                    if anomaly.score < 0.60:
                        continue

                    last_alert = alert_cooldowns.get(anomaly.type, 0)
                    if (current_time - last_alert) < 5.0:
                        continue
                    alert_cooldowns[anomaly.type] = current_time

                    # Log to Database
                    try:
                        db = current_app.db
                        log_data = {
                            "video_id": "live_webcam_01",
                            "anomaly_type": anomaly.type,
                            "anomaly_score": round(anomaly.score, 2),
                            "frame_timestamp": current_time,
                            "description": f"Live Feed: {anomaly.description}",
                            "objects_detected": anomaly.objects,
                            "detection_count": len(detections),
                            "created_at": datetime.now(),
                            "is_live": True
                        }
                        result = db.anomalies.insert_one(log_data)
                        print(f"LOGGED TO DB: {anomaly.type}")

                        # Link anomaly to current recording
                        with camera_state['recording_lock']:
                            if camera_state['is_recording'] and camera_state['recording_id']:
                                try:
                                    add_anomaly_to_recording(
                                        db,
                                        camera_state['recording_id'],
                                        result.inserted_id
                                    )
                                except Exception as e:
                                    print(f"Error linking anomaly to recording: {e}")

                    except Exception as e:
                        print(f"DB Error: {e}")

                    valid_anomalies.append(anomaly)

                # Update state for drawing
                camera_state['latest_detections'] = detections
                camera_state['latest_anomalies'] = valid_anomalies
                prev_detections = detections

            except Exception as e:
                print(f"AI Error: {e}")

        # --- DRAWING ---
        annotated = frame.copy()

        # Draw object boxes
        for d in camera_state['latest_detections']:
            x, y, w, h = d.bbox
            color = (0, 255, 0)
            is_threat = False
            for anom in camera_state['latest_anomalies']:
                if d.label in anom.objects:
                    is_threat = True
                    break
            if is_threat:
                color = (0, 0, 255)

            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            cv2.putText(annotated, f"{d.label}", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # Draw behavior alert labels
        for i, anomaly in enumerate(camera_state['latest_anomalies']):
            text = f"ALERT: {anomaly.type.upper()}"
            cv2.rectangle(annotated, (5, 5 + (i * 35)), (350, 35 + (i * 35)), (0, 0, 255), -1)
            cv2.putText(annotated, text, (10, 28 + (i * 35)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Draw recording indicator
        with camera_state['recording_lock']:
            if camera_state['is_recording']:
                if int(current_time * 2) % 2 == 0:
                    cv2.circle(annotated, (620, 20), 8, (0, 0, 255), -1)
                cv2.putText(annotated, "REC", (590, 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                cv2.putText(annotated,
                            f"Frames: {camera_state['recording_frame_count']}",
                            (10, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        # Encode to JPEG
        ret, buffer = cv2.imencode('.jpg', annotated)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


# ===================== PAGE ROUTES =====================

@live_bp.route('/dashboard', methods=['GET'])
def live_dashboard():
    dummy_camera = {
        '_id': 'webcam_0',
        'name': 'Laptop Webcam (Live)',
        'location': 'Local System'
    }

    recordings = []
    try:
        db = current_app.db
        recordings = get_all_recordings(db, camera_id='webcam_0', limit=10)
    except Exception as e:
        print(f"Error fetching recordings: {e}")

    return render_template('live_cameras.html',
                           camera=dummy_camera,
                           recordings=recordings,
                           is_recording=camera_state['is_recording'])


@live_bp.route('/video_feed')
def video_feed():
    """Route that the HTML <img> tag links to."""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


# ===================== CAMERA CONTROL API =====================

@live_bp.route('/api/start', methods=['POST'])
def api_start_camera():
    global camera_state
    if not camera_state['is_running']:
        camera_state['cap'] = cv2.VideoCapture(0)
        camera_state['is_running'] = True
    return jsonify({'status': 'started'})


@live_bp.route('/api/stop', methods=['POST'])
def api_stop_camera():
    global camera_state

    # Stop recording first if active
    with camera_state['recording_lock']:
        if camera_state['is_recording']:
            _stop_recording_internal()

    camera_state['is_running'] = False
    if camera_state['cap']:
        camera_state['cap'].release()
    return jsonify({'status': 'stopped'})


# ===================== RECORDING API =====================

@live_bp.route('/api/record/start', methods=['POST'])
def api_start_recording():
    """Start recording the live camera feed to a video file."""
    global camera_state

    if not camera_state['is_running']:
        return jsonify({'error': 'Camera is not running. Start it first.'}), 400

    with camera_state['recording_lock']:
        if camera_state['is_recording']:
            return jsonify({'error': 'Already recording'}), 400

    try:
        # Create recordings directory
        recordings_dir = Config.RECORDING_FOLDER
        os.makedirs(recordings_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"live_recording_{timestamp}.mp4"
        filepath = os.path.join(recordings_dir, filename)

        # Setup video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = 20.0
        frame_size = (640, 480)

        writer = cv2.VideoWriter(filepath, fourcc, fps, frame_size)

        if not writer.isOpened():
            return jsonify({'error': 'Failed to initialize video writer'}), 500

        # Log to MongoDB
        db = current_app.db
        user = session.get('user', {})

        recording_doc = start_recording(db, {
            'camera_id': 'webcam_0',
            'filename': filepath,
            'resolution': {'width': 640, 'height': 480},
            'fps': fps,
            'started_by': user.get('email', 'system')
        })

        # Update camera state
        camera_state['is_recording'] = True
        camera_state['video_writer'] = writer
        camera_state['recording_id'] = recording_doc['_id']
        camera_state['recording_filename'] = filepath
        camera_state['recording_frame_count'] = 0

        return jsonify({
            'status': 'recording_started',
            'recording_id': recording_doc['_id'],
            'filename': filename
        })

    except Exception as e:
        print(f"Error starting recording: {e}")
        return jsonify({'error': str(e)}), 500


@live_bp.route('/api/record/stop', methods=['POST'])
def api_stop_recording():
    """Stop recording and finalize the video file."""
    global camera_state

    with camera_state['recording_lock']:
        if not camera_state['is_recording']:
            return jsonify({'error': 'Not currently recording'}), 400

        result = _stop_recording_internal()

    return jsonify(result)


def _stop_recording_internal():
    """Internal helper to stop recording. Must be called with recording_lock held."""
    global camera_state

    try:
        # Release video writer
        if camera_state['video_writer'] is not None:
            camera_state['video_writer'].release()
            camera_state['video_writer'] = None

        # Convert to browser-playable format (h264)
        recording_file = camera_state['recording_filename']
        if recording_file and os.path.exists(recording_file):
            print(f"[RECORD] Converting recording to browser format...")
            convert_to_browser_format(recording_file)

        # Update MongoDB
        try:
            db = current_app.db
            stop_recording(
                db,
                camera_state['recording_id'],
                camera_state['recording_frame_count'],
                camera_state['recording_filename']
            )
        except Exception as e:
            print(f"Error updating recording in DB: {e}")

        result = {
            'status': 'recording_stopped',
            'recording_id': camera_state['recording_id'],
            'total_frames': camera_state['recording_frame_count'],
            'filename': camera_state['recording_filename']
        }

        # Reset recording state
        camera_state['is_recording'] = False
        camera_state['recording_id'] = None
        camera_state['recording_filename'] = None
        camera_state['recording_frame_count'] = 0

        return result

    except Exception as e:
        print(f"Error stopping recording: {e}")
        camera_state['is_recording'] = False
        return {'error': str(e)}


@live_bp.route('/api/record/status', methods=['GET'])
def api_recording_status():
    """Get current recording status."""
    with camera_state['recording_lock']:
        return jsonify({
            'is_recording': camera_state['is_recording'],
            'recording_id': camera_state.get('recording_id'),
            'frame_count': camera_state.get('recording_frame_count', 0),
            'filename': camera_state.get('recording_filename')
        })


@live_bp.route('/api/recordings', methods=['GET'])
def api_get_recordings():
    """Get list of all past recordings from MongoDB."""
    try:
        db = current_app.db
        recordings = get_all_recordings(db, camera_id='webcam_0', limit=50)
        return jsonify(recordings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===================== UPLOAD & ANALYZE =====================

@live_bp.route('/api/record/upload_and_process', methods=['POST'])
def upload_and_process_recording():
    """One-click: Upload recording + Run AI detection."""
    try:
        if 'user' not in session:
            return jsonify({'error': 'Not authenticated. Please login.'}), 401

        data = request.get_json(silent=True) or {}
        recording_id = data.get('recording_id')

        if not recording_id:
            return jsonify({'error': 'No recording_id provided'}), 400

        db = current_app.db

        # 1. Get recording from database
        recording = db.recordings.find_one({'_id': ObjectId(recording_id)})
        if not recording:
            return jsonify({'error': 'Recording not found in database'}), 404

        source_file = recording.get('filename')
        if not source_file:
            return jsonify({'error': 'No filename in recording document'}), 400

        if not os.path.exists(source_file):
            return jsonify({'error': f'Recording file not found on disk: {source_file}'}), 404

        # 2. Copy file to uploads/
        video_filename = os.path.basename(source_file)
        upload_dir = os.path.join(current_app.root_path, 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        dest_path = os.path.join(upload_dir, video_filename)

        if not os.path.exists(dest_path):
            shutil.copy2(source_file, dest_path)

        print(f"[UPLOAD] Source: {source_file}")
        print(f"[UPLOAD] Dest: {dest_path}")
        print(f"[UPLOAD] Exists: {os.path.exists(dest_path)}")

        # Store relative path
        rel_path = 'uploads/' + video_filename

        # 3. Create video entry in MongoDB
        user = session.get('user', {})
        start_time = recording.get('start_time', datetime.now())
        location_name = f"Live Recording {start_time.strftime('%Y-%m-%d %H:%M')}"

        video_data = {
            'file_path': rel_path,
            'location': location_name,
            'resolution': f"{recording.get('resolution', {}).get('width', 640)}x{recording.get('resolution', {}).get('height', 480)}",
            'status': 'processing',
            'owner_id': user.get('_id'),
            'source': 'live_recording',
            'recording_id': recording_id,
            'created_at': datetime.now()
        }

        result = db.videos.insert_one(video_data)
        video_id = str(result.inserted_id)
        print(f"[UPLOAD] Video entry created: {video_id}")

        # 4. Link back to recording
        db.recordings.update_one(
            {'_id': ObjectId(recording_id)},
            {'$set': {'video_id': video_id, 'updated_at': datetime.now()}}
        )

        # 5. Run AI detection using absolute path
        try:
            anomalies = process_video(db, dest_path, video_id=video_id)
        except Exception as proc_err:
            print(f"[ERROR] AI Processing error: {proc_err}")
            import traceback
            traceback.print_exc()

            db.videos.update_one(
                {'_id': ObjectId(video_id)},
                {'$set': {'status': 'error'}}
            )
            return jsonify({
                'status': 'error',
                'video_id': video_id,
                'error': f'AI processing failed: {str(proc_err)}',
                'dashboard_url': f'/dashboard?video_id={video_id}'
            }), 500

        # 6. Update status
        db.videos.update_one(
            {'_id': ObjectId(video_id)},
            {'$set': {
                'status': 'processed',
                'processed_at': datetime.now(),
                'anomaly_count': len(anomalies)
            }}
        )

        return jsonify({
            'status': 'completed',
            'video_id': video_id,
            'anomalies_found': len(anomalies),
            'message': f'Recording uploaded and analyzed! Found {len(anomalies)} anomalies.',
            'dashboard_url': f'/dashboard?video_id={video_id}'
        })

    except Exception as e:
        print(f"[ERROR] Upload & Process failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@live_bp.route('/api/record/upload_and_analyze', methods=['POST'])
def upload_and_analyze_recording():
    """Upload only (no AI processing)."""
    try:
        if 'user' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        data = request.get_json(silent=True) or {}
        recording_id = data.get('recording_id')

        if not recording_id:
            return jsonify({'error': 'No recording_id provided'}), 400

        db = current_app.db

        recording = db.recordings.find_one({'_id': ObjectId(recording_id)})
        if not recording:
            return jsonify({'error': 'Recording not found'}), 404

        source_file = recording.get('filename')
        if not source_file or not os.path.exists(source_file):
            return jsonify({'error': f'File not found: {source_file}'}), 404

        video_filename = os.path.basename(source_file)
        upload_dir = os.path.join(current_app.root_path, 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        dest_path = os.path.join(upload_dir, video_filename)

        if not os.path.exists(dest_path):
            shutil.copy2(source_file, dest_path)

        rel_path = 'uploads/' + video_filename

        user = session.get('user', {})
        start_time = recording.get('start_time', datetime.now())
        location_name = f"Live Recording {start_time.strftime('%Y-%m-%d %H:%M')}"

        video_data = {
            'file_path': rel_path,
            'location': location_name,
            'resolution': f"{recording.get('resolution', {}).get('width', 640)}x{recording.get('resolution', {}).get('height', 480)}",
            'status': 'unprocessed',
            'owner_id': user.get('_id'),
            'source': 'live_recording',
            'recording_id': recording_id,
            'created_at': datetime.now()
        }

        result = db.videos.insert_one(video_data)
        video_id = str(result.inserted_id)

        db.recordings.update_one(
            {'_id': ObjectId(recording_id)},
            {'$set': {'video_id': video_id, 'updated_at': datetime.now()}}
        )

        return jsonify({
            'status': 'uploaded',
            'video_id': video_id,
            'filename': video_filename,
            'location': location_name,
            'message': 'Video uploaded! Ready for AI analysis.'
        })

    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@live_bp.route('/api/record/process/<video_id>', methods=['POST'])
def process_recorded_video(video_id):
    """Run AI detection on uploaded recording."""
    try:
        if 'user' not in session:
            return jsonify({'error': 'Not authenticated'}), 401

        db = current_app.db
        video = get_video_by_id(db, video_id)

        if not video:
            return jsonify({'error': 'Video not found'}), 404

        db.videos.update_one(
            {'_id': ObjectId(video_id)},
            {'$set': {'status': 'processing'}}
        )

        # Find actual file
        from routes.video import find_video_file
        abs_path = find_video_file(video['file_path'])
        if abs_path is None:
            raise ValueError(f"Video file not found: {video['file_path']}")

        anomalies = process_video(db, abs_path, video_id=video_id)

        db.videos.update_one(
            {'_id': ObjectId(video_id)},
            {'$set': {
                'status': 'processed',
                'processed_at': datetime.now(),
                'anomaly_count': len(anomalies)
            }}
        )

        return jsonify({
            'status': 'processed',
            'video_id': video_id,
            'anomalies_found': len(anomalies),
            'message': f'AI found {len(anomalies)} anomalies!'
        })

    except Exception as e:
        print(f"[ERROR] Processing failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            db = current_app.db
            db.videos.update_one(
                {'_id': ObjectId(video_id)},
                {'$set': {'status': 'error'}}
            )
        except:
            pass
        return jsonify({'error': str(e)}), 500