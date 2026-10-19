"""
Automated Test Suite for FindMate Campus Lost & Found
Runs against an isolated test database (findmate_test_db) to preserve development data.
"""

import unittest
import os
from bson import ObjectId
from werkzeug.security import check_password_hash

# Set test environment config
os.environ["DB_NAME"] = "findmate_test_db"
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-testing"

from app import create_app
from database.connection import get_db, init_db_indexes
from services.auth_service import AuthService
from services.item_service import ItemService
from services.claim_service import ClaimService

class FindMateTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = cls.app.test_client()
        cls.db = get_db()
        init_db_indexes()

    def setUp(self):
        # Clean collections before each test
        self.db.users.delete_many({})
        self.db.items.delete_many({})
        self.db.claim_requests.delete_many({})

    def tearDown(self):
        self.db.users.delete_many({})
        self.db.items.delete_many({})
        self.db.claim_requests.delete_many({})

    # 1. Authentication & Registration Tests
    def test_user_registration_success(self):
        success, msg, user = AuthService.register_user(
            full_name="Jane Doe",
            email="jane.doe@campus.edu",
            password="securepassword123",
            confirm_password="securepassword123",
            student_id="UH-998811"
        )
        self.assertTrue(success)
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "student")
        
        # Verify in DB
        db_user = self.db.users.find_one({"email": "jane.doe@campus.edu"})
        self.assertIsNotNone(db_user)
        self.assertTrue(check_password_hash(db_user["password_hash"], "securepassword123"))

    def test_user_registration_duplicate_email(self):
        AuthService.register_user("Jane Doe", "jane@campus.edu", "pass123", "pass123")
        success, msg, user = AuthService.register_user("Jane 2", "jane@campus.edu", "pass123", "pass123")
        self.assertFalse(success)
        self.assertIn("already exists", msg)

    def test_user_registration_mismatched_password(self):
        success, msg, user = AuthService.register_user("Jane", "jane@campus.edu", "pass123", "mismatch")
        self.assertFalse(success)
        self.assertIn("Passwords do not match", msg)

    def test_user_authentication(self):
        AuthService.register_user("Student One", "student@campus.edu", "campuspass", "campuspass")
        # Valid
        ok, msg, user = AuthService.authenticate_user("student@campus.edu", "campuspass")
        self.assertTrue(ok)
        self.assertEqual(user["email"], "student@campus.edu")
        # Invalid
        fail, msg, user = AuthService.authenticate_user("student@campus.edu", "wrongpass")
        self.assertFalse(fail)

    # 2. Item CRUD & Validation Tests
    def test_item_create_and_retrieve(self):
        _, _, user = AuthService.register_user("Reporter", "rep@campus.edu", "pass123", "pass123")
        
        data = {
            "title": "Blue Water Bottle",
            "category": "Water Bottles",
            "report_type": "lost",
            "location": "Hamilton Library",
            "date_lost_or_found": "2025-10-15",
            "description": "Lost blue hydroflask with dog stickers near quiet study.",
            "additional_details": "Initial 'JD' scratched on bottom"
        }
        
        success, msg, item_id = ItemService.create_item(data, None, user["_id"])
        self.assertTrue(success)
        self.assertIsNotNone(item_id)

        # Retrieve
        item = ItemService.get_item_by_id(item_id)
        self.assertIsNotNone(item)
        self.assertEqual(item["title"], "Blue Water Bottle")
        self.assertEqual(item["resolution_status"], "open")
        self.assertEqual(item["reporter"]["full_name"], "Reporter")

    def test_item_filtering_and_search(self):
        _, _, u = AuthService.register_user("User", "u@campus.edu", "pass123", "pass123")
        ItemService.create_item({
            "title": "AirPods Pro",
            "category": "Electronics",
            "report_type": "found",
            "location": "Gilmore Hall",
            "description": "White case found on desk",
        }, None, u["_id"])
        
        ItemService.create_item({
            "title": "Calculator TI-84",
            "category": "Calculators",
            "report_type": "lost",
            "location": "Campus Center",
            "description": "Black graphing calculator",
        }, None, u["_id"])

        # Filter by type=found
        res = ItemService.get_items({"type": "found"})
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["items"][0]["title"], "AirPods Pro")

        # Search query
        res_search = ItemService.get_items({"q": "Calculator"})
        self.assertEqual(res_search["total"], 1)
        self.assertEqual(res_search["items"][0]["title"], "Calculator TI-84")

    def test_item_ownership_update_and_delete(self):
        _, _, u1 = AuthService.register_user("Owner", "owner@campus.edu", "pass123", "pass123")
        _, _, u2 = AuthService.register_user("Stranger", "stranger@campus.edu", "pass123", "pass123")
        
        _, _, item_id = ItemService.create_item({
            "title": "My Jacket",
            "category": "Apparel & Gear",
            "report_type": "found",
            "location": "Campus Center",
            "description": "Warm black jacket",
        }, None, u1["_id"])

        # Stranger cannot edit
        ok, msg = ItemService.update_item(item_id, {"title": "Hacked", "description": "Hacked desc"}, None, u2["_id"])
        self.assertFalse(ok)
        self.assertIn("Unauthorized", msg)

        # Owner can edit
        ok, msg = ItemService.update_item(item_id, {"title": "Updated Jacket", "description": "Updated desc"}, None, u1["_id"])
        self.assertTrue(ok)

        # Stranger cannot delete
        del_ok, _ = ItemService.delete_item(item_id, u2["_id"])
        self.assertFalse(del_ok)

        # Owner can delete
        del_ok, _ = ItemService.delete_item(item_id, u1["_id"])
        self.assertTrue(del_ok)
        self.assertIsNone(ItemService.get_item_by_id(item_id))

    # 3. Claim Request Workflow Tests
    def test_claim_submission_and_approval(self):
        sample_photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        _, _, finder = AuthService.register_user("Finder", "finder@campus.edu", "pass123", "pass123", phone_number="9876543210")
        _, _, owner = AuthService.register_user("Owner", "owner@campus.edu", "pass123", "pass123", phone_number="8765432109")

        _, _, item_id = ItemService.create_item({
            "title": "Keys found on bench",
            "category": "Keys",
            "report_type": "found",
            "location": "West Lawn",
            "description": "Brass keys with green lanyard",
        }, None, finder["_id"])

        # Finder cannot claim their own found item
        fail_self, msg, _ = ClaimService.submit_claim(item_id, finder["_id"], "mine", "proof", base64_data=sample_photo)
        self.assertFalse(fail_self)
        self.assertIn("cannot submit a claim on an item that you reported", msg)

        # Photo required: fail if photo missing
        fail_no_photo, msg_no_photo, _ = ClaimService.submit_claim(
            item_id=item_id,
            user_id=owner["_id"],
            message="These are my keys",
            verification_details="Room 301 engraved",
            base64_data=None,
            file_obj=None
        )
        self.assertFalse(fail_no_photo)
        self.assertIn("photo is required", msg_no_photo.lower())

        # Owner submits valid claim with photo
        ok, msg, claim_id = ClaimService.submit_claim(
            item_id=item_id,
            user_id=owner["_id"],
            message="These are my dorm keys!",
            verification_details="Room 301 engraved on brass key",
            base64_data=sample_photo,
            user_email="owner@campus.edu"
        )
        self.assertTrue(ok)
        self.assertIsNotNone(claim_id)

        # Verify claim document has private image path and pending status
        claim = ClaimService.get_claim_by_id(claim_id)
        self.assertIsNotNone(claim.get("verification_image_path"))
        self.assertEqual(claim.get("status"), "pending")
        self.assertFalse(claim.get("contact_sharing_enabled"))

        # Prevent duplicate pending claim
        dup_ok, dup_msg, _ = ClaimService.submit_claim(
            item_id=item_id,
            user_id=owner["_id"],
            message="Trying again",
            verification_details="Same proof",
            base64_data=sample_photo
        )
        self.assertFalse(dup_ok)
        self.assertIn("already have a pending claim", dup_msg)

        # Finder approves claim
        app_ok, app_msg = ClaimService.review_claim(
            claim_id=claim_id,
            action="approve",
            reviewer_notes="Verified room number.",
            reviewer_user_id=finder["_id"]
        )
        self.assertTrue(app_ok)

        # Verify contact sharing enabled on approved claim
        updated_claim = ClaimService.get_claim_by_id(claim_id)
        self.assertEqual(updated_claim["status"], "approved")
        self.assertTrue(updated_claim["contact_sharing_enabled"])

        # Verify item resolution status updated to 'claimed'
        updated_item = ItemService.get_item_by_id(item_id)
        self.assertEqual(updated_item["resolution_status"], "claimed")

    # 4. Web Endpoint Tests
    def test_public_pages_render(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"FindMate", resp.data)

        resp_browse = self.client.get("/browse")
        self.assertEqual(resp_browse.status_code, 200)

        resp_faq = self.client.get("/faq")
        self.assertEqual(resp_faq.status_code, 200)

        resp_health = self.client.get("/health")
        self.assertEqual(resp_health.status_code, 200)

    # 5. Contact Number & Date Validation Tests
    def test_contact_number_generation_and_format(self):
        import re
        from datetime import datetime, timedelta
        _, _, user = AuthService.register_user("Contact Tester", "ctest@campus.edu", "pass123", "pass123")
        
        # Test Lost Item
        today_str = datetime.now().strftime("%Y-%m-%d")
        ok_lost, _, lost_id = ItemService.create_item({
            "title": "Lost Wallet",
            "category": "IDs & Wallets",
            "report_type": "lost",
            "location": "Campus Center",
            "date_lost_or_found": today_str,
            "description": "Brown leather wallet lost near dining area",
        }, None, user["_id"])
        self.assertTrue(ok_lost)
        lost_item = ItemService.get_item_by_id(lost_id)
        self.assertIn("contact_number", lost_item)
        contact_num = lost_item["contact_number"]
        self.assertTrue(bool(re.match(r"^[789]\d{9}$", contact_num)))
        self.assertEqual(len(contact_num), 10)
        self.assertIn(contact_num[0], ("7", "8", "9"))

        # Test Found Item
        ok_found, _, found_id = ItemService.create_item({
            "title": "Found AirTag",
            "category": "Electronics",
            "report_type": "found",
            "location": "Sinclair Hall",
            "date_lost_or_found": today_str,
            "description": "Silver Apple AirTag found under desk",
        }, None, user["_id"])
        self.assertTrue(ok_found)
        found_item = ItemService.get_item_by_id(found_id)
        self.assertIn("contact_number", found_item)
        self.assertTrue(bool(re.match(r"^[789]\d{9}$", found_item["contact_number"])))

        # Numbers must be unique
        self.assertNotEqual(lost_item["contact_number"], found_item["contact_number"])

    def test_contact_number_preserved_on_edit(self):
        from datetime import datetime
        _, _, user = AuthService.register_user("Editor", "edit@campus.edu", "pass123", "pass123")
        today_str = datetime.now().strftime("%Y-%m-%d")
        _, _, item_id = ItemService.create_item({
            "title": "Calculus Book",
            "category": "Books & Notebooks",
            "report_type": "lost",
            "location": "Keller Hall",
            "date_lost_or_found": today_str,
            "description": "Stewart Calculus 9th edition with green cover",
        }, None, user["_id"])

        original_item = ItemService.get_item_by_id(item_id)
        original_contact = original_item["contact_number"]
        self.assertIsNotNone(original_contact)

        # Edit item
        edit_ok, msg = ItemService.update_item(
            item_id=item_id,
            data={
                "title": "Calculus Book (Early Transcendentals)",
                "category": "Books & Notebooks",
                "location": "Keller Hall Rm 101",
                "description": "Updated description with room details",
                "date_lost_or_found": today_str
            },
            file_storage=None,
            user_id=user["_id"]
        )
        self.assertTrue(edit_ok)
        updated_item = ItemService.get_item_by_id(item_id)
        self.assertEqual(updated_item["contact_number"], original_contact)

    def test_future_date_rejected(self):
        from datetime import datetime, timedelta
        _, _, user = AuthService.register_user("Future Date Tester", "future@campus.edu", "pass123", "pass123")
        future_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")

        # Lost report with future date
        fail_lost, msg_lost, item_id = ItemService.create_item({
            "title": "Future Item",
            "category": "Electronics",
            "report_type": "lost",
            "location": "Library",
            "date_lost_or_found": future_date,
            "description": "Will lose this in the future",
        }, None, user["_id"])
        self.assertFalse(fail_lost)
        self.assertIn("future", msg_lost.lower())
        self.assertIsNone(item_id)

        # Found report with future date
        fail_found, msg_found, _ = ItemService.create_item({
            "title": "Future Found Item",
            "category": "Keys",
            "report_type": "found",
            "location": "Library",
            "date_lost_or_found": future_date,
            "description": "Will find this tomorrow",
        }, None, user["_id"])
        self.assertFalse(fail_found)
        self.assertIn("future", msg_found.lower())

    def test_past_date_and_legacy_items_without_contact(self):
        from datetime import datetime, timezone
        from bson import ObjectId
        # Direct legacy insert without contact_number
        legacy_doc = {
            "title": "Old Umbrella",
            "category": "Other",
            "report_type": "found",
            "location": "Paradise Palm Cafe",
            "date_lost_or_found": "2024-05-10",
            "description": "Black compact umbrella",
            "report_id": "#FD-2024-0001",
            "created_by": ObjectId(),
            "resolution_status": "open",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        res = self.db.items.insert_one(legacy_doc)
        item = ItemService.get_item_by_id(res.inserted_id)
        self.assertIsNotNone(item)
        self.assertIsNone(item.get("contact_number"))

        # Verify get_items handles it gracefully
        listing = ItemService.get_items({"q": "Umbrella"})
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["title"], "Old Umbrella")

    # 6. Photo Verification Privacy & Mutual Phone Number Unlock Tests
    def test_verification_photo_privacy_and_access_control(self):
        sample_photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        _, _, owner = AuthService.register_user("Owner Bob", "bob@campus.edu", "pass123", "pass123", phone_number="9876543210")
        _, _, claimant = AuthService.register_user("Claimant Alice", "alice@campus.edu", "pass123", "pass123", phone_number="8765432109")
        _, _, stranger = AuthService.register_user("Stranger Sam", "sam@campus.edu", "pass123", "pass123", phone_number="7654321098")

        _, _, item_id = ItemService.create_item({
            "title": "Lost Gold Watch",
            "category": "Jewelry",
            "report_type": "lost",
            "location": "Gym",
            "description": "Engraved gold watch",
        }, None, owner["_id"])

        ok, _, claim_id = ClaimService.submit_claim(
            item_id=item_id,
            user_id=claimant["_id"],
            message="I found your gold watch!",
            verification_details="Engraving matches initials BW",
            base64_data=sample_photo,
            user_email="alice@campus.edu"
        )
        self.assertTrue(ok)

        # Unauthenticated visitor cannot view private photo (redirects to login)
        resp_anon = self.client.get(f"/claims/{claim_id}/verification-photo")
        self.assertEqual(resp_anon.status_code, 302)

        # Stranger cannot view private photo (403 Forbidden)
        self.client.post("/login", data={"email": "sam@campus.edu", "password": "pass123"})
        resp_stranger = self.client.get(f"/claims/{claim_id}/verification-photo")
        self.assertEqual(resp_stranger.status_code, 403)
        self.client.get("/logout")

        # Item owner can view private photo (200 OK)
        self.client.post("/login", data={"email": "bob@campus.edu", "password": "pass123"})
        resp_owner = self.client.get(f"/claims/{claim_id}/verification-photo")
        self.assertEqual(resp_owner.status_code, 200)
        self.client.get("/logout")

        # Claimant can view their own submitted verification photo (200 OK)
        self.client.post("/login", data={"email": "alice@campus.edu", "password": "pass123"})
        resp_claimant = self.client.get(f"/claims/{claim_id}/verification-photo")
        self.assertEqual(resp_claimant.status_code, 200)
        self.client.get("/logout")

    def test_mutual_phone_number_masking_and_unlock(self):
        sample_photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        _, _, owner = AuthService.register_user("Owner Dan", "dan@campus.edu", "pass123", "pass123", phone_number="9876543210")
        _, _, claimant1 = AuthService.register_user("Claimant 1", "c1@campus.edu", "pass123", "pass123", phone_number="8765432109")
        _, _, claimant2 = AuthService.register_user("Claimant 2", "c2@campus.edu", "pass123", "pass123", phone_number="7654321098")

        _, _, item_id = ItemService.create_item({
            "title": "Lost Wallet",
            "category": "Wallets",
            "report_type": "lost",
            "location": "Campus Center",
            "description": "Black leather wallet",
        }, None, owner["_id"])

        # Claimant 1 submits claim
        ok1, _, claim_id1 = ClaimService.submit_claim(
            item_id=item_id,
            user_id=claimant1["_id"],
            message="Found it at dining hall",
            verification_details="Driver license name matches",
            base64_data=sample_photo
        )
        self.assertTrue(ok1)

        # Claimant 2 submits claim on same item
        ok2, _, claim_id2 = ClaimService.submit_claim(
            item_id=item_id,
            user_id=claimant2["_id"],
            message="Found it on chair",
            verification_details="Credit card matches",
            base64_data=sample_photo
        )
        self.assertTrue(ok2)

        # BEFORE approval: Both users see masked phone numbers
        rec_claims = ClaimService.get_claims_received_for_user_items(owner["_id"])
        c1_rec = next(c for c in rec_claims if str(c["_id"]) == claim_id1)
        self.assertFalse(c1_rec["contact_unlocked"])
        self.assertIsNone(c1_rec["claimant_phone"])  # Raw phone must NOT be present
        self.assertIn("XXXXXX", c1_rec["claimant_phone_masked"])

        sent_claims_1 = ClaimService.get_claims_submitted_by_user(claimant1["_id"])
        c1_sent = next(c for c in sent_claims_1 if str(c["_id"]) == claim_id1)
        self.assertFalse(c1_sent["contact_unlocked"])
        self.assertIsNone(c1_sent["owner_phone"])  # Raw phone must NOT be present
        self.assertIn("XXXXXX", c1_sent["owner_phone_masked"])

        # Wrong user cannot approve claim
        fail_unauth, unauth_msg = ClaimService.review_claim(
            claim_id=claim_id1,
            action="approve",
            reviewer_notes="Unauthorized approval",
            reviewer_user_id=claimant2["_id"]
        )
        self.assertFalse(fail_unauth)
        self.assertIn("Unauthorized", unauth_msg)

        # Owner approves Claimant 1's photo
        app_ok, _ = ClaimService.review_claim(
            claim_id=claim_id1,
            action="approve",
            reviewer_notes="Photo verified",
            reviewer_user_id=owner["_id"]
        )
        self.assertTrue(app_ok)

        # AFTER approval: Owner and Claimant 1 can see each other's full phone numbers
        rec_claims_after = ClaimService.get_claims_received_for_user_items(owner["_id"])
        c1_rec_after = next(c for c in rec_claims_after if str(c["_id"]) == claim_id1)
        self.assertTrue(c1_rec_after["contact_unlocked"])
        self.assertEqual(c1_rec_after["claimant_phone"], "8765432109")

        sent_claims_after = ClaimService.get_claims_submitted_by_user(claimant1["_id"])
        c1_sent_after = next(c for c in sent_claims_after if str(c["_id"]) == claim_id1)
        self.assertTrue(c1_sent_after["contact_unlocked"])
        self.assertEqual(c1_sent_after["owner_phone"], "9876543210")

        # MULTI-CLAIM ISOLATION: Claimant 2's claim remains locked!
        c2_rec_after = next(c for c in rec_claims_after if str(c["_id"]) == claim_id2)
        self.assertFalse(c2_rec_after["contact_unlocked"])
        self.assertIsNone(c2_rec_after["claimant_phone"])

        sent_claims_2_after = ClaimService.get_claims_submitted_by_user(claimant2["_id"])
        c2_sent_after = next(c for c in sent_claims_2_after if str(c["_id"]) == claim_id2)
        self.assertFalse(c2_sent_after["contact_unlocked"])
        self.assertIsNone(c2_sent_after["owner_phone"])

    def test_claim_rejection_keeps_numbers_masked(self):
        sample_photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        _, _, owner = AuthService.register_user("Owner Roy", "roy@campus.edu", "pass123", "pass123", phone_number="9876543210")
        _, _, claimant = AuthService.register_user("Claimant Mia", "mia@campus.edu", "pass123", "pass123", phone_number="8765432109")

        _, _, item_id = ItemService.create_item({
            "title": "Water Bottle",
            "category": "Other",
            "report_type": "found",
            "location": "Gym",
            "description": "Green bottle",
        }, None, owner["_id"])

        ok, _, claim_id = ClaimService.submit_claim(
            item_id=item_id,
            user_id=claimant["_id"],
            message="My bottle",
            verification_details="Has dent on bottom",
            base64_data=sample_photo
        )
        self.assertTrue(ok)

        # Owner rejects claim
        rej_ok, _ = ClaimService.review_claim(
            claim_id=claim_id,
            action="reject",
            reviewer_notes="No dent visible on bottle.",
            reviewer_user_id=owner["_id"]
        )
        self.assertTrue(rej_ok)

        # Numbers remain locked and masked
        rec_claims = ClaimService.get_claims_received_for_user_items(owner["_id"])
        c_rec = next(c for c in rec_claims if str(c["_id"]) == claim_id)
        self.assertFalse(c_rec["contact_unlocked"])
        self.assertIsNone(c_rec["claimant_phone"])

        sent_claims = ClaimService.get_claims_submitted_by_user(claimant["_id"])
        c_sent = next(c for c in sent_claims if str(c["_id"]) == claim_id)
        self.assertFalse(c_sent["contact_unlocked"])
        self.assertIsNone(c_sent["owner_phone"])

    def test_missing_phone_blocks_contact_sharing(self):
        sample_photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        _, _, owner = AuthService.register_user("Owner NoPhone", "nophone_owner@campus.edu", "pass123", "pass123", phone_number=None)
        _, _, claimant = AuthService.register_user("Claimant NoPhone", "nophone_claimant@campus.edu", "pass123", "pass123", phone_number=None)

        _, _, item_id = ItemService.create_item({
            "title": "Calculator",
            "category": "Electronics",
            "report_type": "lost",
            "location": "Keller Hall",
            "description": "TI-84 silver",
        }, None, owner["_id"])

        # 1. Claimant without phone tries to submit claim without phone -> Rejected
        fail_sub1, msg1, _ = ClaimService.submit_claim(
            item_id=item_id,
            user_id=claimant["_id"],
            message="Found your calculator",
            verification_details="Serial code matches",
            base64_data=sample_photo,
            user_phone=None
        )
        self.assertFalse(fail_sub1)
        self.assertIn("mobile number", msg1.lower())

        # 2. Claimant provides invalid phone -> Rejected
        fail_sub2, msg2, _ = ClaimService.submit_claim(
            item_id=item_id,
            user_id=claimant["_id"],
            message="Found your calculator",
            verification_details="Serial code matches",
            base64_data=sample_photo,
            user_phone="12345"
        )
        self.assertFalse(fail_sub2)
        self.assertIn("valid 10-digit", msg2.lower())

        # 3. Claimant provides valid 10-digit mobile number -> Accepted and saved
        ok_sub, msg3, claim_id = ClaimService.submit_claim(
            item_id=item_id,
            user_id=claimant["_id"],
            message="Found your calculator",
            verification_details="Serial code matches",
            base64_data=sample_photo,
            user_phone="9876543210"
        )
        self.assertTrue(ok_sub)
        self.assertIsNotNone(claim_id)

        # Verify claimant profile has phone saved
        updated_claimant = self.db.users.find_one({"_id": claimant["_id"]})
        self.assertEqual(updated_claimant.get("phone_number"), "9876543210")

        # 4. Owner tries to approve while missing phone number -> Blocked
        fail_app, msg_app = ClaimService.review_claim(
            claim_id=claim_id,
            action="approve",
            reviewer_notes="Photo matches",
            reviewer_user_id=owner["_id"]
        )
        self.assertFalse(fail_app)
        self.assertIn("mobile number", msg_app.lower())

        # 5. Owner adds phone number to profile
        self.db.users.update_one({"_id": owner["_id"]}, {"$set": {"phone_number": "8765432109"}})

        # 6. Now approval succeeds and contact numbers unlock
        ok_app, _ = ClaimService.review_claim(
            claim_id=claim_id,
            action="approve",
            reviewer_notes="Photo matches",
            reviewer_user_id=owner["_id"]
        )
        self.assertTrue(ok_app)

        # Verify mutual phone access is unlocked
        rec_claims = ClaimService.get_claims_received_for_user_items(owner["_id"])
        c_rec = next(c for c in rec_claims if str(c["_id"]) == claim_id)
        self.assertTrue(c_rec["contact_unlocked"])
        self.assertEqual(c_rec["claimant_phone"], "9876543210")


if __name__ == "__main__":
    unittest.main()
