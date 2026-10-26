"""
Comprehensive Test Suite for BloodLink Functional Dashboards:
1. Donor Dashboard:
   - Access control (DONOR allowed, unauth 302, RECIPIENT 403)
   - Profile retrieval (GET /donor/me)
   - Profile creation when unlinked (POST /donors)
   - Duplicate profile prevention (409 Conflict)
   - Profile editing (PUT /donor/me)
   - Availability toggle (PUT /donor/me/availability)
   - Emergency requests feed privacy (no recipient phone exposed)
2. Recipient Dashboard:
   - Access control (RECIPIENT allowed, unauth 302, DONOR 403)
   - Profile retrieval (GET /recipient/me)
   - Profile creation when unlinked (POST /recipients)
   - Duplicate profile prevention (409 Conflict)
   - Profile editing (PUT /recipient/me)
   - Emergency request creation linked to verified profile (POST /emergency)
   - Cross-account recipient_id spoofing prevention (403 Forbidden)
   - Personal request history strictly isolated (GET /recipient/me/emergency)
   - Emergency request cancellation (PUT /emergency/<id>/status)
   - Compatible donor search with phone/user_id redaction (GET /find-donors)
3. Cross-Account Negative Security Tests
"""

import unittest
from unittest.mock import MagicMock, patch
import json

from app import app


class TestDonorDashboard(unittest.TestCase):
    """Tests for Donor Dashboard operations and endpoints."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # 1. Access Control
    def test_donor_can_access_donor_dashboard_page(self):
        """Authenticated DONOR can view the donor dashboard page."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"
        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Aarav Patel", res.get_data(as_text=True))
        self.assertIn("Donor Portal", res.get_data(as_text=True))

    def test_recipient_cannot_access_donor_dashboard_page(self):
        """Authenticated RECIPIENT is forbidden from viewing donor dashboard."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"
        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_redirected_from_donor_dashboard(self):
        """Unauthenticated user is redirected to /login."""
        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    # 2. Profile Retrieval (GET /donor/me)
    @patch("app.get_db_connection")
    def test_get_my_donor_profile_success(self, mock_get_db):
        """DONOR can retrieve their own database-linked profile."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 12,
            "user_id": 101,
            "name": "Aarav Patel",
            "age": 28,
            "gender": "Male",
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Mumbai",
            "availability": 1,
            "weight": 70.0,
            "medical_status": "Fit to donate",
            "last_donation_date": "2026-01-15"
        }

        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["donor_id"], 12)
        self.assertEqual(data["user_id"], 101)
        self.assertEqual(data["blood_group"], "O+")

    @patch("app.get_db_connection")
    def test_get_my_donor_profile_not_found_returns_404(self, mock_get_db):
        """Returns 404 when authenticated donor has no linked profile yet."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 999
            sess["user_name"] = "New Donor"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.get_json().get("message", "").lower())

    # 3. Profile Creation when unlinked (POST /donors)
    @patch("app.get_db_connection")
    def test_donor_can_create_profile_when_unlinked(self, mock_get_db):
        """DONOR can create their donor profile and it binds to session user_id."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 105
            sess["user_name"] = "Kavita Rao"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # First query checks for existing profile -> None
        mock_cursor.fetchone.return_value = None
        mock_cursor.lastrowid = 35

        payload = {
            "name": "Kavita Rao",
            "age": 25,
            "gender": "Female",
            "blood_group": "A+",
            "phone": "9812345678",
            "location": "Bangalore",
            "weight": 58,
            "availability": 1,
            "medical_status": "Eligible"
        }

        res = self.client.post("/donors", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["donor_id"], 35)

    @patch("app.get_db_connection")
    def test_donor_cannot_create_duplicate_profile(self, mock_get_db):
        """DONOR attempting to create a second profile receives 409 Conflict."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Already has an existing profile
        mock_cursor.fetchone.return_value = {"donor_id": 12}

        payload = {
            "name": "Aarav Duplicate",
            "age": 28,
            "gender": "Male",
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Mumbai",
            "weight": 70,
            "availability": 1
        }

        res = self.client.post("/donors", json=payload)
        self.assertEqual(res.status_code, 409)
        self.assertIn("conflict", res.get_json().get("error", "").lower())

    # 4. Profile Editing (PUT /donor/me)
    @patch("app.get_db_connection")
    def test_donor_can_edit_own_profile(self, mock_get_db):
        """DONOR can edit permitted profile fields via PUT /donor/me."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # First fetch: resolve donor_id for user_id = 101 -> donor_id = 12
        # Second fetch: in update_donor to verify ownership -> user_id = 101
        mock_cursor.fetchone.side_effect = [
            {"donor_id": 12},
            {"donor_id": 12, "user_id": 101}
        ]

        payload = {
            "name": "Aarav Patel Updated",
            "blood_group": "O+",
            "phone": "9998887776",
            "location": "Navi Mumbai",
            "age": 29,
            "gender": "Male",
            "weight": 72.5,
            "medical_status": "Healthy and active"
        }

        res = self.client.put("/donor/me", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("updated", res.get_json().get("message", "").lower())

    # 5. Availability Toggle (PUT /donor/me/availability)
    @patch("app.get_db_connection")
    def test_donor_can_toggle_availability(self, mock_get_db):
        """DONOR can toggle their availability status via PUT /donor/me/availability."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # First fetch: resolve donor_id for user_id = 101
        # Second fetch: in update_donor_availability -> donor record with user_id = 101
        mock_cursor.fetchone.side_effect = [
            {"donor_id": 12},
            {"donor_id": 12, "user_id": 101, "availability": 1}
        ]

        res = self.client.put("/donor/me/availability", json={"availability": 0})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["availability"], 0)

    # 6. Emergency Requests Feed (GET /emergency)
    @patch("app.get_db_connection")
    def test_donor_can_view_active_emergency_feed_without_recipient_contact(self, mock_get_db):
        """DONOR can view active emergency requests without exposing recipient telephone or private contact."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [
            {
                "request_id": 1,
                "recipient_id": 4,
                "hospital_id": 2,
                "blood_group_required": "O+",
                "units_required": 3,
                "emergency_level": "CRITICAL",
                "request_status": "ACTIVE",
                "request_date": "2026-10-25"
            }
        ]

        res = self.client.get("/emergency?status=ACTIVE")
        self.assertEqual(res.status_code, 200)
        requests = res.get_json()
        self.assertEqual(len(requests), 1)
        req = requests[0]

        # Recipient contact numbers must NEVER be present in emergency_requests
        self.assertNotIn("phone", req)
        self.assertNotIn("recipient_phone", req)
        self.assertEqual(req["blood_group_required"], "O+")
        self.assertEqual(req["emergency_level"], "CRITICAL")


