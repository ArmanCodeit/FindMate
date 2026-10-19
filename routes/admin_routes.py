import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from bson import ObjectId
from bson.errors import InvalidId

from database.connection import get_db
from services.auth_service import admin_required, get_current_user
from services.item_service import ItemService, CATEGORIES
from services.claim_service import ClaimService

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/")
@admin_required
def admin_dashboard():
    """Administrator control center with system metrics and moderation tools."""
    db = get_db()
    current_user = get_current_user()

    # System-wide metrics
    total_users = db.users.count_documents({})
    total_reports = db.items.count_documents({})
    open_lost = db.items.count_documents({"report_type": "lost", "resolution_status": "open"})
    open_found = db.items.count_documents({"report_type": "found", "resolution_status": "open"})
    resolved_reports = db.items.count_documents({"resolution_status": {"$in": ["claimed", "resolved"]}})
    pending_claims_count = db.claim_requests.count_documents({"status": "pending"})

    # Category breakdown via aggregation pipeline
    cat_pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    category_stats = list(db.items.aggregate(cat_pipeline))

    # All items for moderation (paginated or recent 30)
    items_cursor = db.items.aggregate([
        {"$sort": {"created_at": -1}},
        {"$limit": 30},
        {
            "$lookup": {
                "from": "users",
                "localField": "created_by",
                "foreignField": "_id",
                "as": "reporter"
            }
        },
        {"$unwind": {"path": "$reporter", "preserveNullAndEmptyArrays": True}}
    ])
    items = list(items_cursor)
    for it in items:
        if "reporter" in it and it["reporter"]:
            it["reporter"].pop("password_hash", None)

    # Users list
    users = list(db.users.find({}, {"password_hash": 0}).sort("created_at", -1).limit(50))

    # Claims list
    all_claims = ClaimService.get_all_claims(limit=30)

    return render_template(
        "admin_dashboard.html",
        admin=current_user,
        total_users=total_users,
        total_reports=total_reports,
        open_lost=open_lost,
        open_found=open_found,
        resolved_reports=resolved_reports,
        pending_claims_count=pending_claims_count,
        category_stats=category_stats,
        items=items,
        users=users,
        all_claims=all_claims,
        categories=CATEGORIES
    )

@admin_bp.route("/user/<user_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_user_status(user_id):
    """Activate or deactivate user account."""
    current_user = get_current_user()
    if str(current_user["_id"]) == str(user_id):
        flash("You cannot deactivate your own administrative account.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    try:
        u_oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        flash("Invalid user ID.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    db = get_db()
    user = db.users.find_one({"_id": u_oid})
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    new_status = not user.get("is_active", True)
    db.users.update_one({"_id": u_oid}, {"$set": {"is_active": new_status}})
    action_text = "activated" if new_status else "deactivated"
    flash(f"User {user.get('email')} has been {action_text}.", "success")
    return redirect(url_for("admin.admin_dashboard"))

@admin_bp.route("/user/<user_id>/change-role", methods=["POST"])
@admin_required
def change_user_role(user_id):
    """Change user role between student and admin with safeguards."""
    current_user = get_current_user()
    if str(current_user["_id"]) == str(user_id):
        flash("You cannot change your own role.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    new_role = request.form.get("role", "student")
    if new_role not in ("student", "admin"):
        flash("Invalid role specified.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    try:
        u_oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        flash("Invalid user ID.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    db = get_db()
    db.users.update_one({"_id": u_oid}, {"$set": {"role": new_role}})
    flash(f"User role updated to {new_role}.", "success")
    return redirect(url_for("admin.admin_dashboard"))

@admin_bp.route("/item/<item_id>/delete", methods=["POST"])
@admin_required
def admin_delete_item(item_id):
    """Admin moderation: delete an inappropriate listing."""
    current_user = get_current_user()
    success, msg = ItemService.delete_item(item_id, current_user["_id"], is_admin=True)
    if success:
        flash("Listing removed by administrative moderation.", "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin.admin_dashboard"))
