import os
import uuid
import base64
import secrets
import logging
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId

from config import Config
from database.connection import get_db
from services.item_service import ItemService
from services.auth_service import validate_indian_mobile

logger = logging.getLogger(__name__)


def mask_phone_number(phone):
    """
    Mask a phone number safely.
    Example: '9731234512' -> '973XXXXXX12' (middle digits masked).
    Never returns the full number if masked is requested.
    """
    if not phone:
        return "XXXXXXXXXX"
    digits = "".join(c for c in str(phone) if c.isdigit())
    if len(digits) >= 10:
        return f"{digits[:3]}XXXXXX{digits[-2:]}"
    elif len(digits) >= 6:
        return f"{digits[:2]}{'X' * (len(digits) - 4)}{digits[-2:]}"
    return "XXXXXX" + digits[-2:] if len(digits) >= 2 else "XXXXXXXXXX"


class ClaimService:
    """Manages the lifecycle of lost and found claim verification requests and private contact sharing."""

    @staticmethod
    def save_verification_image(file_obj=None, base64_data=None):
        """
        Validates and stores a private verification image evidence in Config.PRIVATE_UPLOAD_FOLDER.
        Supports direct camera capture (base64 data URI) or file upload.
        Validates MIME magic bytes, size limit (5MB), and assigns secure server-generated filename.
        Returns (success: bool, filename_or_error: str).
        """
        upload_dir = Config.PRIVATE_UPLOAD_FOLDER
        os.makedirs(upload_dir, exist_ok=True)
        max_bytes = Config.MAX_CONTENT_LENGTH  # 5 MB

        raw_bytes = None
        ext = None

        try:
            if base64_data and str(base64_data).strip():
                # Direct camera capture data URI
                data_str = str(base64_data).strip()
                if "," in data_str:
                    _, b64_payload = data_str.split(",", 1)
                else:
                    b64_payload = data_str
                raw_bytes = base64.b64decode(b64_payload)
            elif file_obj and hasattr(file_obj, "read"):
                # File upload
                raw_bytes = file_obj.read()
            else:
                return False, "A verification photo is required before submitting your claim."

            if not raw_bytes or len(raw_bytes) == 0:
                return False, "The submitted photo is empty. Please capture or upload a valid photo."

            if len(raw_bytes) > max_bytes:
                return False, "Verification photo exceeds the 5 MB size limit. Please upload a smaller image."

            # Inspect magic bytes to confirm valid image format
            if raw_bytes.startswith(b"\xff\xd8\xff"):
                ext = "jpg"
            elif raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                ext = "png"
            elif raw_bytes.startswith(b"RIFF") and len(raw_bytes) >= 12 and raw_bytes[8:12] == b"WEBP":
                ext = "webp"
            else:
                return False, "Unsupported image format. Allowed formats are JPEG, PNG, and WebP."

            # Check if Cloudinary is configured
            from services.cloudinary_service import CloudinaryService, is_cloudinary_configured
            if is_cloudinary_configured():
                try:
                    folder = getattr(Config, "CLOUDINARY_FOLDER_VERIFICATION", "findmate/verification_photos")
                    upload_res = CloudinaryService.upload_image(raw_bytes, folder=folder)
                    secure_url = upload_res.get("secure_url")
                    if secure_url:
                        logger.info("Saved private verification photo to Cloudinary: %s", secure_url)
                        return True, secure_url
                    return False, "Cloudinary upload did not return a valid secure URL."
                except Exception as c_err:
                    logger.error("Cloudinary upload failed for verification photo: %s", c_err)
                    return False, f"Could not upload verification image: {str(c_err)}"

            # Generate secure unique server filename for local fallback
            filename = f"verify_{uuid.uuid4().hex}_{secrets.token_hex(4)}.{ext}"
            file_path = os.path.join(upload_dir, filename)

            with open(file_path, "wb") as f:
                f.write(raw_bytes)

            logger.info("Saved private verification photo locally: %s (%d bytes)", filename, len(raw_bytes))
            return True, filename

        except Exception as exc:
            logger.error("Error processing verification photo: %s", exc)
            return False, f"Could not process verification image: {str(exc)}"

    @staticmethod
    def submit_claim(item_id, user_id, message, verification_details, file_obj=None, base64_data=None, user_phone=None, user_email=""):
        """
        Submit a new claim request with required private verification photo.
        Enforces item existence, ownership rules, photo requirement, and mobile number registration.
        Returns (success: bool, message: str, claim_id: str|None).
        """
        item = ItemService.get_item_by_id(item_id)
        if not item:
            return False, "The requested item does not exist or has been removed.", None

        # Rule 1: Cannot claim your own item report
        if str(item.get("created_by")) == str(user_id):
            return False, "You cannot submit a claim on an item that you reported.", None

        # Rule 2: Cannot claim an already resolved/claimed item
        if item.get("resolution_status") in ("claimed", "resolved"):
            return False, "This item has already been claimed or resolved.", None

        # Rule 3: Validate input notes
        message = (message or "").strip()
        verification_details = (verification_details or "").strip()

        if not message or len(message) < 5:
            return False, "Please provide a brief message explaining your claim (at least 5 characters).", None

        if not verification_details or len(verification_details) < 5:
            return False, "Please provide specific verification details or proof of ownership (at least 5 characters).", None

        db = get_db()
        try:
            user_oid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
            item_oid = ObjectId(item_id) if not isinstance(item_id, ObjectId) else item_id
        except (InvalidId, TypeError):
            return False, "Invalid identifier.", None

        # Rule 4: Validate user mobile number for mutual contact sharing
        user_doc = db.users.find_one({"_id": user_oid})
        if not user_doc:
            return False, "User account not found.", None

        if not user_doc.get("phone_number"):
            if user_phone and str(user_phone).strip():
                is_valid, cleaned_phone = validate_indian_mobile(user_phone)
                if not is_valid:
                    return False, "Please provide a valid 10-digit mobile number (beginning with 6, 7, 8, or 9) to enable contact sharing.", None
                db.users.update_one(
                    {"_id": user_oid},
                    {"$set": {"phone_number": cleaned_phone, "updated_at": datetime.now(timezone.utc)}}
                )
            else:
                return False, "Please provide your 10-digit mobile number so contact sharing can be enabled upon claim approval.", None

        # Rule 5: Prevent duplicate pending claims by the same user on this item
        existing_claim = db.claim_requests.find_one({
            "item_id": item_oid,
            "requested_by": user_oid,
            "status": "pending"
        })
        if existing_claim:
            return False, "You already have a pending claim submitted for this item.", None

        # Rule 6: Verification photo is strictly REQUIRED
        photo_ok, photo_res = ClaimService.save_verification_image(file_obj=file_obj, base64_data=base64_data)
        if not photo_ok:
            return False, photo_res, None

        saved_filename = photo_res
        now = datetime.now(timezone.utc)

        claim_doc = {
            "item_id": item_oid,
            "requested_by": user_oid,
            "message": message,
            "verification_details": verification_details,
            "verification_image_path": saved_filename,
            "verification_status": "pending_verification",
            "decision_status": "pending",
            "status": "pending",
            "contact_sharing_enabled": False,
            "contact_sharing_enabled_at": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "contact_email": user_email or user_doc.get("email", ""),
            "reviewer_notes": "",
            "created_at": now,
            "updated_at": now
        }

        try:
            res = db.claim_requests.insert_one(claim_doc)
            logger.info("Submitted claim %s with verification photo %s for item %s by user %s",
                        res.inserted_id, saved_filename, item_id, user_id)
            return True, "Your verification photo and claim request have been securely submitted for review.", str(res.inserted_id)
        except Exception as exc:
            logger.error("Failed to insert claim request: %s", exc)
            if saved_filename and ("cloudinary.com" in str(saved_filename)):
                try:
                    from services.cloudinary_service import CloudinaryService
                    CloudinaryService.delete_image_by_url(saved_filename)
                except Exception:
                    pass
            elif saved_filename and not str(saved_filename).startswith(("http://", "https://")):
                file_path = os.path.join(Config.PRIVATE_UPLOAD_FOLDER, saved_filename)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
            return False, "Database error submitting claim. Please try again.", None

    @staticmethod
    def get_claim_by_id(claim_id):
        """Retrieve a single claim by its ObjectId."""
        if not claim_id:
            return None
        try:
            c_oid = ObjectId(claim_id) if not isinstance(claim_id, ObjectId) else claim_id
        except (InvalidId, TypeError):
            return None

        db = get_db()
        return db.claim_requests.find_one({"_id": c_oid})

    @staticmethod
    def get_claims_submitted_by_user(user_id):
        """
        Retrieve all claim requests created by the given user with item details.
        Applies mutual contact privacy rules: owner's phone number is only unmasked if approved.
        """
        try:
            user_oid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        except (InvalidId, TypeError):
            return []

        db = get_db()
        pipeline = [
            {"$match": {"requested_by": user_oid}},
            {"$sort": {"created_at": -1}},
            {
                "$lookup": {
                    "from": "items",
                    "localField": "item_id",
                    "foreignField": "_id",
                    "as": "item"
                }
            },
            {"$unwind": {"path": "$item", "preserveNullAndEmptyArrays": True}}
        ]
        claims = list(db.claim_requests.aggregate(pipeline))

        for c in claims:
            # Look up item owner user document
            owner_phone = ""
            if "item" in c and c["item"] and c["item"].get("created_by"):
                owner_doc = db.users.find_one({"_id": c["item"]["created_by"]})
                if owner_doc:
                    owner_phone = owner_doc.get("phone_number") or ""

            # Check if contact sharing is authorized for this claim
            if c.get("contact_sharing_enabled") is True and c.get("status") == "approved":
                c["owner_phone"] = owner_phone
                c["owner_phone_masked"] = mask_phone_number(owner_phone)
                c["contact_unlocked"] = True
            else:
                c["owner_phone"] = None  # Never expose raw phone number
                c["owner_phone_masked"] = mask_phone_number(owner_phone)
                c["contact_unlocked"] = False

        return claims

    @staticmethod
    def get_claims_received_for_user_items(user_id):
        """
        Retrieve all claim requests made on items reported by the given user.
        Includes claimant details and applies mutual contact privacy rules:
        claimant's phone number is only unmasked if approved.
        """
        try:
            user_oid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
        except (InvalidId, TypeError):
            return []

        db = get_db()
        user_items = list(db.items.find({"created_by": user_oid}, {"_id": 1}))
        item_ids = [it["_id"] for it in user_items]
        if not item_ids:
            return []

        pipeline = [
            {"$match": {"item_id": {"$in": item_ids}}},
            {"$sort": {"created_at": -1}},
            {
                "$lookup": {
                    "from": "items",
                    "localField": "item_id",
                    "foreignField": "_id",
                    "as": "item"
                }
            },
            {"$unwind": {"path": "$item", "preserveNullAndEmptyArrays": True}},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "requested_by",
                    "foreignField": "_id",
                    "as": "claimant"
                }
            },
            {"$unwind": {"path": "$claimant", "preserveNullAndEmptyArrays": True}}
        ]

        claims = list(db.claim_requests.aggregate(pipeline))
        for c in claims:
            claimant = c.get("claimant")
            claimant_phone = ""
            if claimant:
                claimant_phone = claimant.get("phone_number") or ""
                claimant.pop("password_hash", None)

            # Check if contact sharing is authorized for this claim
            if c.get("contact_sharing_enabled") is True and c.get("status") == "approved":
                c["claimant_phone"] = claimant_phone
                c["claimant_phone_masked"] = mask_phone_number(claimant_phone)
                c["contact_unlocked"] = True
            else:
                c["claimant_phone"] = None  # Never expose raw phone number
                c["claimant_phone_masked"] = mask_phone_number(claimant_phone)
                c["contact_unlocked"] = False

        return claims

    @staticmethod
    def get_all_claims(limit=50):
        """Admin helper: Retrieve all claims across the campus with item and claimant details."""
        db = get_db()
        pipeline = [
            {"$sort": {"created_at": -1}},
            {"$limit": limit},
            {
                "$lookup": {
                    "from": "items",
                    "localField": "item_id",
                    "foreignField": "_id",
                    "as": "item"
                }
            },
            {"$unwind": {"path": "$item", "preserveNullAndEmptyArrays": True}},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "requested_by",
                    "foreignField": "_id",
                    "as": "claimant"
                }
            },
            {"$unwind": {"path": "$claimant", "preserveNullAndEmptyArrays": True}}
        ]
        claims = list(db.claim_requests.aggregate(pipeline))
        for c in claims:
            if "claimant" in c and c["claimant"]:
                c["claimant"].pop("password_hash", None)
        return claims

    @staticmethod
    def review_claim(claim_id, action, reviewer_notes, reviewer_user_id, is_admin=False):
        """
        Approve or reject a claim's verification photo.
        Enforces strict authorization: only item owner or administrator can review.
        Prevents self-approval.
        On approval:
          - Sets verification_status to 'approved'
          - Enables mutual contact sharing ONLY for the two users on this specific claim
          - Updates item resolution status to 'claimed' for coordination
        On rejection:
          - Sets verification_status to 'rejected'
          - Keeps contact numbers strictly masked
        """
        try:
            c_oid = ObjectId(claim_id) if not isinstance(claim_id, ObjectId) else claim_id
        except (InvalidId, TypeError):
            return False, "Invalid claim ID."

        db = get_db()
        claim = db.claim_requests.find_one({"_id": c_oid})
        if not claim:
            return False, "Claim request not found."

        item = db.items.find_one({"_id": claim["item_id"]})
        if not item:
            return False, "Associated item could not be found."

        # Ownership authorization: must be creator of the item or admin
        item_owner_id = str(item.get("created_by", ""))
        if str(reviewer_user_id) != item_owner_id and not is_admin:
            return False, "Unauthorized: Only the listing reporter or an administrator can review this claim."

        # Prevent approving own claim (defense-in-depth)
        if str(claim.get("requested_by")) == str(reviewer_user_id) and not is_admin:
            return False, "Unauthorized: You cannot review your own claim."

        action = (action or "").lower().strip()
        if action not in ("approve", "reject"):
            return False, "Action must be either 'approve' or 'reject'."

        now = datetime.now(timezone.utc)

        if action == "approve":
            # Ensure the reviewer (owner) also has a registered phone number for mutual exchange
            reviewer_doc = db.users.find_one({"_id": ObjectId(reviewer_user_id)})
            if reviewer_doc and not reviewer_doc.get("phone_number"):
                return False, "Please add your verified 10-digit mobile number to your profile before approving contact sharing."

            # Update this specific claim to approved and enable contact sharing
            db.claim_requests.update_one(
                {"_id": c_oid},
                {
                    "$set": {
                        "status": "approved",
                        "verification_status": "approved",
                        "decision_status": "approved",
                        "contact_sharing_enabled": True,
                        "contact_sharing_enabled_at": now,
                        "reviewer_notes": reviewer_notes or "Verification photo approved. Handover authorized.",
                        "reviewed_by": ObjectId(reviewer_user_id),
                        "reviewed_at": now,
                        "updated_at": now
                    }
                }
            )

            # Update item resolution status to 'claimed' (active in coordination)
            db.items.update_one(
                {"_id": item["_id"]},
                {
                    "$set": {
                        "resolution_status": "claimed",
                        "updated_at": now
                    }
                }
            )

            logger.info("Claim %s approved by %s. Contact sharing unlocked.", claim_id, reviewer_user_id)
            return True, "Verification approved! Contact numbers are now available to both students."

        else:
            # Reject action: ensure contact sharing remains disabled
            db.claim_requests.update_one(
                {"_id": c_oid},
                {
                    "$set": {
                        "status": "rejected",
                        "verification_status": "rejected",
                        "decision_status": "rejected",
                        "contact_sharing_enabled": False,
                        "contact_sharing_enabled_at": None,
                        "reviewer_notes": reviewer_notes or "Proof of ownership did not match verification details.",
                        "reviewed_by": ObjectId(reviewer_user_id),
                        "reviewed_at": now,
                        "updated_at": now
                    }
                }
            )
            logger.info("Claim %s rejected by %s.", claim_id, reviewer_user_id)
            return True, "Claim rejected. Contact numbers remain locked."

    @staticmethod
    def mark_handover_resolved(claim_id, reviewer_user_id, is_admin=False):
        """
        Mark an item as physically returned/resolved after successful handover.
        Separate from photo verification approval.
        """
        try:
            c_oid = ObjectId(claim_id) if not isinstance(claim_id, ObjectId) else claim_id
        except (InvalidId, TypeError):
            return False, "Invalid claim ID."

        db = get_db()
        claim = db.claim_requests.find_one({"_id": c_oid})
        if not claim:
            return False, "Claim not found."

        item = db.items.find_one({"_id": claim["item_id"]})
        if not item:
            return False, "Item not found."

        item_owner_id = str(item.get("created_by", ""))
        claimant_id = str(claim.get("requested_by", ""))
        user_str = str(reviewer_user_id)

        # Either owner, claimant, or admin can confirm physical handover
        if user_str != item_owner_id and user_str != claimant_id and not is_admin:
            return False, "Unauthorized: Only the parties involved or an admin can confirm item handover."

        now = datetime.now(timezone.utc)
        db.items.update_one(
            {"_id": item["_id"]},
            {
                "$set": {
                    "resolution_status": "resolved",
                    "updated_at": now
                }
            }
        )
        return True, "Item handover confirmed! Status marked as Resolved."
