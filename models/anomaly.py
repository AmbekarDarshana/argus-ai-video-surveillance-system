from bson import ObjectId
from datetime import datetime

def log_anomaly(db, anomaly_data):
    """Insert a new anomaly record.

    ``anomaly_data`` may already contain ``owner_id``,
    ``organization_id`` and ``camera_group_id`` (these usually come from the
    associated video document).  We also stamp the detection time and
    initialize status.
    """
    anomaly_data['detection_time'] = datetime.now()
    anomaly_data['status'] = 'pending'
    result = db.anomalies.insert_one(anomaly_data)
    anomaly_data['_id'] = str(result.inserted_id)
    return anomaly_data

def get_anomalies(db,
                  video_id=None,
                  owner_id=None,
                  organization_id=None,
                  camera_group_id=None,
                  anomaly_type=None,
                  start_time=None,
                  end_time=None):
    """Return list of anomalies.

    Optional filters may be passed for multi‑tenant scoping (``owner_id``,
    ``organization_id``, ``camera_group_id``) and investigative searches using
    ``video_id`` (also used as a camera selector), ``anomaly_type`` and a
    timestamp range.  ``start_time``/``end_time`` should be Python
    ``datetime`` objects; any that are provided will be applied to the
    ``detection_time`` field.

    Admin callers can invoke with no filters.  Clients should supply their
    ``owner_id`` to see only their own events.
    """
    query = {}
    if video_id is not None:
        query['video_id'] = video_id
    if owner_id is not None:
        query['owner_id'] = owner_id
    if organization_id is not None:
        query['organization_id'] = organization_id
    if camera_group_id is not None:
        query['camera_group_id'] = camera_group_id
    if anomaly_type:
        query['anomaly_type'] = anomaly_type

    # time range
    if start_time or end_time:
        ts_query = {}
        if start_time:
            ts_query['$gte'] = start_time
        if end_time:
            ts_query['$lte'] = end_time
        query['detection_time'] = ts_query

    anomalies = list(db.anomalies.find(query).sort('frame_timestamp', 1))
    for anomaly in anomalies:
        anomaly['_id'] = str(anomaly['_id'])
    return anomalies

def update_anomaly_status(db, anomaly_id, status):
    db.anomalies.update_one({'_id': ObjectId(anomaly_id)}, {'$set': {'status': status}})

def get_anomaly_by_id(db, anomaly_id):
    anomaly = db.anomalies.find_one({'_id': ObjectId(anomaly_id)})
    if anomaly:
        anomaly['_id'] = str(anomaly['_id'])
    return anomaly
