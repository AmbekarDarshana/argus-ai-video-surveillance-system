import bcrypt
from datetime import datetime

def create_user(db, user_data):
    existing = db.users.find_one({'email': user_data['email']})
    if existing:
        print(f"  User {user_data['email']} exists, skipping...")
        return existing
    
    user_data['password'] = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    user_data['created_at'] = datetime.now()
    result = db.users.insert_one(user_data)
    user_data['_id'] = result.inserted_id
    print(f"  Created: {user_data['email']}")
    return user_data

def get_user_by_email(db, email):
    return db.users.find_one({'email': email})

def verify_password(stored_password, provided_password):
    # 'stored_password' is the $2b$ string from your database
    # 'provided_password' is what the user typed (e.g., "12345")
    
    # Bcrypt needs bytes, so we encode them
    return bcrypt.checkpw(
        provided_password.encode('utf-8'), 
        stored_password.encode('utf-8')
    )