class TestRecipientDashboard(unittest.TestCase):
    """Tests for Recipient Dashboard operations and endpoints."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # 1. Access Control
    def test_recipient_can_access_recipient_dashboard_page(self):
        """Authenticated RECIPIENT can view the recipient dashboard page."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"
        res = self.client.get("/recipient/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Priya Sharma", res.get_data(as_text=True))
        self.assertIn("Recipient Portal", res.get_data(as_text=True))

    def test_donor_cannot_access_recipient_dashboard_page(self):
        """Authenticated DONOR is forbidden from viewing recipient dashboard."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"
        res = self.client.get("/recipient/dashboard")
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_redirected_from_recipient_dashboard(self):
        """Unauthenticated user is redirected to /login."""
        res = self.client.get("/recipient/dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    # 2. Profile Retrieval (GET /recipient/me)
    @patch("app.get_db_connection")
    def test_get_my_recipient_profile_success(self, mock_get_db):
        """RECIPIENT can retrieve their own profile with linked hospital."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 8,
            "user_id": 202,
            "name": "Priya Sharma",
            "age": 32,
            "gender": "Female",
            "blood_group": "B+",
            "phone": "9876543210",
            "location": "Pune",
            "hospital_id": 1,
            "units_required": 2,
            "emergency_level": "HIGH",
            "hospital_name": "City Care Hospital",
            "hospital_city": "Pune"
        }

        res = self.client.get("/recipient/me")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["recipient_id"], 8)
        self.assertEqual(data["user_id"], 202)
        self.assertEqual(data["blood_group"], "B+")
        self.assertEqual(data["hospital_name"], "City Care Hospital")

    @patch("app.get_db_connection")
    def test_get_my_recipient_profile_not_found_returns_404(self, mock_get_db):
        """Returns 404 when authenticated recipient has no linked profile yet."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 998
            sess["user_name"] = "New Recipient"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        res = self.client.get("/recipient/me")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.get_json().get("message", "").lower())

    # 3. Profile Creation when unlinked (POST /recipients)
    @patch("app.get_db_connection")
    def test_recipient_can_create_profile_when_unlinked(self, mock_get_db):
        """RECIPIENT can create their profile and it binds to session user_id."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 205
            sess["user_name"] = "Sunita Joshi"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Checks hospital_id exists -> returns row
        # Checks existing recipient for user_id -> None
        mock_cursor.fetchone.side_effect = [
            {"hospital_id": 1},
            None
        ]
        mock_cursor.lastrowid = 19

        payload = {
            "name": "Sunita Joshi",
            "age": 45,
            "gender": "Female",
            "blood_group": "AB+",
            "phone": "9812345678",
            "location": "Nagpur",
            "hospital_id": 1,
            "units_required": 3,
            "emergency_level": "NORMAL"
        }

        res = self.client.post("/recipients", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["recipient_id"], 19)

    @patch("app.get_db_connection")
    def test_recipient_cannot_create_duplicate_profile(self, mock_get_db):
        """RECIPIENT attempting to create duplicate profile receives 409 Conflict."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"hospital_id": 1},
            {"recipient_id": 8}  # Already exists
        ]

        payload = {
            "name": "Priya Sharma",
            "age": 32,
            "gender": "Female",
            "blood_group": "B+",
            "phone": "9876543210",
            "location": "Pune",
            "hospital_id": 1,
            "units_required": 2,
            "emergency_level": "HIGH"
        }

        res = self.client.post("/recipients", json=payload)
        self.assertEqual(res.status_code, 409)
        self.assertIn("conflict", res.get_json().get("error", "").lower())

    # 4. Profile Editing (PUT /recipient/me)
    @patch("app.get_db_connection")
    def test_recipient_can_edit_own_profile(self, mock_get_db):
        """RECIPIENT can edit permitted profile fields via PUT /recipient/me."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # 1. Resolve recipient_id for user_id = 202 -> recipient_id = 8
        # 2. In update_recipient: verify recipient ownership -> user_id = 202
        # 3. Check hospital exists -> hospital_id = 1
        mock_cursor.fetchone.side_effect = [
            {"recipient_id": 8},
            {"recipient_id": 8, "user_id": 202},
            {"hospital_id": 1}
        ]

        payload = {
            "name": "Priya Sharma Updated",
            "blood_group": "B+",
            "phone": "9998881111",
            "location": "Pune East",
            "age": 33,
            "gender": "Female",
            "hospital_id": 1,
            "units_required": 1,
            "emergency_level": "NORMAL"
        }

        res = self.client.put("/recipient/me", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertIn("updated", res.get_json().get("message", "").lower())

    # 5. Emergency Request Creation (POST /emergency)
    @patch("app.get_db_connection")
    def test_recipient_can_create_emergency_request_linked_to_profile(self, mock_get_db):
        """RECIPIENT creates an emergency request automatically linked to verified profile."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # 1. Fetch user recipient record -> recipient_id = 8
        # 2. Check hospital exists -> hospital_id = 1
        # 3. Check recipient exists -> recipient_id = 8
        mock_cursor.fetchone.side_effect = [
            {"recipient_id": 8},
            {"hospital_id": 1},
            {"recipient_id": 8}
        ]
        mock_cursor.lastrowid = 101

        payload = {
            "blood_group_required": "B+",
            "units_required": 2,
            "emergency_level": "CRITICAL",
            "hospital_id": 1
        }

        res = self.client.post("/emergency", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["request_id"], 101)

    @patch("app.get_db_connection")
    def test_recipient_cannot_create_request_for_another_recipient(self, mock_get_db):
        """RECIPIENT attempting to set another recipient's recipient_id is rejected (403)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Caller's profile has recipient_id = 8
        mock_cursor.fetchone.return_value = {"recipient_id": 8}

        payload = {
            "recipient_id": 99,  # Attempting to forge request for recipient #99
            "blood_group_required": "B+",
            "units_required": 2,
            "emergency_level": "CRITICAL",
            "hospital_id": 1
        }

        res = self.client.post("/emergency", json=payload)
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json().get("error", "").lower())

    # 6. Personal Request History (GET /recipient/me/emergency)
    @patch("app.get_db_connection")
    def test_recipient_gets_only_own_emergency_history(self, mock_get_db):
        """GET /recipient/me/emergency returns strictly the caller's own requests."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # 1. Fetch recipient_id for user_id = 202 -> 8
        mock_cursor.fetchone.return_value = {"recipient_id": 8}

        # 2. Return requests for recipient_id = 8
        mock_cursor.fetchall.return_value = [
            {
                "request_id": 101,
                "recipient_id": 8,
                "hospital_id": 1,
                "blood_group_required": "B+",
                "units_required": 2,
                "emergency_level": "CRITICAL",
                "request_status": "ACTIVE",
                "hospital_name": "City Care Hospital",
                "hospital_city": "Pune"
            }
        ]

        res = self.client.get("/recipient/me/emergency")
        self.assertEqual(res.status_code, 200)
        history = res.get_json()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["recipient_id"], 8)
        self.assertEqual(history[0]["request_id"], 101)

    # 7. Cancel Own Emergency Request
    @patch("app.get_db_connection")
    def test_recipient_can_cancel_own_emergency_request(self, mock_get_db):
        """RECIPIENT can cancel their own active emergency request."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Existing request belongs to recipient_user_id = 202
        mock_cursor.fetchone.return_value = {
            "request_id": 101,
            "request_status": "ACTIVE",
            "recipient_id": 8,
            "recipient_user_id": 202
        }

        res = self.client.put("/emergency/101/status", json={"status": "CANCELLED"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "CANCELLED")

    @patch("app.get_db_connection")
    def test_recipient_cannot_cancel_another_recipients_request(self, mock_get_db):
        """RECIPIENT cannot cancel another recipient's emergency request (403)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Request belongs to user_id = 999 (different user)
        mock_cursor.fetchone.return_value = {
            "request_id": 55,
            "request_status": "ACTIVE",
            "recipient_id": 14,
            "recipient_user_id": 999
        }

        res = self.client.put("/emergency/55/status", json={"status": "CANCELLED"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json().get("error", "").lower())

    # 8. Compatible Donor Search Privacy (GET /find-donors)
    @patch("app.find_best_donors")
    @patch("app.get_db_connection")
    def test_find_donors_protects_contact_and_user_ids(self, mock_get_db, mock_find):
        """Compatible donor search redacts telephone numbers and user_id for recipient searchers."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_find.return_value = [
            {
                "donor_id": 12,
                "user_id": 101,
                "name": "Aarav Patel",
                "blood_group": "O+",
                "phone": "9876543210",
                "location": "Pune",
                "availability": 1,
                "matching_score": 90
            }
        ]

        res = self.client.get("/find-donors?blood_group=B+&location=Pune")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["donors"]), 1)
        donor = data["donors"][0]

        # Privacy verification: phone and user_id must NOT be exposed
        self.assertNotIn("phone", donor)
        self.assertNotIn("user_id", donor)
        self.assertEqual(donor["name"], "Aarav Patel")
        self.assertEqual(donor["matching_score"], 90)


