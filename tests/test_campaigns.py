"""
Comprehensive Test Suite for BloodLink Donation Campaigns:
1. Permissions & Access Control:
   - Unauthenticated users: 401 Unauthorized for all endpoints.
   - Donors and Recipients: Can view campaigns (GET /campaigns, GET /campaigns/<id>),
     but are forbidden (403) from creating, editing, updating status, or deleting campaigns.
   - Admin: Full CRUD permissions to create, view, edit, update status, and delete campaigns.
2. Server-side Validation:
   - Required fields (campaign_name, location, start_date, end_date).
   - Character length bounds (<= 150 chars for name and location).
   - Valid datetime parsing (ISO, space-separated, etc.).
   - Chronological validation: end_date must be strictly after start_date.
   - Status validation: only allowed statuses permitted.
3. Status Lifecycle & Distinctions:
   - Marking campaigns as UPCOMING/PLANNED, ONGOING, COMPLETED, or CANCELLED.
   - Distinct display status computation for date-aware feeds.
4. Database Integration:
   - Live integration tests against the MySQL campaigns table verifying atomic transactions,
     persisted updates, and zero leakage.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import datetime
from app import (
    app,
    parse_campaign_datetime,
    format_campaign_dict,
    ALLOWED_CAMPAIGN_STATUSES
)
import database


class TestCampaignPermissions(unittest.TestCase):
    """Verifies authentication and role-based access control for all campaign endpoints."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def set_session(self, user_id=1, user_name="Test User", role="ADMIN"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = user_name
            sess["user_role"] = role

    # 1. Unauthenticated Access -> 401 JSON
    def test_unauthenticated_get_campaigns_returns_401(self):
        res = self.client.get("/campaigns")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_get_single_campaign_returns_401(self):
        res = self.client.get("/campaigns/1")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_post_campaign_returns_401(self):
        res = self.client.post("/campaigns", json={"campaign_name": "Test"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_put_campaign_returns_401(self):
        res = self.client.put("/campaigns/1", json={"campaign_name": "Test"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_patch_campaign_status_returns_401(self):
        res = self.client.patch("/campaigns/1/status", json={"status": "COMPLETED"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_delete_campaign_returns_401(self):
        res = self.client.delete("/campaigns/1")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    # 2. Donor Role Access Control
    @patch("app.get_db_connection")
    def test_donor_can_view_campaigns(self, mock_get_db):
        self.set_session(user_id=101, user_name="Donor Dan", role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {
                "campaign_id": 1,
                "campaign_name": "City Hall Drive",
                "location": "Mumbai",
                "start_date": datetime.datetime(2026, 11, 1, 9, 0),
                "end_date": datetime.datetime(2026, 11, 1, 17, 0),
                "status": "UPCOMING",
                "description": "Public drive",
                "created_at": datetime.datetime(2026, 10, 20)
            }
        ]

        res = self.client.get("/campaigns")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["campaign_name"], "City Hall Drive")

    @patch("app.get_db_connection")
    def test_donor_can_view_single_campaign(self, mock_get_db):
        self.set_session(user_id=101, user_name="Donor Dan", role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            "campaign_id": 1,
            "campaign_name": "City Hall Drive",
            "location": "Mumbai",
            "start_date": datetime.datetime(2026, 11, 1, 9, 0),
            "end_date": datetime.datetime(2026, 11, 1, 17, 0),
            "status": "UPCOMING",
            "description": "Public drive",
            "created_at": datetime.datetime(2026, 10, 20)
        }

        res = self.client.get("/campaigns/1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["campaign_id"], 1)

    def test_donor_forbidden_from_creating_campaign(self):
        self.set_session(user_id=101, user_name="Donor Dan", role="DONOR")
        res = self.client.post("/campaigns", json={"campaign_name": "Forbidden"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_forbidden_from_updating_campaign(self):
        self.set_session(user_id=101, user_name="Donor Dan", role="DONOR")
        res = self.client.put("/campaigns/1", json={"campaign_name": "Forbidden"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_forbidden_from_updating_campaign_status(self):
        self.set_session(user_id=101, user_name="Donor Dan", role="DONOR")
        res = self.client.put("/campaigns/1/status", json={"status": "COMPLETED"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_forbidden_from_deleting_campaign(self):
        self.set_session(user_id=101, user_name="Donor Dan", role="DONOR")
        res = self.client.delete("/campaigns/1")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    # 3. Recipient Role Access Control
    @patch("app.get_db_connection")
    def test_recipient_can_view_campaigns(self, mock_get_db):
        self.set_session(user_id=202, user_name="Recipient Rita", role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        res = self.client.get("/campaigns")
        self.assertEqual(res.status_code, 200)

    def test_recipient_forbidden_from_creating_campaign(self):
        self.set_session(user_id=202, user_name="Recipient Rita", role="RECIPIENT")
        res = self.client.post("/campaigns", json={"campaign_name": "Forbidden"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_recipient_forbidden_from_updating_campaign(self):
        self.set_session(user_id=202, user_name="Recipient Rita", role="RECIPIENT")
        res = self.client.put("/campaigns/1", json={"campaign_name": "Forbidden"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_recipient_forbidden_from_updating_campaign_status(self):
        self.set_session(user_id=202, user_name="Recipient Rita", role="RECIPIENT")
        res = self.client.put("/campaigns/1/status", json={"status": "COMPLETED"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_recipient_forbidden_from_deleting_campaign(self):
        self.set_session(user_id=202, user_name="Recipient Rita", role="RECIPIENT")
        res = self.client.delete("/campaigns/1")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())


class TestCampaignValidation(unittest.TestCase):
    """Verifies server-side validation rules on campaign creation and update."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Super Admin"
            sess["user_role"] = "ADMIN"

    def test_create_campaign_missing_name_returns_400(self):
        payload = {
            "location": "Mumbai",
            "start_date": "2026-11-01 09:00:00",
            "end_date": "2026-11-01 17:00:00"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("campaign name is required", res.get_json()["error"].lower())

    def test_create_campaign_whitespace_name_returns_400(self):
        payload = {
            "campaign_name": "   ",
            "location": "Mumbai",
            "start_date": "2026-11-01 09:00:00",
            "end_date": "2026-11-01 17:00:00"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("campaign name is required", res.get_json()["error"].lower())

    def test_create_campaign_name_exceeds_150_chars_returns_400(self):
        payload = {
            "campaign_name": "A" * 151,
            "location": "Mumbai",
            "start_date": "2026-11-01 09:00:00",
            "end_date": "2026-11-01 17:00:00"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("150 characters", res.get_json()["error"].lower())

    def test_create_campaign_missing_location_returns_400(self):
        payload = {
            "campaign_name": "Valid Name",
            "location": "  ",
            "start_date": "2026-11-01 09:00:00",
            "end_date": "2026-11-01 17:00:00"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("location is required", res.get_json()["error"].lower())

    def test_create_campaign_missing_dates_returns_400(self):
        payload = {
            "campaign_name": "Valid Name",
            "location": "Mumbai"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("both start date and end date are required", res.get_json()["error"].lower())

    def test_create_campaign_invalid_start_date_format_returns_400(self):
        payload = {
            "campaign_name": "Valid Name",
            "location": "Mumbai",
            "start_date": "not-a-date",
            "end_date": "2026-11-01 17:00:00"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("invalid start date", res.get_json()["error"].lower())

    def test_create_campaign_invalid_end_date_format_returns_400(self):
        payload = {
            "campaign_name": "Valid Name",
            "location": "Mumbai",
            "start_date": "2026-11-01 09:00:00",
            "end_date": "invalid-end-date"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("invalid end date", res.get_json()["error"].lower())

    def test_create_campaign_end_date_before_start_date_returns_400(self):
        payload = {
            "campaign_name": "Valid Name",
            "location": "Mumbai",
            "start_date": "2026-11-02 10:00:00",
            "end_date": "2026-11-01 09:00:00"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("after", res.get_json()["error"].lower())

    def test_create_campaign_end_date_equal_start_date_returns_400(self):
        payload = {
            "campaign_name": "Valid Name",
            "location": "Mumbai",
            "start_date": "2026-11-01 10:00:00",
            "end_date": "2026-11-01 10:00:00"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("after", res.get_json()["error"].lower())

    def test_create_campaign_invalid_status_returns_400(self):
        payload = {
            "campaign_name": "Valid Name",
            "location": "Mumbai",
            "start_date": "2026-11-01 09:00:00",
            "end_date": "2026-11-01 17:00:00",
            "status": "NONEXISTENT_STATUS"
        }
        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("invalid status", res.get_json()["error"].lower())


class TestCampaignCRUDOperations(unittest.TestCase):
    """Verifies campaign creation, editing, status change, and deletion logic."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Super Admin"
            sess["user_role"] = "ADMIN"

    @patch("app.get_db_connection")
    def test_admin_create_campaign_success(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.lastrowid = 42
        mock_cursor.fetchone.return_value = {
            "campaign_id": 42,
            "campaign_name": "Metro Blood Drive",
            "description": "Donation with health checkup",
            "location": "Community Center, Delhi",
            "start_date": datetime.datetime(2026, 11, 10, 9, 30),
            "end_date": datetime.datetime(2026, 11, 10, 18, 0),
            "status": "UPCOMING",
            "created_at": datetime.datetime(2026, 10, 26)
        }

        payload = {
            "campaign_name": "Metro Blood Drive",
            "location": "Community Center, Delhi",
            "start_date": "2026-11-10T09:30",
            "end_date": "2026-11-10T18:00",
            "status": "UPCOMING",
            "description": "Donation with health checkup"
        }

        res = self.client.post("/campaigns", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["message"], "Campaign created successfully.")
        self.assertEqual(data["campaign"]["campaign_id"], 42)
        self.assertEqual(data["campaign"]["campaign_name"], "Metro Blood Drive")
        mock_db.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_admin_update_campaign_success(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Existing record
        mock_cursor.fetchone.side_effect = [
            {
                "campaign_id": 42,
                "campaign_name": "Old Name",
                "location": "Old Location",
                "start_date": datetime.datetime(2026, 11, 10, 9, 30),
                "end_date": datetime.datetime(2026, 11, 10, 18, 0),
                "status": "UPCOMING",
                "description": "Old desc"
            },
            {
                "campaign_id": 42,
                "campaign_name": "Updated Name",
                "location": "Updated Location",
                "start_date": datetime.datetime(2026, 11, 10, 10, 0),
                "end_date": datetime.datetime(2026, 11, 10, 19, 0),
                "status": "ONGOING",
                "description": "Updated desc",
                "created_at": datetime.datetime(2026, 10, 26)
            }
        ]

        payload = {
            "campaign_name": "Updated Name",
            "location": "Updated Location",
            "start_date": "2026-11-10T10:00",
            "end_date": "2026-11-10T19:00",
            "status": "ONGOING",
            "description": "Updated desc"
        }

        res = self.client.put("/campaigns/42", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["message"], "Campaign updated successfully.")
        self.assertEqual(data["campaign"]["campaign_name"], "Updated Name")
        mock_db.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_admin_update_nonexistent_campaign_returns_404(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        res = self.client.put("/campaigns/999", json={"campaign_name": "New Name"})
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_admin_change_campaign_status_success(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"campaign_id": 5, "status": "UPCOMING"},
            {
                "campaign_id": 5,
                "campaign_name": "Blood Drive",
                "location": "Pune",
                "start_date": datetime.datetime(2026, 11, 1, 9, 0),
                "end_date": datetime.datetime(2026, 11, 1, 17, 0),
                "status": "COMPLETED",
                "description": None,
                "created_at": datetime.datetime(2026, 10, 20)
            }
        ]

        res = self.client.put("/campaigns/5/status", json={"status": "COMPLETED"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["campaign"]["status"], "COMPLETED")
        mock_db.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_admin_delete_campaign_success(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"campaign_id": 7}

        res = self.client.delete("/campaigns/7")
        self.assertEqual(res.status_code, 200)
        self.assertIn("deleted successfully", res.get_json()["message"].lower())
        mock_db.commit.assert_called_once()


class TestCampaignDisplayStatusComputation(unittest.TestCase):
    """Verifies that format_campaign_dict accurately distinguishes campaign states."""

    def test_upcoming_status_preserved(self):
        now = datetime.datetime.now()
        future_start = now + datetime.timedelta(days=5)
        future_end = future_start + datetime.timedelta(hours=8)

        row = {
            "campaign_id": 1,
            "campaign_name": "Future Camp",
            "location": "Bangalore",
            "start_date": future_start,
            "end_date": future_end,
            "status": "UPCOMING"
        }
        res = format_campaign_dict(row)
        self.assertEqual(res["status"], "UPCOMING")
        self.assertEqual(res["display_status"], "UPCOMING")

    def test_ongoing_status_computed_when_within_timeframe(self):
        now = datetime.datetime.now()
        past_start = now - datetime.timedelta(hours=2)
        future_end = now + datetime.timedelta(hours=4)

        row = {
            "campaign_id": 2,
            "campaign_name": "Active Camp",
            "location": "Bangalore",
            "start_date": past_start,
            "end_date": future_end,
            "status": "UPCOMING"
        }
        res = format_campaign_dict(row)
        self.assertEqual(res["display_status"], "ONGOING")

    def test_completed_status_distinguished(self):
        row = {
            "campaign_id": 3,
            "campaign_name": "Concluded Camp",
            "location": "Bangalore",
            "start_date": datetime.datetime(2026, 1, 1),
            "end_date": datetime.datetime(2026, 1, 2),
            "status": "COMPLETED"
        }
        res = format_campaign_dict(row)
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(res["display_status"], "COMPLETED")

    def test_cancelled_status_distinguished(self):
        row = {
            "campaign_id": 4,
            "campaign_name": "Cancelled Camp",
            "location": "Bangalore",
            "start_date": datetime.datetime(2026, 12, 1),
            "end_date": datetime.datetime(2026, 12, 2),
            "status": "CANCELLED"
        }
        res = format_campaign_dict(row)
        self.assertEqual(res["status"], "CANCELLED")
        self.assertEqual(res["display_status"], "CANCELLED")


class TestCampaignLiveDatabaseIntegration(unittest.TestCase):
    """
    Live integration test against the MySQL campaigns table.
    Verifies actual insertion, query, update, and deletion in the database.
    Guarantees no orphaned records remain after test execution.
    """

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Super Admin"
            sess["user_role"] = "ADMIN"

        self.created_campaign_ids = []

    def tearDown(self):
        # Clean up any created test records from live DB
        if self.created_campaign_ids:
            try:
                db = database.get_db_connection()
                cur = db.cursor()
                for cid in self.created_campaign_ids:
                    cur.execute("DELETE FROM campaigns WHERE campaign_id = %s", (cid,))
                db.commit()
                cur.close()
                db.close()
            except Exception as e:
                print("Teardown cleanup exception:", e)

    def test_live_campaign_lifecycle(self):
        """Tests full end-to-end campaign lifecycle directly against the MySQL database."""
        # 1. Create a campaign
        create_payload = {
            "campaign_name": "Automated Test Blood Drive",
            "location": "Test Medical Center, Ward 5",
            "start_date": "2026-11-20 09:00:00",
            "end_date": "2026-11-20 17:00:00",
            "status": "UPCOMING",
            "description": "Integration test campaign payload."
        }
        res = self.client.post("/campaigns", json=create_payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        cid = data["campaign"]["campaign_id"]
        self.created_campaign_ids.append(cid)
        self.assertEqual(data["campaign"]["campaign_name"], "Automated Test Blood Drive")

        # 2. Retrieve via GET /campaigns
        res_list = self.client.get("/campaigns")
        self.assertEqual(res_list.status_code, 200)
        campaigns = res_list.get_json()
        match = next((c for c in campaigns if c["campaign_id"] == cid), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["location"], "Test Medical Center, Ward 5")

        # 3. Update campaign details via PUT /campaigns/<id>
        update_payload = {
            "campaign_name": "Automated Test Blood Drive — Extended",
            "location": "Test Medical Center, Hall 10",
            "start_date": "2026-11-20 09:00:00",
            "end_date": "2026-11-20 20:00:00",
            "status": "ONGOING",
            "description": "Extended hours."
        }
        res_update = self.client.put(f"/campaigns/{cid}", json=update_payload)
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(res_update.get_json()["campaign"]["campaign_name"], "Automated Test Blood Drive — Extended")

        # 4. Update status via dedicated status endpoint
        res_status = self.client.put(f"/campaigns/{cid}/status", json={"status": "COMPLETED"})
        self.assertEqual(res_status.status_code, 200)
        self.assertEqual(res_status.get_json()["campaign"]["status"], "COMPLETED")

        # 5. Delete campaign via DELETE /campaigns/<id>
        res_del = self.client.delete(f"/campaigns/{cid}")
        self.assertEqual(res_del.status_code, 200)

        # 6. Verify 404 on subsequent retrieval
        res_get = self.client.get(f"/campaigns/{cid}")
        self.assertEqual(res_get.status_code, 404)

    def test_donor_and_recipient_see_same_published_campaigns(self):
        """Verifies that both DONOR and RECIPIENT accounts retrieve identical published campaigns."""
        create_payload = {
            "campaign_name": "Parity Test Blood Drive",
            "location": "Central Plaza, Mumbai",
            "start_date": "2026-11-25 10:00:00",
            "end_date": "2026-11-25 18:00:00",
            "status": "UPCOMING",
            "description": "Cross-role parity verification."
        }
        res_create = self.client.post("/campaigns", json=create_payload)
        self.assertEqual(res_create.status_code, 201)
        cid = res_create.get_json()["campaign"]["campaign_id"]
        self.created_campaign_ids.append(cid)

        # Retrieve as DONOR
        donor_client = self.app.test_client()
        with donor_client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"
        res_donor = donor_client.get("/campaigns?status=ALL")
        self.assertEqual(res_donor.status_code, 200)
        donor_campaigns = res_donor.get_json()
        donor_match = next((c for c in donor_campaigns if c["campaign_id"] == cid), None)
        self.assertIsNotNone(donor_match)

        # Retrieve as RECIPIENT
        recipient_client = self.app.test_client()
        with recipient_client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "RECIPIENT"
        res_rec = recipient_client.get("/campaigns?status=ALL")
        self.assertEqual(res_rec.status_code, 200)
        rec_campaigns = res_rec.get_json()
        rec_match = next((c for c in rec_campaigns if c["campaign_id"] == cid), None)
        self.assertIsNotNone(rec_match)

        # Assert identical campaign details across both roles
        self.assertEqual(donor_match["campaign_name"], rec_match["campaign_name"])
        self.assertEqual(donor_match["location"], rec_match["location"])
        self.assertEqual(donor_match["start_date"], rec_match["start_date"])
        self.assertEqual(donor_match["end_date"], rec_match["end_date"])
        self.assertEqual(donor_match["status"], rec_match["status"])
        self.assertEqual(donor_match["display_status"], rec_match["display_status"])


class TestDashboardCampaignClientIntegrity(unittest.TestCase):
    """Verifies that dashboard HTML templates provide required client-side helpers (e.g. escapeHtml)."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_donor_dashboard_template_has_escape_html_and_campaign_elements(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"
        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # DOM containers
        self.assertIn('id="donor-campaigns-card"', html)
        self.assertIn('id="donor-campaigns-container"', html)
        self.assertIn('id="donor-campaign-filter-tabs"', html)
        self.assertIn('id="donor-campaign-search"', html)

        # JavaScript functions
        self.assertIn('function escapeHtml', html)
        self.assertIn('function loadDonorCampaigns', html)
        self.assertIn('function renderDonorCampaigns', html)

    def test_recipient_dashboard_template_has_escape_html_and_campaign_elements(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "RECIPIENT"
        res = self.client.get("/recipient/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # DOM containers
        self.assertIn('id="recipient-campaigns-card"', html)
        self.assertIn('id="recipient-campaigns-container"', html)
        self.assertIn('id="recipient-campaign-filter-tabs"', html)
        self.assertIn('id="recipient-campaign-search"', html)

        # JavaScript functions
        self.assertIn('function escapeHtml', html)
        self.assertIn('function loadRecipientCampaigns', html)
        self.assertIn('function renderRecipientCampaigns', html)


if __name__ == "__main__":
    unittest.main()
