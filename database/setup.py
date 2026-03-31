from database.connection import get_db
from models.user import create_user
from models.video import create_video

db = get_db()

db.users.drop()
db.videos.drop()
db.anomalies.drop()
db.feedback.drop()
db.payments.drop()
db.tickets.drop()

print("Creating users...")
create_user(db, {'name': 'Admin User', 'email': 'admin@example.com', 'password': 'admin123', 'phone': '+1234567890', 'role': 'admin'})
create_user(db, {'name': 'Client User', 'email': 'client@example.com', 'password': 'client123', 'phone': '+1234567893', 'role': 'client'})

print("Creating sample videos...")
video1 = create_video(db, {'file_path': '/static/videos/sample.mp4', 'location': 'Entrance', 'resolution': '1080p', 'status': 'unprocessed'})

print("✅ Demo data seeded!")
print("\nLogins: client@example.com / client123")
