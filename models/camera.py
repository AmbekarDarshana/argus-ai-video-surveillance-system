"""Camera and site management for multi-client assignments."""
from bson import ObjectId
from datetime import datetime


def create_camera(db, camera_data):
    """Create a new camera/site record.
    
    camera_data should contain:
    - name: str, human-readable camera name
    - location: str, physical location
    - owner_id: str, client who owns this camera
    - organization_id: str (optional)
    - camera_group_id: str (optional)
    - resolution: str, e.g. '1920x1080'
    - status: str, 'active', 'inactive', 'offline'
    """
    camera_data['created_at'] = datetime.now()
    camera_data['updated_at'] = datetime.now()
    camera_data['status'] = camera_data.get('status', 'active')
    result = db.cameras.insert_one(camera_data)
    camera_data['_id'] = str(result.inserted_id)
    return camera_data


def get_cameras(db, owner_id=None, organization_id=None):
    """Get cameras, optionally filtered by owner/org."""
    query = {}
    if owner_id:
        query['owner_id'] = owner_id
    if organization_id:
        query['organization_id'] = organization_id
    cameras = list(db.cameras.find(query))
    for c in cameras:
        c['_id'] = str(c['_id'])
    return cameras


def get_camera_by_id(db, camera_id):
    """Get a single camera by ID."""
    camera = db.cameras.find_one({'_id': ObjectId(camera_id)})
    if camera:
        camera['_id'] = str(camera['_id'])
    return camera


def update_camera(db, camera_id, update_data):
    """Update a camera record."""
    update_data['updated_at'] = datetime.now()
    db.cameras.update_one({'_id': ObjectId(camera_id)}, {'$set': update_data})


def delete_camera(db, camera_id):
    """Delete a camera."""
    db.cameras.delete_one({'_id': ObjectId(camera_id)})


def assign_camera_to_client(db, camera_id, owner_id):
    """Assign a camera to a client (for admin)."""
    db.cameras.update_one({'_id': ObjectId(camera_id)}, {'$set': {'owner_id': owner_id}})


def get_client_cameras(db, owner_id):
    """Get all cameras assigned to a client."""
    return get_cameras(db, owner_id=owner_id)


def get_camera_stats(db, camera_id, days=7):
    """Get statistics for a camera (anomalies, videos, etc)."""
    from datetime import timedelta
    
    cutoff = datetime.now() - timedelta(days=days)
    
    # Count videos
    videos = db.videos.count_documents({'camera_id': camera_id, 'created_at': {'$gte': cutoff}})
    
    # Count anomalies
    anomalies = db.anomalies.count_documents({'video_id': camera_id, 'detection_time': {'$gte': cutoff}})
    
    # Top anomaly type
    pipeline = [
        {'$match': {'video_id': camera_id, 'detection_time': {'$gte': cutoff}}},
        {'$group': {'_id': '$anomaly_type', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 1}
    ]
    top_anomaly = list(db.anomalies.aggregate(pipeline))
    
    return {
        'videos': videos,
        'anomalies': anomalies,
        'top_anomaly_type': top_anomaly[0]['_id'] if top_anomaly else None,
        'days': days
    }
