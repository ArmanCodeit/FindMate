import logging
from flask import Blueprint, render_template
from bson import ObjectId
from database.connection import get_db
from services.auth_service import login_required, get_current_user
from services.claim_service import ClaimService

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
@login_required
def student_dashboard():
    """Personal portal for student reports, claims, and status tracking."""
    current_user = get_current_user()
    db = get_db()
    user_oid = current_user["_id"]

    # Student personal reports
    my_items = list(db.items.find({"created_by": user_oid}).sort("created_at", -1))

    # Aggregated personal counts
    total_my_reports = len(my_items)
    lost_my_reports = sum(1 for it in my_items if it.get("report_type") == "lost")
    found_my_reports = sum(1 for it in my_items if it.get("report_type") == "found")
    resolved_my_reports = sum(1 for it in my_items if it.get("resolution_status") in ("claimed", "resolved"))

    # Claims sent by current student
    claims_sent = ClaimService.get_claims_submitted_by_user(user_oid)

    # Claims received for items reported by current student
    claims_received = ClaimService.get_claims_received_for_user_items(user_oid)

    return render_template(
        "student_dashboard.html",
        user=current_user,
        items=my_items,
        total_reports=total_my_reports,
        lost_reports=lost_my_reports,
        found_reports=found_my_reports,
        resolved_reports=resolved_my_reports,
        claims_sent=claims_sent,
        claims_received=claims_received
    )
