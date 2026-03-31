from bson import ObjectId
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from config import Config

def create_video(db, video_data):
    # when a user uploads a video we expect the caller to supply
    # owner_id/organization_id/camera_group_id (typically pulled from
    # ``session['user']``); fall back to whatever is already present.
    if 'file' in video_data:
        file = video_data.pop('file')
        filename = secure_filename(file.filename)
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        file.save(filepath)
        video_data['file_path'] = f"/static/videos/{filename}"

    video_data['created_at'] = datetime.now()
    video_data['status'] = video_data.get('status', 'unprocessed')
    # owner / org / group may already exist in video_data; whatever is there
    result = db.videos.insert_one(video_data)
    video_data['_id'] = result.inserted_id
    return video_data

def get_all_videos(db, owner_id=None, organization_id=None, camera_group_id=None):
    """Return videos filtered by the given identifiers.

    Admin code can call with no arguments to receive everything.  Client
    code should pass ``owner_id`` (the string form of the user ID) so only
    their own videos are returned.
    """
    query = {}
    if owner_id:
        query['owner_id'] = owner_id
    if organization_id:
        query['organization_id'] = organization_id
    if camera_group_id:
        query['camera_group_id'] = camera_group_id

    videos = list(db.videos.find(query))
    for video in videos:
        video['_id'] = str(video['_id'])
    return videos

def update_video_status(db, video_id, status, processed_at=None):
    update_data = {'status': status}
    if processed_at:
        update_data['processed_at'] = processed_at
    db.videos.update_one({'_id': ObjectId(video_id)}, {'$set': update_data})

def get_video_by_id(db, video_id):
    video = db.videos.find_one({'_id': ObjectId(video_id)})
    if video:
        video['_id'] = str(video['_id'])
    return video
