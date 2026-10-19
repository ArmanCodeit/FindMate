import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from services.auth_service import login_required, get_current_user
from services.item_service import ItemService, CATEGORIES, LOCATIONS

logger = logging.getLogger(__name__)
item_bp = Blueprint("item", __name__)

@item_bp.route("/")
def home():
    """FindMate Home Page matching Stitch design."""
    stats = ItemService.get_summary_stats()
    
    # Selected category for Recent Intake tab
    active_tab = request.args.get("tab", "All")
    recent_items = ItemService.get_recent_items(limit=4, category=active_tab)
    
    # Campus feed mini preview items
    feed_items = ItemService.get_recent_items(limit=3)

    return render_template(
        "home.html",
        stats=stats,
        recent_items=recent_items,
        feed_items=feed_items,
        active_tab=active_tab,
        categories=CATEGORIES,
        locations=LOCATIONS
    )

@item_bp.route("/browse")
def browse():
    """Browse lost and found items with search, filters, and pagination."""
    q = request.args.get("q", "")
    category = request.args.get("category", "")
    building = request.args.get("building", "")
    date_val = request.args.get("date", "")
    sort_by = request.args.get("sort", "newest")
    report_type = request.args.get("type", "")
    status = request.args.get("status", "")
    page = request.args.get("page", 1)

    filters = {
        "q": q,
        "category": category,
        "building": building,
        "date": date_val,
        "type": report_type,
        "status": status
    }

    result = ItemService.get_items(filters=filters, page=page, per_page=8, sort_by=sort_by)
    stats = ItemService.get_summary_stats()

    return render_template(
        "browse_items.html",
        items=result["items"],
        pagination=result,
        current_filters=filters,
        current_sort=sort_by,
        stats=stats,
        categories=CATEGORIES,
        locations=LOCATIONS
    )

@item_bp.route("/item/<item_id>")
def item_details(item_id):
    """Item detail page with verification status and claim initiation."""
    item = ItemService.get_item_by_id(item_id)
    if not item:
        flash("The requested item was not found or may have been deleted.", "warning")
        return redirect(url_for("item.browse")), 404

    current_user = get_current_user()
    is_owner = False
    is_admin = False
    has_approved_claim = False
    has_pending_claim = False

    if current_user:
        is_owner = (str(item.get("created_by")) == str(current_user["_id"]))
        is_admin = (current_user.get("role") == "admin")
        from database.connection import get_db
        db = get_db()
        has_approved_claim = bool(db.claim_requests.find_one({
            "item_id": item["_id"],
            "requested_by": current_user["_id"],
            "status": "approved",
            "contact_sharing_enabled": True
        }))
        has_pending_claim = bool(db.claim_requests.find_one({
            "item_id": item["_id"],
            "requested_by": current_user["_id"],
            "status": "pending"
        }))

    contact_unlocked = (is_owner or has_approved_claim or is_admin)

    # Sanitize item dict for template: do not leak raw contact number if not unlocked
    raw_contact = item.get("contact_number") or ""
    item_for_view = dict(item)
    if not contact_unlocked:
        item_for_view["raw_contact_number"] = None
    else:
        item_for_view["raw_contact_number"] = raw_contact

    nearby_items = ItemService.get_nearby_items(
        location=item.get("location", ""),
        exclude_id=item["_id"],
        limit=4
    )

    return render_template(
        "item_details.html",
        item=item_for_view,
        is_owner=is_owner,
        is_admin=is_admin,
        contact_unlocked=contact_unlocked,
        has_approved_claim=has_approved_claim,
        has_pending_claim=has_pending_claim,
        nearby_items=nearby_items
    )

@item_bp.route("/report", methods=["GET", "POST"])
@login_required
def report_item():
    """Report a lost or found item matching the Stitch layout."""
    current_user = get_current_user()

    # Pre-select report type from query param if available
    default_type = request.args.get("type", "found")
    if default_type not in ("lost", "found"):
        default_type = "found"

    if request.method == "POST":
        file = request.files.get("item_photo")
        data = {
            "title": request.form.get("title", ""),
            "category": request.form.get("category", ""),
            "report_type": request.form.get("report_type", default_type),
            "location": request.form.get("location", ""),
            "date_lost_or_found": request.form.get("date_lost_or_found", ""),
            "description": request.form.get("description", ""),
            "additional_details": request.form.get("additional_details", ""),
            "contact_preference": request.form.get("contact_preference", "direct")
        }

        success, msg, item_id = ItemService.create_item(
            data=data,
            file_storage=file,
            user_id=current_user["_id"]
        )

        if success and item_id:
            flash(msg, "success")
            return redirect(url_for("item.item_details", item_id=item_id))
        else:
            flash(msg, "danger")
            # Preserve form data on error
            return render_template(
                "report_item.html",
                default_type=data.get("report_type", default_type),
                form_data=data,
                categories=CATEGORIES,
                locations=LOCATIONS
            )

    return render_template(
        "report_item.html",
        default_type=default_type,
        form_data={},
        categories=CATEGORIES,
        locations=LOCATIONS
    )

@item_bp.route("/item/<item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    """Edit existing lost/found report."""
    item = ItemService.get_item_by_id(item_id)
    if not item:
        flash("Item not found.", "danger")
        return redirect(url_for("item.browse")), 404

    current_user = get_current_user()
    is_owner = (str(item.get("created_by")) == str(current_user["_id"]))
    is_admin = (current_user.get("role") == "admin")

    if not is_owner and not is_admin:
        flash("You are not authorized to edit this report.", "danger")
        return redirect(url_for("item.item_details", item_id=item_id))

    if request.method == "POST":
        file = request.files.get("item_photo")
        data = {
            "title": request.form.get("title", ""),
            "category": request.form.get("category", ""),
            "location": request.form.get("location", ""),
            "date_lost_or_found": request.form.get("date_lost_or_found", ""),
            "description": request.form.get("description", ""),
            "additional_details": request.form.get("additional_details", ""),
            "resolution_status": request.form.get("resolution_status", item.get("resolution_status", "open"))
        }

        success, msg = ItemService.update_item(
            item_id=item_id,
            data=data,
            file_storage=file,
            user_id=current_user["_id"],
            is_admin=is_admin
        )

        if success:
            flash(msg, "success")
            return redirect(url_for("item.item_details", item_id=item_id))
        else:
            flash(msg, "danger")

    return render_template(
        "edit_item.html",
        item=item,
        categories=CATEGORIES,
        locations=LOCATIONS
    )

@item_bp.route("/item/<item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    """Delete report document with ownership verification."""
    current_user = get_current_user()
    is_admin = (current_user.get("role") == "admin")

    success, msg = ItemService.delete_item(
        item_id=item_id,
        user_id=current_user["_id"],
        is_admin=is_admin
    )

    if success:
        flash(msg, "info")
        return redirect(url_for("dashboard.student_dashboard"))
    else:
        flash(msg, "danger")
        return redirect(url_for("item.item_details", item_id=item_id))

@item_bp.route("/item/<item_id>/resolve", methods=["POST"])
@login_required
def toggle_resolve(item_id):
    """Toggle item between open and resolved."""
    current_user = get_current_user()
    is_admin = (current_user.get("role") == "admin")

    success, msg = ItemService.toggle_resolution_status(
        item_id=item_id,
        user_id=current_user["_id"],
        is_admin=is_admin
    )

    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")

    return redirect(request.referrer or url_for("item.item_details", item_id=item_id))

@item_bp.route("/faq")
def faq():
    """Frequently Asked Questions and campus protocol guide."""
    return render_template("faq.html")
