import os
import logging
from flask import Blueprint, request, redirect, url_for, flash, render_template, abort, send_from_directory, current_app
from config import Config
from services.auth_service import login_required, get_current_user
from services.claim_service import ClaimService
from services.item_service import ItemService

logger = logging.getLogger(__name__)
claim_bp = Blueprint("claim", __name__)


@claim_bp.route("/item/<item_id>/claim", methods=["POST"])
@login_required
def submit_claim(item_id):
    """
    Submit a claim request with required private verification photo.
    Accepts camera photo (base64) or device file upload, plus phone number if missing.
    """
    current_user = get_current_user()
    message = request.form.get("message", "").strip()
    verification_details = request.form.get("verification_details", "").strip()
    user_phone = request.form.get("phone_number", "").strip()

    # Capture from device camera (base64 string) or direct file input
    base64_photo = request.form.get("verification_photo_data", "").strip()
    file_photo = request.files.get("verification_photo_file")

    success, msg, claim_id = ClaimService.submit_claim(
        item_id=item_id,
        user_id=current_user["_id"],
        message=message,
        verification_details=verification_details,
        file_obj=file_photo,
        base64_data=base64_photo,
        user_phone=user_phone,
        user_email=current_user.get("email", "")
    )

    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")

    return redirect(url_for("item.item_details", item_id=item_id))


@claim_bp.route("/claims")
@login_required
def claims_overview():
    """View claim requests submitted and received by current user with mutual contact sharing."""
    current_user = get_current_user()
    claims_sent = ClaimService.get_claims_submitted_by_user(current_user["_id"])
    claims_received = ClaimService.get_claims_received_for_user_items(current_user["_id"])

    return render_template(
        "claim_requests.html",
        claims_sent=claims_sent,
        claims_received=claims_received,
        current_user=current_user
    )


@claim_bp.route("/claims/<claim_id>/verification-photo")
@login_required
def get_verification_photo(claim_id):
    """
    Protected endpoint: Serves a claim's private verification image ONLY to:
    1. The owner of the relevant item.
    2. The claimant who submitted the claim.
    3. An authorized campus administrator.
    Any unauthorized user or guest receives 403 Forbidden.
    """
    current_user = get_current_user()
    claim = ClaimService.get_claim_by_id(claim_id)
    if not claim:
        abort(404, description="Claim not found.")

    item = ItemService.get_item_by_id(claim["item_id"])
    if not item:
        abort(404, description="Associated item not found.")

    user_id_str = str(current_user["_id"])
    is_claimant = (user_id_str == str(claim.get("requested_by", "")))
    is_item_owner = (user_id_str == str(item.get("created_by", "")))
    is_admin = (current_user.get("role") == "admin")

    if not (is_claimant or is_item_owner or is_admin):
        logger.warning(
            "Unauthorized access attempt to verification photo for claim %s by user %s (%s)",
            claim_id, user_id_str, current_user.get("email")
        )
        abort(403, description="Access denied: You are not authorized to view this private verification photo.")

    filename = claim.get("verification_image_path")
    if not filename:
        abort(404, description="No verification photo is attached to this claim.")

    if filename.startswith("http://") or filename.startswith("https://"):
        try:
            import urllib.request
            req = urllib.request.Request(filename, headers={"User-Agent": "FindMate/1.0"})
            with urllib.request.urlopen(req, timeout=10) as remote_res:
                data = remote_res.read()
                content_type = remote_res.headers.get("Content-Type", "image/jpeg")
                from flask import Response
                response = Response(data, mimetype=content_type)
                response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
                return response
        except Exception as e:
            logger.error("Failed to stream verification photo from cloud URL: %s", e)
            return redirect(filename)

    private_dir = Config.PRIVATE_UPLOAD_FOLDER
    file_path = os.path.join(private_dir, filename)
    if not os.path.isfile(file_path):
        abort(404, description="Verification photo file not found on server.")

    response = send_from_directory(private_dir, filename)
    response.headers["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
    return response


@claim_bp.route("/claims/<claim_id>/review", methods=["POST"])
@login_required
def review_claim(claim_id):
    """Approve or reject a claim's verification photo and unlock mutual phone numbers."""
    current_user = get_current_user()
    action = request.form.get("action", "").lower().strip()
    reviewer_notes = request.form.get("reviewer_notes", "").strip()
    is_admin = (current_user.get("role") == "admin")

    success, msg = ClaimService.review_claim(
        claim_id=claim_id,
        action=action,
        reviewer_notes=reviewer_notes,
        reviewer_user_id=current_user["_id"],
        is_admin=is_admin
    )

    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")

    return redirect(request.referrer or url_for("claim.claims_overview"))


@claim_bp.route("/claims/<claim_id>/resolve", methods=["POST"])
@login_required
def resolve_handover(claim_id):
    """Confirm physical handover and mark item as resolved."""
    current_user = get_current_user()
    is_admin = (current_user.get("role") == "admin")

    success, msg = ClaimService.mark_handover_resolved(
        claim_id=claim_id,
        reviewer_user_id=current_user["_id"],
        is_admin=is_admin
    )

    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")

    return redirect(request.referrer or url_for("claim.claims_overview"))
