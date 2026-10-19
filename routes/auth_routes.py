import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from services.auth_service import AuthService, login_user, logout_user, get_current_user

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Handle student and admin authentication."""
    # If already logged in, redirect to dashboard or home
    if session.get("user_id"):
        return redirect(url_for("dashboard.student_dashboard"))

    next_url = request.args.get("next") or request.form.get("next") or url_for("item.home")

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        success, msg, user = AuthService.authenticate_user(email, password)
        if success and user:
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.get('full_name')}!", "success")
            
            # Avoid open redirect vulnerabilities
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("dashboard.student_dashboard")
            return redirect(next_url)
        else:
            flash(msg, "danger")

    return render_template("login.html", next=next_url)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Handle new student registration."""
    if session.get("user_id"):
        return redirect(url_for("dashboard.student_dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        student_id = request.form.get("student_id", "").strip()
        phone_number = request.form.get("phone_number", "").strip()

        success, msg, user = AuthService.register_user(
            full_name=full_name,
            email=email,
            password=password,
            confirm_password=confirm_password,
            student_id=student_id,
            phone_number=phone_number
        )

        if success and user:
            # Automatically log in the user after successful registration
            login_user(user)
            flash("Account registered successfully! Welcome to FindMate.", "success")
            return redirect(url_for("dashboard.student_dashboard"))
        else:
            flash(msg, "danger")

    return render_template("register.html")

@auth_bp.route("/profile/phone", methods=["POST"])
def update_phone():
    """Update verified mobile phone number for logged-in user."""
    from services.auth_service import login_required
    if not session.get("user_id"):
        flash("Please sign in to update your profile.", "warning")
        return redirect(url_for("auth.login"))

    user_id = session.get("user_id")
    phone_number = request.form.get("phone_number", "").strip()

    success, msg, cleaned = AuthService.update_user_phone(user_id, phone_number)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")

    return redirect(request.referrer or url_for("claim.claims_overview"))

@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Log out current user and clear session."""
    logout_user()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("item.home"))

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Password recovery instructions page."""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter your registered campus email address.", "danger")
        else:
            # Generic safe response to prevent user enumeration
            flash(
                "If an account exists with this email address, password recovery instructions have been sent.",
                "success"
            )
            return redirect(url_for("auth.login"))
    return render_template("forgot_password.html")
