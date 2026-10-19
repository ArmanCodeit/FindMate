import sys
import logging
from pymongo import MongoClient, TEXT, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from config import Config

logger = logging.getLogger(__name__)

# Global client and db reference
_mongo_client = None
_db = None

def get_client():
    """Return singleton MongoClient with connection verification."""
    global _mongo_client
    if _mongo_client is None:
        mongo_uri = os.getenv("MONGO_URI") or getattr(Config, "MONGO_URI", "mongodb://localhost:27017/")
        try:
            _mongo_client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=3000,
                connectTimeoutMS=3000
            )
            # Verify connection via admin ping
            _mongo_client.admin.command('ping')
            logger.info("Successfully connected to MongoDB at %s", mongo_uri.split("@")[-1] if "@" in mongo_uri else mongo_uri)
        except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
            _mongo_client = None  # Reset so subsequent retry calls can re-attempt with new credentials
            logger.error("FATAL: Could not connect to MongoDB at %s: %s", mongo_uri, exc)
            raise ConnectionError(
                f"Failed to connect to MongoDB at {mongo_uri}. "
                f"Please ensure MongoDB connection URI is configured."
            ) from exc
    return _mongo_client

def get_db():
    """Return database instance for findmate_db."""
    global _db
    if _db is None:
        client = get_client()
        db_name = os.getenv("DB_NAME") or getattr(Config, "DB_NAME", "findmate_db")
        _db = client[db_name]
    return _db

def check_db_connection():
    """Health check for MongoDB connection."""
    try:
        client = get_client()
        client.admin.command('ping')
        return True, "MongoDB connection healthy"
    except Exception as exc:
        return False, str(exc)

def init_db_indexes():
    """
    Safely initialize required indexes across findmate_db collections.
    Ensures unique constraints and fast queries for filters and search.
    """
    db = get_db()
    
    # 1. users collection indexes
    try:
        # Unique case-insensitive index on email
        db.users.create_index(
            [("email", ASCENDING)],
            unique=True,
            name="uniq_user_email"
        )
        db.users.create_index([("role", ASCENDING)], name="idx_user_role")
        logger.info("Initialized users collection indexes")
    except Exception as exc:
        logger.warning("Error creating users indexes: %s", exc)
        
    # 2. items collection indexes
    try:
        # Compound index for filtering lost/found and resolution status
        db.items.create_index(
            [("report_type", ASCENDING), ("resolution_status", ASCENDING)],
            name="idx_items_type_status"
        )
        db.items.create_index([("category", ASCENDING)], name="idx_items_category")
        db.items.create_index([("location", ASCENDING)], name="idx_items_location")
        db.items.create_index([("created_at", DESCENDING)], name="idx_items_created_at")
        db.items.create_index([("created_by", ASCENDING)], name="idx_items_creator")
        db.items.create_index(
            [("contact_number", ASCENDING)],
            unique=True,
            sparse=True,
            name="uniq_contact_number"
        )
        
        # Text index for title, description, location search
        # Check existing text indexes first to prevent conflicts
        existing_indexes = db.items.index_information()
        has_text_index = any(idx.get("weights") for idx in existing_indexes.values())
        if not has_text_index:
            db.items.create_index(
                [
                    ("title", TEXT),
                    ("description", TEXT),
                    ("location", TEXT),
                    ("additional_details", TEXT)
                ],
                weights={"title": 10, "description": 5, "location": 3, "additional_details": 2},
                name="idx_items_text_search"
            )
        logger.info("Initialized items collection indexes")
    except Exception as exc:
        logger.warning("Error creating items indexes: %s", exc)
        
    # 3. claim_requests collection indexes
    try:
        db.claim_requests.create_index(
            [("item_id", ASCENDING), ("requested_by", ASCENDING)],
            name="idx_claim_item_user"
        )
        db.claim_requests.create_index([("item_id", ASCENDING)], name="idx_claim_item")
        db.claim_requests.create_index([("requested_by", ASCENDING)], name="idx_claim_user")
        db.claim_requests.create_index([("status", ASCENDING)], name="idx_claim_status")
        db.claim_requests.create_index([("created_at", DESCENDING)], name="idx_claim_created")
        logger.info("Initialized claim_requests collection indexes")
    except Exception as exc:
        logger.warning("Error creating claim_requests indexes: %s", exc)
