import secrets
import logging
from datetime import datetime, timezone
from functools import wraps
from bson import ObjectId
from bson.errors import InvalidId
from flask import session, request, redirect, url_for, flash, abort, g
from werkzeug.security import generate_password_hash, check_password_hash
from email_validator import validate_email, EmailNotValidError

from database.connection import get_db

logger = logging.getLogger(__name__)

def validate_indian_mobile(phone):
    """
    Validates a 10-digit Indian mobile number beginning with 6, 7, 8, or 9.
    Strips country code (+91, 91), leading zeros, and delimiters.
    Returns (is_valid: bool, cleaned_number: str|None).
    """
    import re
    if not phone:
        return False, None
    raw = str(phone).strip()
    digits = re.sub(r'[\s\-+()]+', '', raw)
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith('0') and len(digits) == 11:
        digits = digits[1:]
    
    if re.match(r'^[6789]\d{9}$', digits):
        return True, digits
    return False, None


class AuthService:
    """Handles user authentication, registration, password hashing, and session management."""

    @staticmethod
    def register_user(full_name, email, password, confirm_password, student_id=None, phone_number=None):
        """
        Register a new student user.
        Validates all inputs, hashes the password, and prevents role escalation.
        Returns (success: bool, message: str, user_doc: dict|None).
        """
        # Validate inputs
        if not full_name or len(full_name.strip()) < 2:
            return False, "Full name must be at least 2 characters long.", None
        
        full_name = full_name.strip()
        if len(full_name) > 80:
            return False, "Full name cannot exceed 80 characters.", None

        if not email:
            return False, "Email address is required.", None

        # Normalize and validate email
        try:
            valid = validate_email(email.strip(), check_deliverability=False)
            normalized_email = valid.normalized.lower()
        except EmailNotValidError as e:
            return False, f"Invalid email address: {str(e)}", None

        # Password checks
        if not password or len(password) < 6:
            return False, "Password must be at least 6 characters long.", None

        if password != confirm_password:
            return False, "Passwords do not match.", None

        cleaned_phone = None
        if phone_number and str(phone_number).strip():
            is_valid, cleaned = validate_indian_mobile(phone_number)
            if not is_valid:
                return False, "Please enter a valid 10-digit mobile number starting with 6, 7, 8, or 9.", None
            cleaned_phone = cleaned

        db = get_db()

        # Check existing user
        existing_user = db.users.find_one({"email": normalized_email})
        if existing_user:
            return False, "An account with this email address already exists.", None

        # Hash password securely using Werkzeug scrypt/pbkdf2
        password_hash = generate_password_hash(password)

        new_user = {
            "full_name": full_name,
            "email": normalized_email,
            "password_hash": password_hash,
            "role": "student",  # Never allow role escalation from public signup
            "student_id": (student_id.strip() if student_id else None),
            "phone_number": cleaned_phone,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        try:
            result = db.users.insert_one(new_user)
            new_user["_id"] = result.inserted_id
            logger.info("Created new student user: %s (id: %s)", normalized_email, result.inserted_id)
            return True, "Registration successful! You can now log in.", new_user
        except Exception as exc:
            logger.error("Failed to insert user: %s", exc)
            return False, "A database error occurred during registration. Please try again.", None

    @staticmethod
    def update_user_phone(user_id, phone_number):
        """
        Validate and update an authenticated user's mobile number.
        Returns (success: bool, message: str, cleaned_phone: str|None).
        """
        if not user_id:
            return False, "User not authenticated.", None

        try:
            user_oid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        except (InvalidId, TypeError):
            return False, "Invalid user identifier.", None

        is_valid, cleaned = validate_indian_mobile(phone_number)
        if not is_valid:
            return False, "Please enter a valid 10-digit Indian mobile number beginning with 6, 7, 8, or 9.", None

        db = get_db()
        now = datetime.now(timezone.utc)
        result = db.users.update_one(
            {"_id": user_oid},
            {"$set": {"phone_number": cleaned, "updated_at": now}}
        )
        if result.matched_count == 0:
            return False, "User record not found.", None

        logger.info("Updated phone number for user %s", user_id)
        return True, "Mobile phone number saved successfully.", cleaned

    @staticmethod
    def authenticate_user(email, password):
        """
        Verify credentials for email and password.
        Returns (success: bool, message: str, user_doc: dict|None).
        """
        if not email or not password:
            return False, "Please provide both email and password.", None

        normalized_email = email.strip().lower()
        db = get_db()
        user = db.users.find_one({"email": normalized_email})

        if not user:
            return False, "Invalid email address or password.", None

        if not user.get("is_active", True):
            return False, "Your account has been deactivated. Please contact campus security.", None

        if not check_password_hash(user["password_hash"], password):
            return False, "Invalid email address or password.", None

        # Return clean user (no password hash)
        clean_user = dict(user)
        clean_user.pop("password_hash", None)
        return True, "Login successful.", clean_user

    @staticmethod
    def get_user_by_id(user_id):
        """Retrieve user document by ObjectId string or ObjectId."""
        if not user_id:
            return None
        try:
            oid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        except (InvalidId, TypeError):
            return None

        db = get_db()
        user = db.users.find_one({"_id": oid})
        if user:
            user.pop("password_hash", None)
        return user

    @staticmethod
    def get_user_by_email(email):
        """Retrieve user document by email."""
        if not email:
            return None
        db = get_db()
        user = db.users.find_one({"email": email.strip().lower()})
        if user:
            user.pop("password_hash", None)
        return user


# Session and CSRF helpers
def login_user(user, remember=False):
    """Store user in session."""
    session.permanent = bool(remember)
    session["user_id"] = str(user["_id"])
    session["user_name"] = user.get("full_name", "Student")
    session["user_email"] = user.get("email", "")
    session["user_role"] = user.get("role", "student")
    session["student_id"] = user.get("student_id", "")
    session.modified = True

def logout_user():
    """Clear session data."""
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)
    session.pop("user_role", None)
    session.pop("student_id", None)
    session.modified = True

def get_current_user():
    """Get active user dictionary or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = AuthService.get_user_by_id(user_id)
    if not user or not user.get("is_active", True):
        logout_user()
        return None
    return user

def generate_csrf_token():
    """Generate or retrieve CSRF token from session."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

def validate_csrf():
    """Check CSRF token on POST/PUT/DELETE requests."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Check form or header
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        expected = session.get("_csrf_token")
        if not expected or not token or not secrets.compare_digest(token, expected):
            logger.warning("CSRF validation failed for route: %s", request.path)
            abort(400, description="Invalid or missing CSRF token. Please refresh the page and try again.")

def login_required(f):
    """Route decorator requiring authenticated user."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Route decorator requiring administrator role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in with administrator credentials.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        user = get_current_user()
        if not user or user.get("role") != "admin":
            flash("Access denied: Administrator privileges required.", "danger")
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function
