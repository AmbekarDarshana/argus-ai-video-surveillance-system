# Save as fix_video_path.py and run it
from pymongo import MongoClient
from bson import ObjectId
import os

client = MongoClient('mongodb+srv://videoAI:videoAI@cluster0.3fuhgvr.mongodb.net/ai_surveillance')
db = client.ai_surveillance

# List all videos and their paths
videos = list(db.videos.find())
print(f"\n=== Videos in Database ({len(videos)}) ===")
for v in videos:
    file_path = v.get('file_path', 'NO PATH')
    
    # Check if file actually exists
    # Strip leading slash for os.path check
    check_path = file_path.lstrip('/')
    exists = os.path.exists(check_path)
    
    print(f"  ID: {v['_id']}")
    print(f"  Location: {v.get('location')}")
    print(f"  DB Path: '{file_path}'")
    print(f"  File exists: {exists}")
    
    if not exists:
        # Also check without 'static/' prefix
        alt_path = os.path.join('static', 'videos', os.path.basename(file_path))
        alt_exists = os.path.exists(alt_path)
        print(f"  Alt path '{alt_path}' exists: {alt_exists}")
    print("  ---")

# List actual files in static/videos
print("\n=== Actual files in static/videos/ ===")
video_dir = 'static/videos'
if os.path.exists(video_dir):
    for f in os.listdir(video_dir):
        filepath = os.path.join(video_dir, f)
        size = os.path.getsize(filepath)
        print(f"  {f} ({size} bytes)")
else:
    print("  Directory does not exist!")