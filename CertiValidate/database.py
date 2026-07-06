"""
MongoDB Database Connection Module
Replaces the previous SQLite database with MongoDB (PyMongo)
Collections: users, certificates, verification_logs
"""
from pymongo import MongoClient, DESCENDING, ASCENDING
from pymongo.errors import ConnectionFailure, DuplicateKeyError
from datetime import datetime
import os

# ─── MongoDB Configuration ───────────────────────────────────────────────────
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME   = os.environ.get("MONGO_DB_NAME", "certivalidate")

_client = None
_db     = None

def get_mongo_client():
    """Returns a singleton MongoClient instance."""
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client

def get_db():
    """Returns the CertiValidate MongoDB database, creating indexes on first call."""
    global _db
    if _db is None:
        client = get_mongo_client()
        _db = client[DB_NAME]
        _create_indexes(_db)
    return _db

def _create_indexes(db):
    """Create unique / performance indexes on collections."""
    # Users
    db.users.create_index("email", unique=True)
    db.users.create_index("verification_token")
    # Certificates
    db.certificates.create_index("register_number", unique=True)
    db.certificates.create_index("certificate_hash")
    db.certificates.create_index("blockchain_hash")
    db.certificates.create_index([("uploaded_at", DESCENDING)])
    # Verification logs
    db.verification_logs.create_index([("timestamp", DESCENDING)])
    db.verification_logs.create_index("certificate_id")

def ping_db():
    """Test whether MongoDB is reachable. Returns True / False."""
    try:
        get_mongo_client().admin.command("ping")
        return True
    except ConnectionFailure:
        return False
