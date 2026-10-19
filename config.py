import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "findmate-development-fallback-secret-key-2025")
    
    # MongoDB Configuration
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = os.getenv("DB_NAME", "findmate_db")
    
    # Cloudinary Configuration
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
    CLOUDINARY_FOLDER_ITEMS = os.getenv("CLOUDINARY_FOLDER_ITEMS", "findmate/items")
    CLOUDINARY_FOLDER_VERIFICATION = os.getenv("CLOUDINARY_FOLDER_VERIFICATION", "findmate/verification_photos")

    # Uploads Configuration
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    PRIVATE_UPLOAD_FOLDER = os.path.join(BASE_DIR, "private_uploads", "verification_photos")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB max upload
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
    
    # Session Security
    SESSION_COOKIE_NAME = "findmate_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # Application Info
    APP_NAME = "FindMate"
    APP_TAGLINE = "Campus Lost & Found"
    CAMPUS_NAME = "UH Mānoa Campus Registry"
