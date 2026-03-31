"""
Live Stream Camera Model
Stores configuration and status for IP cameras
"""
from datetime import datetime
from database.connection import get_db


class LiveStream:
    """Model for live streaming cameras"""
    
    @staticmethod
    def create(camera_name: str, rtsp_url: str, location: str, camera_type: str = "generic"):
        """Create a new live stream configuration
        
        Args:
            camera_name: Display name
            rtsp_url: RTSP stream URL (e.g., rtsp://admin:pass@192.168.1.100:554/stream)
            location: Physical location of camera
            camera_type: Brand type (hikvision, axis, dahua, generic)
        """
        stream_doc = {
            "name": camera_name,
            "rtsp_url": rtsp_url,
            "location": location,
            "camera_type": camera_type,
            "status": "offline",  # online, offline, error
            "is_active": True,
            "created_at": datetime.utcnow(),
            "last_connected": None,
            "last_anomaly": None,
            "total_anomalies_today": 0,
            "fps": 0,
            "resolution": "0x0",
            "error_message": None
        }
        result = get_db().live_streams.insert_one(stream_doc)
        return result.inserted_id
    
    @staticmethod
    def get_by_id(stream_id):
        """Get stream config by ID"""
        from bson.objectid import ObjectId
        return get_db().live_streams.find_one({"_id": ObjectId(stream_id)})
    
    @staticmethod
    def get_all_active():
        """Get all active streams"""
        return list(get_db().live_streams.find({"is_active": True}))
    
    @staticmethod
    def get_all():
        """Get all streams"""
        return list(get_db().live_streams.find())
    
    @staticmethod
    def update_status(stream_id, status: str, fps: int = None, resolution: str = None, error: str = None):
        """Update stream status
        
        Args:
            stream_id: Stream ID
            status: 'online', 'offline', 'error'
            fps: Current FPS
            resolution: Current resolution (e.g., "1920x1080")
            error: Error message if status is 'error'
        """
        from bson.objectid import ObjectId
        update_data = {
            "status": status,
            "last_connected": datetime.utcnow() if status == "online" else None
        }
        if fps is not None:
            update_data["fps"] = fps
        if resolution is not None:
            update_data["resolution"] = resolution
        if error is not None:
            update_data["error_message"] = error
        
        get_db().live_streams.update_one(
            {"_id": ObjectId(stream_id)},
            {"$set": update_data}
        )
    
    @staticmethod
    def update_anomaly(stream_id, anomaly_type: str):
        """Record an anomaly detection on this stream"""
        from bson.objectid import ObjectId
        get_db().live_streams.update_one(
            {"_id": ObjectId(stream_id)},
            {
                "$set": {"last_anomaly": datetime.utcnow()},
                "$inc": {"total_anomalies_today": 1}
            }
        )
    
    @staticmethod
    def delete(stream_id):
        """Delete a stream configuration"""
        from bson.objectid import ObjectId
        get_db().live_streams.delete_one({"_id": ObjectId(stream_id)})
    
    @staticmethod
    def toggle_active(stream_id, is_active: bool):
        """Enable/disable stream"""
        from bson.objectid import ObjectId
        get_db().live_streams.update_one(
            {"_id": ObjectId(stream_id)},
            {"$set": {"is_active": is_active}}
        )