class TestCrossAccountDashboardSecurity(unittest.TestCase):
    """Negative tests for cross-account access and data leakage across role boundaries."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_donor_cannot_access_recipient_self_service_endpoints(self):
        """DONOR is forbidden from calling /recipient/me or /recipient/me/emergency."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        res = self.client.get("/recipient/me")
        self.assertEqual(res.status_code, 403)

        res2 = self.client.put("/recipient/me", json={"name": "Tamper"})
        self.assertEqual(res2.status_code, 403)

        res3 = self.client.get("/recipient/me/emergency")
        self.assertEqual(res3.status_code, 403)

    def test_recipient_cannot_access_donor_self_service_endpoints(self):
        """RECIPIENT is forbidden from calling /donor/me or /donor/me/availability."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_role"] = "RECIPIENT"

        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 403)

        res2 = self.client.put("/donor/me", json={"name": "Tamper"})
        self.assertEqual(res2.status_code, 403)

        res3 = self.client.put("/donor/me/availability", json={"availability": 1})
        self.assertEqual(res3.status_code, 403)

    def test_unauthenticated_cannot_access_self_service_endpoints(self):
        """Unauthenticated caller receives 401 for self-service API endpoints."""
        res1 = self.client.get("/donor/me")
        self.assertEqual(res1.status_code, 401)

        res2 = self.client.get("/recipient/me")
        self.assertEqual(res2.status_code, 401)

        res3 = self.client.get("/recipient/me/emergency")
        self.assertEqual(res3.status_code, 401)


if __name__ == "__main__":
    unittest.main()
