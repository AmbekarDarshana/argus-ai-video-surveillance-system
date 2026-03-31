# models/recording.py
"""
Recording model for logging live camera video recordings to MongoDB.
Stores metadata about each recording session.
"""
from bson import ObjectId
from datetime import datetime
import os


def start_recording(db, recording_data):
    """
    Insert a new recording document when recording starts.
    
    recording_data should contain:
        - camera_id: str (e.g., 'live_webcam_01')
        - filename: str (video file path)
        - resolution: dict {'width': int, 'height': int}
        - fps: float
        - started_by: str (user email or ID, optional)
    """
    doc = {
        'camera_id': recording_data.get('camera_id', 'webcam_0'),
        'filename': recording_data.get('filename'),
        'resolution': recording_data.get('resolution', {'width': 640, 'height': 480}),
        'fps': recording_data.get('fps', 20.0),
        'start_time': datetime.now(),
        'end_time': None,
        'duration_seconds': None,
        'status': 'recording',          # recording, completed, error
        'frame_count': 0,
        'file_size_bytes': None,
        'anomalies_during_recording': 0,
        'anomaly_ids': [],
        'video_id': None,                                              # List of anomaly ObjectIds detected during recording
        'started_by': recording_data.get('started_by', 'system'),
        'created_at': datetime.now(),
        'updated_at': datetime.now()
    }

    result = db.recordings.insert_one(doc)
    doc['_id'] = str(result.inserted_id)
    print(f"[DB] Recording started: {doc['_id']}")
    return doc


def stop_recording(db, recording_id, frame_count, filename):
    """
    Update recording document when recording stops.
    Calculates duration and file size.
    """
    end_time = datetime.now()

    # Get start time to calculate duration
    recording = db.recordings.find_one({'_id': ObjectId(recording_id)})
    duration = None
    if recording and recording.get('start_time'):
        duration = (end_time - recording['start_time']).total_seconds()

    # Get file size
    file_size = None
    if filename and os.path.exists(filename):
        file_size = os.path.getsize(filename)

    db.recordings.update_one(
        {'_id': ObjectId(recording_id)},
        {'$set': {
            'end_time': end_time,
            'duration_seconds': round(duration, 2) if duration else None,
            'status': 'completed',
            'frame_count': frame_count,
            'file_size_bytes': file_size,
            'updated_at': datetime.now()
        }}
    )

    print(f"[DB] Recording completed: {recording_id}")
    print(f"     Duration: {round(duration, 2) if duration else 'N/A'}s | "
          f"Frames: {frame_count} | Size: {file_size} bytes")
    return True


def update_recording_frame_count(db, recording_id, frame_count):
    """Update the frame count periodically during recording."""
    db.recordings.update_one(
        {'_id': ObjectId(recording_id)},
        {'$set': {
            'frame_count': frame_count,
            'updated_at': datetime.now()
        }}
    )


def add_anomaly_to_recording(db, recording_id, anomaly_id):
    """Link an anomaly detected during this recording session."""
    db.recordings.update_one(
        {'_id': ObjectId(recording_id)},
        {
            '$push': {'anomaly_ids': str(anomaly_id)},
            '$inc': {'anomalies_during_recording': 1},
            '$set': {'updated_at': datetime.now()}
        }
    )


def mark_recording_error(db, recording_id, error_message):
    """Mark a recording as errored."""
    db.recordings.update_one(
        {'_id': ObjectId(recording_id)},
        {'$set': {
            'status': 'error',
            'end_time': datetime.now(),
            'error_message': error_message,
            'updated_at': datetime.now()
        }}
    )


def get_all_recordings(db, camera_id=None, limit=50):
    """Retrieve recordings, optionally filtered by camera."""
    query = {}
    if camera_id:
        query['camera_id'] = camera_id

    recordings = list(
        db.recordings.find(query)
        .sort('start_time', -1)
        .limit(limit)
    )
    for r in recordings:
        r['_id'] = str(r['_id'])
    return recordings


def get_recording_by_id(db, recording_id):
    """Get a specific recording."""
    recording = db.recordings.find_one({'_id': ObjectId(recording_id)})
    if recording:
        recording['_id'] = str(recording['_id'])
    return recording


def get_recording_stats(db):
    """Get aggregate statistics of all recordings."""
    pipeline = [
        {'$match': {'status': 'completed'}},
        {'$group': {
            '_id': None,
            'total_recordings': {'$sum': 1},
            'total_duration': {'$sum': '$duration_seconds'},
            'total_frames': {'$sum': '$frame_count'},
            'total_size_bytes': {'$sum': '$file_size_bytes'},
            'total_anomalies': {'$sum': '$anomalies_during_recording'},
            'avg_duration': {'$avg': '$duration_seconds'}
        }}
    ]
    result = list(db.recordings.aggregate(pipeline))
    return result[0] if result else None