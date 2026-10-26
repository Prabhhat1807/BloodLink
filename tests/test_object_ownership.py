"""
Comprehensive Regression Tests for BloodLink:
Individual Record Ownership, Object-Level Authorization (IDOR Defense),
Privacy Safeguards, and Legacy Record Preservation.

All tests run against Flask test_client with unittest.mock to ensure zero mutation of live database records.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import datetime
from decimal import Decimal

from app import app


class TestDonorObjectOwnership(unittest.TestCase):
    """Verifies that donors can only access/modify their own profiles and cannot touch other donors' or legacy profiles."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def set_user_session(self, user_id=10, user_name="Donor User A", role="DONOR"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = user_name
            sess["user_role"] = role

    @patch("app.get_db_connection")
    def test_donor_a_cannot_read_donor_b_profile(self, mock_get_db):
        """Donor A (user_id=10) attempting to read Donor B's profile (user_id=20) must receive 403 Forbidden."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Donor B belongs to user_id=20
        mock_cursor.fetchone.return_value = {
            "donor_id": 2,
            "user_id": 20,
            "name": "Donor B",
            "blood_group": "A+",
            "phone": "9876543220",
            "location": "Pune"
        }

        res = self.client.get("/donors/2")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_donor_cannot_read_legacy_profile(self, mock_get_db):
        """Ordinary donor cannot read a legacy demo donor record (user_id=NULL). Must receive 403 Forbidden."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Legacy demo record has user_id = None
        mock_cursor.fetchone.return_value = {
            "donor_id": 99,
            "user_id": None,
            "name": "Legacy Demo Donor",
            "blood_group": "O+",
            "phone": "9876543299",
            "location": "Mumbai"
        }

        res = self.client.get("/donors/99")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_donor_a_can_read_own_profile_by_id(self, mock_get_db):
        """Donor A (user_id=10) can read their own profile (donor_id=1, user_id=10)."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 1,
            "user_id": 10,
            "name": "Donor A",
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Pune"
        }

        res = self.client.get("/donors/1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["name"], "Donor A")

    @patch("app.get_db_connection")
    def test_donor_self_service_me_endpoint_success(self, mock_get_db):
        """Authenticated donor can load their own profile via GET /donor/me without specifying an ID."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 1,
            "user_id": 10,
            "name": "Donor A",
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Pune"
        }

        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["donor_id"], 1)
        self.assertEqual(data["user_id"], 10)

    @patch("app.get_db_connection")
    def test_donor_self_service_me_not_found(self, mock_get_db):
        """GET /donor/me returns 404 when the user has not yet created a linked donor profile."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.get_json()["message"].lower())

    @patch("app.get_db_connection")
    def test_donor_a_cannot_modify_donor_b_profile(self, mock_get_db):
        """Donor A (user_id=10) attempting to update Donor B's profile (user_id=20) must receive 403 Forbidden."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 2,
            "user_id": 20,
            "name": "Donor B",
            "age": 25,
            "blood_group": "B+",
            "phone": "9876543220",
            "location": "Pune"
        }

        res = self.client.put("/donors/2", json={"name": "Tampered Name", "age": 26, "blood_group": "B+", "phone": "9876543220", "location": "Pune"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_donor_cannot_modify_legacy_profile(self, mock_get_db):
        """Donor A attempting to modify a legacy profile (user_id=NULL) must receive 403 Forbidden."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 99,
            "user_id": None,
            "name": "Legacy Demo Donor",
            "age": 30,
            "blood_group": "O+",
            "phone": "9876543299",
            "location": "Mumbai"
        }

        res = self.client.put("/donors/99", json={"name": "Hacked Name", "age": 31, "blood_group": "O+", "phone": "9876543299", "location": "Mumbai"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_donor_a_can_modify_own_profile(self, mock_get_db):
        """Donor A (user_id=10) can successfully modify their own profile."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 1,
            "user_id": 10,
            "name": "Donor A",
            "age": 24,
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Pune",
            "gender": "Male",
            "availability": 1,
            "weight": Decimal("70.0"),
            "last_donation_date": None,
            "medical_status": "Healthy"
        }

        res = self.client.put("/donors/1", json={
            "name": "Donor A Updated",
            "age": 25,
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Kothrud, Pune"
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("updated", res.get_json()["message"].lower())

    @patch("app.get_db_connection")
    def test_donor_cannot_transfer_profile_ownership(self, mock_get_db):
        """Donor A attempting to pass a different user_id in the update payload to reassign profile gets 403."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 1,
            "user_id": 10,
            "name": "Donor A",
            "age": 24,
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Pune"
        }

        res = self.client.put("/donors/1", json={
            "user_id": 999,
            "name": "Donor A",
            "age": 25,
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Pune"
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("ownership", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_donor_a_cannot_toggle_donor_b_availability(self, mock_get_db):
        """Donor A (user_id=10) attempting to change availability of Donor B (user_id=20) gets 403."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 2,
            "user_id": 20,
            "name": "Donor B",
            "availability": 1
        }

        res = self.client.patch("/donors/2/availability", json={"availability": 0})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_donor_cannot_toggle_legacy_availability(self, mock_get_db):
        """Donor A attempting to change availability of legacy demo donor (user_id=NULL) gets 403."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 99,
            "user_id": None,
            "name": "Legacy Demo Donor",
            "availability": 1
        }

        res = self.client.patch("/donors/99/availability", json={"availability": 0})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_donor_a_can_toggle_own_availability(self, mock_get_db):
        """Donor A (user_id=10) can toggle their own availability."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 1,
            "user_id": 10,
            "name": "Donor A",
            "availability": 1
        }

        res = self.client.patch("/donors/1/availability", json={"availability": 0})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["availability"], 0)

    @patch("app.get_db_connection")
    def test_donor_cannot_create_profile_with_spoofed_user_id(self, mock_get_db):
        """Donor A (user_id=10) submitting a POST /donors payload with user_id=999 gets 403 Forbidden."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        res = self.client.post("/donors", json={
            "user_id": 999,
            "name": "Spoofed Profile",
            "age": 25,
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Pune"
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("another user", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_donor_create_profile_binds_to_session_user_id(self, mock_get_db):
        """Donor A (user_id=10) creating a profile binds to user_id=10 regardless of omitted or own user_id."""
        self.set_user_session(user_id=10, role="DONOR")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 15

        res = self.client.post("/donors", json={
            "name": "New Donor Profile",
            "age": 28,
            "blood_group": "A+",
            "phone": "9876543210",
            "location": "Pune"
        })
        self.assertEqual(res.status_code, 201)

        # Check that target_user_id bound in the INSERT query was 10
        sql_call = mock_cursor.execute.call_args[0]
        self.assertIn("INSERT INTO donors", sql_call[0])
        values = sql_call[1]
        self.assertEqual(values[0], 10)  # user_id position in values


class TestRecipientObjectOwnership(unittest.TestCase):
    """Verifies that recipients can only access/modify their own profiles and cannot touch other recipients' or legacy profiles."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def set_user_session(self, user_id=100, user_name="Recipient User A", role="RECIPIENT"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = user_name
            sess["user_role"] = role

    @patch("app.get_db_connection")
    def test_recipient_a_cannot_read_recipient_b_profile(self, mock_get_db):
        """Recipient A (user_id=100) attempting to read Recipient B's profile (user_id=200) gets 403 Forbidden."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 2,
            "user_id": 200,
            "name": "Recipient B",
            "blood_group": "B+",
            "phone": "9000000002",
            "location": "Pune"
        }

        res = self.client.get("/recipients/2")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_cannot_read_legacy_profile(self, mock_get_db):
        """Ordinary recipient cannot read a legacy demo recipient record (user_id=NULL). Must receive 403 Forbidden."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 99,
            "user_id": None,
            "name": "Legacy Demo Recipient",
            "blood_group": "AB+",
            "phone": "9000000099",
            "location": "Mumbai"
        }

        res = self.client.get("/recipients/99")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_a_can_read_own_profile_by_id(self, mock_get_db):
        """Recipient A (user_id=100) can read their own profile by ID."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 1,
            "user_id": 100,
            "name": "Recipient A",
            "blood_group": "O+",
            "phone": "9000000001",
            "location": "Pune"
        }

        res = self.client.get("/recipients/1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["name"], "Recipient A")

    @patch("app.get_db_connection")
    def test_recipient_self_service_me_endpoint_success(self, mock_get_db):
        """Authenticated recipient can load their own profile via GET /recipient/me without specifying an ID."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 1,
            "user_id": 100,
            "name": "Recipient A",
            "blood_group": "O+",
            "phone": "9000000001",
            "location": "Pune"
        }

        res = self.client.get("/recipient/me")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["recipient_id"], 1)
        self.assertEqual(data["user_id"], 100)

    @patch("app.get_db_connection")
    def test_recipient_self_service_me_not_found(self, mock_get_db):
        """GET /recipient/me returns 404 when recipient profile has not yet been registered."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        res = self.client.get("/recipient/me")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.get_json()["message"].lower())

    @patch("app.get_db_connection")
    def test_recipient_a_cannot_modify_recipient_b_profile(self, mock_get_db):
        """Recipient A (user_id=100) attempting to update Recipient B's profile (user_id=200) gets 403."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 2,
            "user_id": 200,
            "name": "Recipient B",
            "blood_group": "B+",
            "phone": "9000000002",
            "location": "Pune"
        }

        res = self.client.put("/recipients/2", json={"name": "Tampered Name", "age": 30, "blood_group": "B+", "phone": "9000000002", "location": "Pune"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_cannot_modify_legacy_profile(self, mock_get_db):
        """Recipient A attempting to update legacy recipient profile (user_id=NULL) gets 403."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 99,
            "user_id": None,
            "name": "Legacy Recipient",
            "blood_group": "O+",
            "phone": "9000000099",
            "location": "Mumbai"
        }

        res = self.client.put("/recipients/99", json={"name": "Tampered", "age": 35, "blood_group": "O+", "phone": "9000000099", "location": "Mumbai"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_a_can_modify_own_profile(self, mock_get_db):
        """Recipient A (user_id=100) can successfully update their own profile."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 1,
            "user_id": 100,
            "name": "Recipient A",
            "age": 28,
            "gender": "Female",
            "blood_group": "O+",
            "phone": "9000000001",
            "location": "Pune",
            "hospital_id": None,
            "units_required": 2,
            "emergency_level": "NORMAL"
        }

        res = self.client.put("/recipients/1", json={
            "name": "Recipient A Updated",
            "age": 29,
            "gender": "Female",
            "blood_group": "O+",
            "phone": "9000000001",
            "location": "Kothrud, Pune",
            "units_required": 2,
            "emergency_level": "HIGH"
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("updated", res.get_json()["message"].lower())

    @patch("app.get_db_connection")
    def test_recipient_cannot_transfer_profile_ownership(self, mock_get_db):
        """Recipient A attempting to reassign profile ownership via JSON payload gets 403."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "recipient_id": 1,
            "user_id": 100,
            "name": "Recipient A",
            "blood_group": "O+",
            "phone": "9000000001",
            "location": "Pune"
        }

        res = self.client.put("/recipients/1", json={
            "user_id": 999,
            "name": "Recipient A",
            "age": 28,
            "blood_group": "O+",
            "phone": "9000000001",
            "location": "Pune"
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("ownership", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_cannot_create_profile_with_spoofed_user_id(self, mock_get_db):
        """Recipient A (user_id=100) submitting a POST /recipients payload with user_id=999 gets 403 Forbidden."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        res = self.client.post("/recipients", json={
            "user_id": 999,
            "name": "Spoofed Recipient",
            "age": 30,
            "blood_group": "B+",
            "phone": "9000000001",
            "location": "Pune"
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("another user", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_create_profile_binds_to_session_user_id(self, mock_get_db):
        """Recipient A (user_id=100) creating a profile binds to user_id=100."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 42

        res = self.client.post("/recipients", json={
            "name": "Self Recipient",
            "age": 30,
            "blood_group": "B+",
            "phone": "9000000001",
            "location": "Pune"
        })
        self.assertEqual(res.status_code, 201)

        sql_call = mock_cursor.execute.call_args[0]
        self.assertIn("INSERT INTO recipients", sql_call[0])
        values = sql_call[1]
        self.assertEqual(values[0], 100)  # user_id position in values


class TestEmergencyRequestOwnershipAndMatching(unittest.TestCase):
    """Verifies that emergency request status updates enforce relationship-based ownership and matching protects privacy."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def set_user_session(self, user_id=100, user_name="Recipient User A", role="RECIPIENT"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = user_name
            sess["user_role"] = role

    @patch("app.get_db_connection")
    def test_recipient_a_cannot_update_recipient_b_emergency_request(self, mock_get_db):
        """Recipient A (user_id=100) cannot update status of emergency request belonging to Recipient B (user_id=200)."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Database lookup joins emergency_requests to recipients; returns recipient_user_id=200
        mock_cursor.fetchone.return_value = {
            "request_id": 5,
            "request_status": "ACTIVE",
            "recipient_id": 2,
            "recipient_user_id": 200
        }

        res = self.client.put("/emergency/5/status", json={"status": "CANCELLED"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_cannot_update_legacy_emergency_request(self, mock_get_db):
        """Recipient A cannot update status of legacy emergency request (recipient_user_id=NULL). Must return 403."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 88,
            "request_status": "ACTIVE",
            "recipient_id": 99,
            "recipient_user_id": None
        }

        res = self.client.put("/emergency/88/status", json={"status": "CANCELLED"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_a_can_update_own_emergency_request(self, mock_get_db):
        """Recipient A (user_id=100) can successfully cancel or fulfill their own emergency request."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 1,
            "request_status": "ACTIVE",
            "recipient_id": 1,
            "recipient_user_id": 100
        }

        res = self.client.put("/emergency/1/status", json={"status": "CANCELLED"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "CANCELLED")

    @patch("app.get_db_connection")
    def test_recipient_cannot_create_emergency_request_for_other_recipient(self, mock_get_db):
        """Recipient A (user_id=100, whose recipient_id=1) cannot create request with recipient_id=2."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # user_recipient lookup returns recipient_id=1
        mock_cursor.fetchone.return_value = {"recipient_id": 1}

        res = self.client.post("/emergency", json={
            "recipient_id": 2,
            "blood_group_required": "O+",
            "units_required": 2,
            "emergency_level": "CRITICAL"
        })
        self.assertEqual(res.status_code, 403)
        self.assertIn("another recipient", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_create_emergency_request_auto_binds_own_recipient_id(self, mock_get_db):
        """Recipient A creating emergency request without recipient_id auto-binds to their own recipient_id."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"recipient_id": 1}
        mock_cursor.lastrowid = 10

        res = self.client.post("/emergency", json={
            "blood_group_required": "O+",
            "units_required": 2,
            "emergency_level": "HIGH"
        })
        self.assertEqual(res.status_code, 201)

        sql_call = mock_cursor.execute.call_args[0]
        self.assertIn("INSERT INTO emergency_requests", sql_call[0])
        values = sql_call[1]
        self.assertEqual(values[0], 1)  # Bound to recipient_id=1

    @patch("app.find_best_donors")
    @patch("app.get_db_connection")
    def test_find_donors_redacts_phone_for_non_admin(self, mock_get_db, mock_find_best_donors):
        """GET /find-donors redacts direct phone numbers for non-admin recipients."""
        self.set_user_session(user_id=100, role="RECIPIENT")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_find_best_donors.return_value = [
            {
                "donor_id": 1,
                "name": "Pawan Patil",
                "blood_group": "O+",
                "location": "Pune",
                "phone": "9876543210",
                "availability": 1
            }
        ]

        res = self.client.get("/find-donors?blood_group=O+&location=Pune")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["donors"]), 1)
        # Verify phone is redacted/omitted
        self.assertNotIn("phone", data["donors"][0])
        self.assertEqual(data["donors"][0]["name"], "Pawan Patil")

    @patch("app.find_best_donors")
    @patch("app.get_db_connection")
    def test_find_donors_retains_phone_for_admin(self, mock_get_db, mock_find_best_donors):
        """GET /find-donors retains direct phone numbers for admin management."""
        self.set_user_session(user_id=1, role="ADMIN")
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_find_best_donors.return_value = [
            {
                "donor_id": 1,
                "name": "Pawan Patil",
                "blood_group": "O+",
                "location": "Pune",
                "phone": "9876543210",
                "availability": 1
            }
        ]

        res = self.client.get("/find-donors?blood_group=O+&location=Pune")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["donors"]), 1)
        self.assertIn("phone", data["donors"][0])
        self.assertEqual(data["donors"][0]["phone"], "9876543210")


class TestAdminManagementAndLegacyPreservation(unittest.TestCase):
    """Verifies that ADMIN retains full management access over all records, including legacy records with user_id = NULL."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "System Administrator"
            sess["user_role"] = "ADMIN"

    @patch("app.get_db_connection")
    def test_admin_can_read_any_donor_including_legacy(self, mock_get_db):
        """Admin can read user-owned donors and legacy demo donors (user_id=NULL)."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Legacy donor
        mock_cursor.fetchone.return_value = {
            "donor_id": 99,
            "user_id": None,
            "name": "Legacy Demo Donor",
            "blood_group": "O+",
            "phone": "9876543299",
            "location": "Mumbai"
        }

        res = self.client.get("/donors/99")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["name"], "Legacy Demo Donor")

    @patch("app.get_db_connection")
    def test_admin_can_modify_legacy_donor(self, mock_get_db):
        """Admin can modify legacy demo donor records."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 99,
            "user_id": None,
            "name": "Legacy Demo Donor",
            "age": 30,
            "blood_group": "O+",
            "phone": "9876543299",
            "location": "Mumbai",
            "gender": "Male",
            "availability": 1,
            "weight": Decimal("75.0"),
            "last_donation_date": None,
            "medical_status": "Healthy"
        }

        res = self.client.put("/donors/99", json={
            "name": "Admin Updated Legacy Donor",
            "age": 31,
            "blood_group": "O+",
            "phone": "9876543299",
            "location": "Mumbai"
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("updated", res.get_json()["message"].lower())

    @patch("app.get_db_connection")
    def test_admin_can_toggle_legacy_donor_availability(self, mock_get_db):
        """Admin can toggle availability of legacy demo donor records."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 99,
            "user_id": None,
            "name": "Legacy Demo Donor",
            "availability": 1
        }

        res = self.client.patch("/donors/99/availability", json={"availability": 0})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["availability"], 0)

    @patch("app.get_db_connection")
    def test_admin_can_read_and_modify_legacy_recipient(self, mock_get_db):
        """Admin can read and modify legacy recipient records (user_id=NULL)."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Read
        mock_cursor.fetchone.return_value = {
            "recipient_id": 99,
            "user_id": None,
            "name": "Legacy Demo Recipient",
            "age": 35,
            "gender": "Female",
            "blood_group": "B+",
            "phone": "9000000099",
            "location": "Mumbai",
            "hospital_id": None,
            "units_required": 1,
            "emergency_level": "NORMAL"
        }

        res = self.client.get("/recipients/99")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["name"], "Legacy Demo Recipient")

        # Update
        res_put = self.client.put("/recipients/99", json={
            "name": "Admin Updated Legacy Recipient",
            "age": 36,
            "gender": "Female",
            "blood_group": "B+",
            "phone": "9000000099",
            "location": "Mumbai",
            "units_required": 2,
            "emergency_level": "HIGH"
        })
        self.assertEqual(res_put.status_code, 200)
        self.assertIn("updated", res_put.get_json()["message"].lower())

    @patch("app.get_db_connection")
    def test_admin_can_update_legacy_emergency_request(self, mock_get_db):
        """Admin can update status of legacy emergency request (recipient_user_id=NULL)."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 88,
            "request_status": "ACTIVE",
            "recipient_id": 99,
            "recipient_user_id": None
        }

        res = self.client.put("/emergency/88/status", json={"status": "FULFILLED"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "FULFILLED")

    @patch("app.get_db_connection")
    def test_admin_can_access_full_directories(self, mock_get_db):
        """Admin can view the complete donors and recipients directories."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [{"id": 1}]

        res_donors = self.client.get("/donors")
        self.assertEqual(res_donors.status_code, 200)

        res_recipients = self.client.get("/recipients")
        self.assertEqual(res_recipients.status_code, 200)


if __name__ == "__main__":
    unittest.main()
