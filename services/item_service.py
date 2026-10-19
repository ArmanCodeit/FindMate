import os
import re
import uuid
import random
import logging
from datetime import datetime, timezone, date
from PIL import Image
from bson import ObjectId
from bson.errors import InvalidId
from werkzeug.utils import secure_filename

from config import Config
from database.connection import get_db

logger = logging.getLogger(__name__)

# Standard categories and campus hubs for FindMate
CATEGORIES = [
    "Electronics",
    "IDs & Wallets",
    "Apparel & Gear",
    "Bags & Backpacks",
    "Keys",
    "Water Bottles",
    "Calculators",
    "Books & Notebooks",
    "Eyewear",
    "Other"
]

LOCATIONS = [
    "Hamilton Library",
    "Campus Center",
    "Gilmore Hall",
    "Moore Hall",
    "Physical Science Bldg",
    "Sinclair Hall",
    "Student Union Dining Hall",
    "Athletics Complex Gym",
    "Hale Aloha Courtyard",
    "East-West Center",
    "Kuykendall Hall",
    "West Lawn Benches",
    "Science Quadrangle"
]

class ItemService:
    """Handles item reporting, listing, searching, filtering, and persistence."""

    @staticmethod
    def allowed_file(filename):
        """Check if file extension is supported."""
        if not filename or "." not in filename:
            return False
        ext = filename.rsplit(".", 1)[1].lower()
        return ext in Config.ALLOWED_EXTENSIONS

    @staticmethod
    def save_uploaded_image(file_storage):
        """
        Validate and save uploaded image safely.
        Validates both file extension and image header/content using Pillow.
        Returns randomized filename or None.
        """
        if not file_storage or file_storage.filename == "":
            return None

        orig_filename = secure_filename(file_storage.filename)
        if not ItemService.allowed_file(orig_filename):
            raise ValueError("Unsupported image file format. Please upload JPG, PNG, WEBP, or GIF.")

        ext = orig_filename.rsplit(".", 1)[1].lower()

        try:
            # Verify file content is a valid image using Pillow
            image = Image.open(file_storage.stream)
            image.verify()  # Verifies that it's an authentic image file
            
            # Reset stream pointer
            file_storage.stream.seek(0)
        except Exception as exc:
            logger.error("Image validation failed: %s", exc)
            raise ValueError("The uploaded file is corrupt or is not a valid image.") from exc

        # Check if Cloudinary is configured
        from services.cloudinary_service import CloudinaryService, is_cloudinary_configured
        if is_cloudinary_configured():
            try:
                folder = getattr(Config, "CLOUDINARY_FOLDER_ITEMS", "findmate/items")
                upload_res = CloudinaryService.upload_image(file_storage, folder=folder)
                secure_url = upload_res.get("secure_url")
                if secure_url:
                    logger.info("Saved validated image to Cloudinary: %s", secure_url)
                    return secure_url
                raise ValueError("Cloudinary upload failed to return a secure URL.")
            except ValueError:
                raise
            except Exception as c_err:
                logger.error("Cloudinary upload failed: %s", c_err)
                raise ValueError(f"Failed to upload image to cloud storage: {str(c_err)}") from c_err

        # Local storage fallback
        safe_filename = f"{uuid.uuid4().hex}_{int(datetime.now().timestamp())}.{ext}"
        destination_path = os.path.join(Config.UPLOAD_FOLDER, safe_filename)
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

        try:
            file_storage.stream.seek(0)
            image = Image.open(file_storage.stream)
            # Convert RGBA to RGB for JPEG saving if needed
            if ext in ("jpg", "jpeg") and image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            
            image.save(destination_path, quality=90, optimize=True)
            logger.info("Saved validated image locally: %s", safe_filename)
            return safe_filename
        except Exception as exc:
            logger.error("Image save failed: %s", exc)
            if os.path.exists(destination_path):
                os.remove(destination_path)
            raise ValueError("The uploaded file is corrupt or is not a valid image.") from exc

    @staticmethod
    def is_valid_contact_number(number):
        """Validate that number is exactly 10 digits starting with 7, 8, or 9."""
        if not isinstance(number, str):
            return False
        return bool(re.match(r"^[789]\d{9}$", number))

    @staticmethod
    def generate_unique_contact_number():
        """
        Generate a random 10-digit contact number starting with 7, 8, or 9.
        Ensures uniqueness against existing records in MongoDB items collection.
        """
        db = get_db()
        first_digits = ["7", "8", "9"]
        for _ in range(50):
            first = random.choice(first_digits)
            rest = "".join(str(random.randint(0, 9)) for _ in range(9))
            candidate = f"{first}{rest}"

            if not ItemService.is_valid_contact_number(candidate):
                continue

            # Ensure number is unique across items
            if db.items.count_documents({"contact_number": candidate}) == 0:
                return candidate

        # Fallback if loop finishes
        first = random.choice(first_digits)
        rest = "".join(str(random.randint(0, 9)) for _ in range(9))
        return f"{first}{rest}"

    @staticmethod
    def generate_report_id(report_type):
        """Generate human-readable report ID like #LF-2025-1047."""
        prefix = "LF" if report_type == "lost" else "FD"
        year = datetime.now().year
        rand_num = random.randint(1000, 9999)
        return f"#{prefix}-{year}-{rand_num}"

    @staticmethod
    def create_item(data, file_storage, user_id):
        """
        Validate inputs and create a new lost or found report.
        Returns (success: bool, message: str, item_id: str|None).
        """
        title = data.get("title", "").strip()
        category = data.get("category", "").strip()
        report_type = data.get("report_type", "found").strip().lower()
        location = data.get("location", "").strip()
        date_str = data.get("date_lost_or_found", "").strip()
        academic_term = data.get("academic_term", "").strip()
        description = data.get("description", "").strip()
        additional_details = data.get("additional_details", "").strip()
        contact_preference = data.get("contact_preference", "direct").strip()

        # Validations
        if not title or len(title) < 3:
            return False, "Item title must be at least 3 characters long.", None
        if len(title) > 120:
            return False, "Item title cannot exceed 120 characters.", None

        if report_type not in ("lost", "found"):
            return False, "Report type must be either 'lost' or 'found'.", None

        if not category:
            return False, "Please select an item category.", None

        if not location:
            return False, "Please specify the campus building or location.", None

        # Backend Date Validation: cannot be in the future
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return False, "Please enter a valid date in YYYY-MM-DD format.", None

        today = datetime.now().date()
        if parsed_date > today:
            action_word = "lost" if report_type == "lost" else "found"
            return False, f"The date cannot be in the future. Please select today ({today.strftime('%d %b %Y')}) or an earlier date when the item was {action_word}.", None

        if not description or len(description) < 5:
            return False, "Please provide a public description (at least 5 characters).", None

        # Generate unique 10-digit contact number starting with 7, 8, or 9
        contact_number = ItemService.generate_unique_contact_number()
        if not ItemService.is_valid_contact_number(contact_number):
            return False, "Failed to generate a valid 10-digit contact number. Please try again.", None

        # Process Image
        image_filename = None
        saved_file_path = None
        if file_storage and file_storage.filename != "":
            try:
                image_filename = ItemService.save_uploaded_image(file_storage)
                if image_filename and not image_filename.startswith(("http://", "https://")):
                    saved_file_path = os.path.join(Config.UPLOAD_FOLDER, image_filename)
            except ValueError as val_err:
                return False, str(val_err), None

        report_id = ItemService.generate_report_id(report_type)

        now = datetime.now(timezone.utc)
        item_doc = {
            "title": title,
            "category": category,
            "report_type": report_type,
            "location": location,
            "date_lost_or_found": date_str,
            "description": description,
            "additional_details": additional_details,
            "contact_preference": contact_preference,
            "contact_number": contact_number,
            "image_filename": image_filename,
            "report_id": report_id,
            "created_by": ObjectId(user_id) if isinstance(user_id, str) else user_id,
            "resolution_status": "open",  # 'open', 'claimed', 'resolved'
            "created_at": now,
            "updated_at": now
        }
        if academic_term:
            item_doc["academic_term"] = academic_term

        db = get_db()
        try:
            result = db.items.insert_one(item_doc)
            logger.info("Successfully created item %s (id: %s) with contact %s", report_id, result.inserted_id, contact_number)
            return True, f"Report submitted successfully! Item {report_id} is now on the registry.", str(result.inserted_id)
        except Exception as exc:
            logger.error("Database error while creating item: %s", exc)
            # Cleanup uploaded image on failure
            if image_filename and ("cloudinary.com" in str(image_filename) or "res.cloudinary.com" in str(image_filename)):
                try:
                    from services.cloudinary_service import CloudinaryService
                    CloudinaryService.delete_image_by_url(image_filename)
                except Exception:
                    pass
            elif saved_file_path and os.path.exists(saved_file_path):
                os.remove(saved_file_path)
            return False, "Failed to save item to database. Please try again.", None

    @staticmethod
    def get_item_by_id(item_id):
        """Retrieve single item document with creator details."""
        if not item_id:
            return None
        try:
            oid = ObjectId(item_id) if not isinstance(item_id, ObjectId) else item_id
        except (InvalidId, TypeError):
            return None

        db = get_db()
        pipeline = [
            {"$match": {"_id": oid}},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "created_by",
                    "foreignField": "_id",
                    "as": "reporter"
                }
            },
            {
                "$unwind": {
                    "path": "$reporter",
                    "preserveNullAndEmptyArrays": True
                }
            }
        ]
        results = list(db.items.aggregate(pipeline))
        if not results:
            return None

        item = results[0]
        # Sanitize reporter info (never leak password)
        if "reporter" in item and item["reporter"]:
            item["reporter"].pop("password_hash", None)
        return item

    @staticmethod
    def get_items(filters=None, page=1, per_page=8, sort_by="newest"):
        """
        Query items from MongoDB with filtering, search, sorting, and pagination.
        Returns { 'items': list, 'total': int, 'page': int, 'pages': int, 'per_page': int }
        """
        db = get_db()
        query = {}
        filters = filters or {}

        # 1. Search Query (Text or Regex)
        search_term = filters.get("q", "").strip()
        if search_term:
            # Safe case-insensitive regex search on title, description, or location
            safe_term = "".join([c for c in search_term if c.isalnum() or c in (" ", "-", "_", "'", "\"")])
            query["$or"] = [
                {"title": {"$regex": safe_term, "$options": "i"}},
                {"description": {"$regex": safe_term, "$options": "i"}},
                {"location": {"$regex": safe_term, "$options": "i"}}
            ]

        # 2. Report Type Filter
        report_type = filters.get("type", "").strip().lower()
        if report_type in ("lost", "found"):
            query["report_type"] = report_type

        # 3. Resolution Status Filter
        status = filters.get("status", "").strip().lower()
        if status in ("open", "claimed", "resolved"):
            query["resolution_status"] = status
        elif report_type == "resolved":
            query["resolution_status"] = {"$in": ["claimed", "resolved"]}

        # 4. Category Filter
        category = filters.get("category", "").strip()
        if category and category != "All" and category != "Category":
            query["category"] = category

        # 5. Building / Location Filter
        building = filters.get("building", "").strip()
        if building and building != "All" and building != "Building":
            query["location"] = {"$regex": f"^{building}", "$options": "i"}

        # 6. Date Filter
        date_filter = filters.get("date", "").strip()
        if date_filter:
            query["date_lost_or_found"] = date_filter

        # 7. Sorting
        sort_field = [("created_at", -1)]
        if sort_by == "oldest":
            sort_field = [("created_at", 1)]
        elif sort_by == "title":
            sort_field = [("title", 1)]

        # Ensure pagination parameters are valid integers
        try:
            page = max(1, int(page))
        except (ValueError, TypeError):
            page = 1
        try:
            per_page = max(1, min(100, int(per_page)))
        except (ValueError, TypeError):
            per_page = 8

        total_entries = db.items.count_documents(query)
        total_pages = max(1, (total_entries + per_page - 1) // per_page)
        if page > total_pages and total_entries > 0:
            page = total_pages

        skip_count = (page - 1) * per_page
        cursor = db.items.find(query).sort(sort_field).skip(skip_count).limit(per_page)
        items_list = list(cursor)

        return {
            "items": items_list,
            "total": total_entries,
            "page": page,
            "pages": total_pages,
            "per_page": per_page,
            "start_index": skip_count + 1 if total_entries > 0 else 0,
            "end_index": min(skip_count + per_page, total_entries)
        }

    @staticmethod
    def get_summary_stats():
        """Get summary statistics for badges and dashboards."""
        db = get_db()
        total_items = db.items.count_documents({})
        lost_items = db.items.count_documents({"report_type": "lost"})
        found_items = db.items.count_documents({"report_type": "found"})
        resolved_items = db.items.count_documents({"resolution_status": {"$in": ["claimed", "resolved"]}})
        open_lost = db.items.count_documents({"report_type": "lost", "resolution_status": "open"})
        open_found = db.items.count_documents({"report_type": "found", "resolution_status": "open"})
        total_users = db.users.count_documents({})
        pending_claims = db.claim_requests.count_documents({"status": "pending"})
        total_claims = db.claim_requests.count_documents({})
        approved_claims = db.claim_requests.count_documents({"status": "approved"})

        # Calculate actual claim verification accuracy from real claims in MongoDB
        if total_claims > 0:
            claim_accuracy_val = f"{int(round((approved_claims / total_claims) * 100))}%"
        else:
            claim_accuracy_val = "0%"

        return {
            "total": total_items,
            "lost": lost_items,
            "found": found_items,
            "resolved": resolved_items,
            "open_lost": open_lost,
            "open_found": open_found,
            "total_users": total_users,
            "pending_claims": pending_claims,
            "total_claims": total_claims,
            "claim_accuracy": claim_accuracy_val,
            "active_hubs_count": len(LOCATIONS)
        }

    @staticmethod
    def get_recent_items(limit=4, category=None):
        """Retrieve recent verified intake items for the homepage."""
        db = get_db()
        query = {}
        if category and category != "All":
            query["category"] = category
        return list(db.items.find(query).sort("created_at", -1).limit(limit))

    @staticmethod
    def get_nearby_items(location, exclude_id=None, limit=4):
        """Retrieve items from the same building/zone for details page."""
        db = get_db()
        query = {}
        if location:
            # Match building keyword
            main_loc = location.split()[0]
            query["location"] = {"$regex": main_loc, "$options": "i"}
        if exclude_id:
            try:
                oid = ObjectId(exclude_id) if not isinstance(exclude_id, ObjectId) else exclude_id
                query["_id"] = {"$ne": oid}
            except Exception:
                pass
        return list(db.items.find(query).sort("created_at", -1).limit(limit))

    @staticmethod
    def update_item(item_id, data, file_storage, user_id, is_admin=False):
        """Update report details with authorization check."""
        item = ItemService.get_item_by_id(item_id)
        if not item:
            return False, "Item not found."

        # Verify authorization
        creator_id = str(item.get("created_by", ""))
        if str(user_id) != creator_id and not is_admin:
            return False, "Unauthorized: You do not have permission to edit this report."

        title = data.get("title", "").strip()
        category = data.get("category", "").strip()
        location = data.get("location", "").strip()
        description = data.get("description", "").strip()
        additional_details = data.get("additional_details", "").strip()
        status = data.get("resolution_status", item.get("resolution_status", "open")).strip()

        if not title or len(title) < 3:
            return False, "Item title must be at least 3 characters."
        if not description or len(description) < 5:
            return False, "Public description must be at least 5 characters."

        update_fields = {
            "title": title,
            "category": category or item.get("category"),
            "location": location or item.get("location"),
            "description": description,
            "additional_details": additional_details,
            "resolution_status": status,
            "updated_at": datetime.now(timezone.utc)
        }

        # If date_lost_or_found is supplied, validate it is not in the future
        date_str = data.get("date_lost_or_found", "").strip()
        if date_str:
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                today = datetime.now().date()
                if parsed_date > today:
                    return False, f"The date cannot be in the future. Please select today ({today.strftime('%d %b %Y')}) or an earlier date."
                update_fields["date_lost_or_found"] = date_str
            except ValueError:
                return False, "Please enter a valid date in YYYY-MM-DD format."

        # Optional new image upload
        if file_storage and file_storage.filename != "":
            try:
                new_filename = ItemService.save_uploaded_image(file_storage)
                update_fields["image_filename"] = new_filename
            except ValueError as e:
                return False, str(e)

        db = get_db()
        db.items.update_one({"_id": item["_id"]}, {"$set": update_fields})
        logger.info("Updated item %s by user %s", item_id, user_id)
        return True, "Item report updated successfully."

    @staticmethod
    def delete_item(item_id, user_id, is_admin=False):
        """Delete report document and linked claims with authorization check."""
        item = ItemService.get_item_by_id(item_id)
        if not item:
            return False, "Item not found."

        creator_id = str(item.get("created_by", ""))
        if str(user_id) != creator_id and not is_admin:
            return False, "Unauthorized: You do not have permission to delete this report."

        db = get_db()
        # Delete item document
        db.items.delete_one({"_id": item["_id"]})
        # Delete linked claims
        db.claim_requests.delete_many({"item_id": item["_id"]})

        # Remove custom uploaded image if not standard seed image
        image_fname = item.get("image_filename")
        if image_fname:
            if "cloudinary.com" in str(image_fname) or "res.cloudinary.com" in str(image_fname):
                try:
                    from services.cloudinary_service import CloudinaryService
                    CloudinaryService.delete_image_by_url(image_fname)
                except Exception:
                    pass
            elif not image_fname.endswith((".jpg", ".png")):
                filepath = os.path.join(Config.UPLOAD_FOLDER, image_fname)
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass

        logger.info("Deleted item %s by user %s", item_id, user_id)
        return True, "Item report deleted successfully."

    @staticmethod
    def toggle_resolution_status(item_id, user_id, is_admin=False):
        """Toggle an item between open and resolved."""
        item = ItemService.get_item_by_id(item_id)
        if not item:
            return False, "Item not found."

        creator_id = str(item.get("created_by", ""))
        if str(user_id) != creator_id and not is_admin:
            return False, "Unauthorized."

        current_status = item.get("resolution_status", "open")
        new_status = "resolved" if current_status == "open" else "open"

        db = get_db()
        db.items.update_one(
            {"_id": item["_id"]},
            {"$set": {"resolution_status": new_status, "updated_at": datetime.now(timezone.utc)}}
        )
        return True, f"Item marked as {new_status}."
