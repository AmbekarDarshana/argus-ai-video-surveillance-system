"""API key management for client integrations and usage tracking."""
from bson import ObjectId
from datetime import datetime
import secrets
import string


def generate_api_key(length=32):
    """Generate a random API key."""
    chars = string.ascii_letters + string.digits + '-_'
    return ''.join(secrets.choice(chars) for _ in range(length))


def create_api_key(db, owner_id, name='Default Key'):
    """Create a new API key for a user.
    
    owner_id: user ID
    name: readable name for this key
    """
    key_data = {
        'owner_id': owner_id,
        'name': name,
        'key': generate_api_key(),
        'created_at': datetime.now(),
        'last_used': None,
        'enabled': True,
        'videos_processed': 0,
        'anomalies_detected': 0
    }
    result = db.api_keys.insert_one(key_data)
    key_data['_id'] = str(result.inserted_id)
    return key_data


def get_api_keys(db, owner_id):
    """List all API keys for a user."""
    keys = list(db.api_keys.find({'owner_id': owner_id}))
    for k in keys:
        k['_id'] = str(k['_id'])
        k['key'] = k['key'][:8] + '...' if k.get('key') else None  # mask key
    return keys


def get_api_key_by_value(db, key_value):
    """Authenticate by API key value."""
    key_doc = db.api_keys.find_one({'key': key_value, 'enabled': True})
    if key_doc:
        # update last_used
        db.api_keys.update_one({'_id': key_doc['_id']}, {'$set': {'last_used': datetime.now()}})
        return key_doc
    return None


def delete_api_key(db, key_id):
    """Delete an API key."""
    db.api_keys.delete_one({'_id': ObjectId(key_id)})


def increment_api_stats(db, owner_id, videos=0, anomalies=0):
    """Update usage stats for all active keys of a user."""
    db.api_keys.update_many(
        {'owner_id': owner_id, 'enabled': True},
        {'$inc': {'videos_processed': videos, 'anomalies_detected': anomalies}}
    )


def get_client_usage(db, owner_id, days=30):
    """Get client usage statistics."""
    from datetime import timedelta
    from collections import defaultdict
    
    cutoff = datetime.now() - timedelta(days=days)
    
    # Count videos processed
    videos = db.videos.count_documents({'owner_id': owner_id, 'created_at': {'$gte': cutoff}})
    
    # Count anomalies detected
    anomalies = db.anomalies.count_documents({'owner_id': owner_id, 'detection_time': {'$gte': cutoff}})
    
    # Get keys and their stats
    keys = list(db.api_keys.find({'owner_id': owner_id}))
    total_processed = sum(k.get('videos_processed', 0) for k in keys)
    total_detected = sum(k.get('anomalies_detected', 0) for k in keys)
    
    # Estimate GB (rough: 50MB per video)
    gb_processed = (videos * 0.05)
    
    return {
        'videos': videos,
        'anomalies': anomalies,
        'api_calls_total': total_processed,
        'anomalies_via_api': total_detected,
        'gb_processed': round(gb_processed, 2),
        'days_tracked': days
    }
