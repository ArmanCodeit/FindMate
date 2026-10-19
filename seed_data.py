"""
seed_data.py - Populates findmate_db with realistic demo campus users and items
Strictly matching the Google Stitch UI reference screenshots.
"""

import sys
import logging
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from database.connection import get_db, init_db_indexes

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def seed_database():
    """Insert demo users and items matching Stitch screenshots."""
    db = get_db()
    init_db_indexes()

    logger.info("Starting database seeding for findmate_db...")

    # 1. Seed Users
    users_data = [
        {
            "full_name": "Riya Sharma",
            "email": "riya.sharma@hawaii.edu",
            "password_hash": generate_password_hash("campus123"),
            "role": "student",
            "student_id": "UH-104928",
            "is_active": True,
            "created_at": datetime.now(timezone.utc) - timedelta(days=45),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "full_name": "Alex Miller",
            "email": "alex.m@hawaii.edu",
            "password_hash": generate_password_hash("campus123"),
            "role": "student",
            "student_id": "UH-301982",
            "is_active": True,
            "created_at": datetime.now(timezone.utc) - timedelta(days=30),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "full_name": "Marcus Lee (Campus Admin)",
            "email": "admin@findmate.campus.edu",
            "password_hash": generate_password_hash("admin123"),
            "role": "admin",
            "student_id": "STAFF-001",
            "is_active": True,
            "created_at": datetime.now(timezone.utc) - timedelta(days=120),
            "updated_at": datetime.now(timezone.utc)
        }
    ]

    user_map = {}
    for u in users_data:
        existing = db.users.find_one({"email": u["email"]})
        if not existing:
            res = db.users.insert_one(u)
            user_map[u["email"]] = res.inserted_id
            logger.info("Inserted user: %s (%s)", u["full_name"], u["email"])
        else:
            user_map[u["email"]] = existing["_id"]
            logger.info("User already exists: %s", u["email"])

    riya_id = user_map["riya.sharma@hawaii.edu"]
    alex_id = user_map["alex.m@hawaii.edu"]
    admin_id = user_map["admin@findmate.campus.edu"]

    # 2. Seed Items (Matching Stitch screenshots)
    items_data = [
        {
            "title": "Green UH Hoodie",
            "category": "Apparel & Gear",
            "report_type": "found",
            "location": "Campus Center",
            "date_lost_or_found": "2025-10-14",
            "academic_term": "Fall 2025",
            "description": "Green university athletic fleece hoodie folded neatly on wooden study desk. Size L, athletics typography printed on chest.",
            "additional_details": "Size L, collegiate athletics print on front chest, clean condition.",
            "contact_preference": "direct",
            "image_filename": "green_hoodie.jpg",
            "report_id": "#FD-2025-1044",
            "created_by": riya_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "title": "Blue Hydroflask",
            "category": "Water Bottles",
            "report_type": "lost",
            "location": "Hamilton Library",
            "date_lost_or_found": "2025-10-13",
            "academic_term": "Fall 2025",
            "description": "Blue 32oz wide-mouth Hydroflask with cute dog stickers, a green collegiate sticker, and slight dent at base. Please contact if you found it near the 1st floor quiet study desks or printing hub.",
            "additional_details": "Has a 'Good Vibes' holographic sticker on the back and a black flex cap straw lid. Small scrape along bottom circumference.",
            "contact_preference": "direct",
            "image_filename": "blue_hydroflask.jpg",
            "report_id": "#LF-2025-1047",
            "created_by": riya_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(hours=5),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "title": "AirPods (2nd Gen)",
            "category": "Electronics",
            "report_type": "found",
            "location": "Gilmore Hall",
            "date_lost_or_found": "2025-10-12",
            "academic_term": "Fall 2025",
            "description": "White wireless Apple AirPods in charging case found on wooden study desk next to open notebook.",
            "additional_details": "White charging case, small faint scratch next to front status LED.",
            "contact_preference": "desk",
            "image_filename": "airpods.jpg",
            "report_id": "#FD-2025-1048",
            "created_by": alex_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(hours=14),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "title": "Student ID Card",
            "category": "IDs & Wallets",
            "report_type": "lost",
            "location": "Moore Hall",
            "date_lost_or_found": "2025-10-11",
            "academic_term": "Fall 2025",
            "description": "Student identity card with green collegiate lanyard lost between lecture hall and courtyard.",
            "additional_details": "Name on card starts with 'Sarah', green fabric lanyard with clasp.",
            "contact_preference": "direct",
            "image_filename": "student_id.jpg",
            "report_id": "#LF-2025-1049",
            "created_by": alex_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(days=1),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "title": "Laptop Charger (USB-C)",
            "category": "Electronics",
            "report_type": "found",
            "location": "Campus Center",
            "date_lost_or_found": "2025-10-10",
            "academic_term": "Fall 2025",
            "description": "Black 65W USB-C laptop charger with coiled power cable and branded velcro strap.",
            "additional_details": "Lenovo 65W AC Adapter with original velcro cable organizer.",
            "contact_preference": "desk",
            "image_filename": "laptop_charger.jpg",
            "report_id": "#FD-2025-1050",
            "created_by": riya_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(days=2),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "title": "Black Leather Wallet",
            "category": "IDs & Wallets",
            "report_type": "lost",
            "location": "Sinclair Hall",
            "date_lost_or_found": "2025-10-09",
            "academic_term": "Fall 2025",
            "description": "Black leather bifold wallet with slight corner wear. Left near window study area.",
            "additional_details": "Contains campus meal pass and driver license.",
            "contact_preference": "desk",
            "image_filename": "leather_wallet.jpg",
            "report_id": "#LF-2025-1051",
            "created_by": riya_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(days=3),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "title": "Graphing Calculator TI-84",
            "category": "Calculators",
            "report_type": "found",
            "location": "Physical Science Bldg",
            "date_lost_or_found": "2025-10-08",
            "academic_term": "Fall 2025",
            "description": "TI-84 Plus CE graphing calculator left on lecture table following calculus class.",
            "additional_details": "Subtle metallic gold name initials inside slide cover.",
            "contact_preference": "desk",
            "image_filename": "calculator.jpg",
            "report_id": "#FD-2025-1052",
            "created_by": alex_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(days=4),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "title": "Dorm Room Keyring",
            "category": "Keys",
            "report_type": "found",
            "location": "Hale Aloha Courtyard",
            "date_lost_or_found": "2025-10-07",
            "academic_term": "Fall 2025",
            "description": "Set of brass keys with dark green lanyard and black dorm barcode access tag.",
            "additional_details": "Brass key stamped with 'DORM 301' and black access barcode tag.",
            "contact_preference": "desk",
            "image_filename": "dorm_keys.jpg",
            "report_id": "#FD-2025-1053",
            "created_by": alex_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(days=5),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "title": "Silver MacBook Air 13\"",
            "category": "Electronics",
            "report_type": "found",
            "location": "Hamilton Library",
            "date_lost_or_found": "2025-10-06",
            "academic_term": "Fall 2025",
            "description": "Silver MacBook Air laptop turned in to 2nd floor desk. Has student club stickers on top lid.",
            "additional_details": "Sustainability club and library stickers on front cover.",
            "contact_preference": "desk",
            "image_filename": "silver_macbook.jpg",
            "report_id": "#FD-2025-1054",
            "created_by": riya_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(days=6),
            "updated_at": datetime.now(timezone.utc)
        },
        {
            "title": "Tortoiseshell Reading Glasses",
            "category": "Eyewear",
            "report_type": "found",
            "location": "Athletics Complex Gym",
            "date_lost_or_found": "2025-10-05",
            "academic_term": "Fall 2025",
            "description": "Brown tortoiseshell frames inside brown leather magnetic case on spectator bleachers.",
            "additional_details": "Tortoiseshell frames, prescription reading lenses, leather magnetic case.",
            "contact_preference": "desk",
            "image_filename": "reading_glasses.jpg",
            "report_id": "#FD-2025-1055",
            "created_by": alex_id,
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc) - timedelta(days=7),
            "updated_at": datetime.now(timezone.utc)
        }
    ]

    item_ids = []
    for it in items_data:
        existing = db.items.find_one({"report_id": it["report_id"]})
        if not existing:
            res = db.items.insert_one(it)
            item_ids.append(res.inserted_id)
            logger.info("Inserted item: %s (%s)", it["title"], it["report_id"])
        else:
            item_ids.append(existing["_id"])

    # 3. Seed Sample Claim Request
    if item_ids:
        sample_item_id = item_ids[0]  # Green UH Hoodie reported by Riya
        existing_claim = db.claim_requests.find_one({"item_id": sample_item_id, "requested_by": alex_id})
        if not existing_claim:
            claim_doc = {
                "item_id": sample_item_id,
                "requested_by": alex_id,
                "message": "Hi Riya, I think this is my athletics hoodie! I left it at Campus Center after study session.",
                "verification_details": "It has my name tag 'Alex M.' written in small black marker on the inner neck wash label.",
                "contact_email": "alex.m@hawaii.edu",
                "status": "pending",
                "reviewer_notes": "",
                "created_at": datetime.now(timezone.utc) - timedelta(minutes=45),
                "updated_at": datetime.now(timezone.utc)
            }
            db.claim_requests.insert_one(claim_doc)
            logger.info("Inserted sample pending claim request for testing")

    logger.info("Database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
