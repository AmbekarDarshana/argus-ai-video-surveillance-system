from pymongo import MongoClient
from config import Config

_db = None

def get_db():
    global _db
    if _db is None:
        client = MongoClient(Config.MONGO_URI)
        _db = client.ai_surveillance
    return _db
