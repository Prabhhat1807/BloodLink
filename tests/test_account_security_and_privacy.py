"""
Targeted Tests for BloodLink:
1. Donor Contact Privacy & Account ID Redaction in Matching
2. Account Lifecycle Security: Deactivation, Deletion, and Stale Role Synchronization
3. Profile Creation, Duplicate Prevention, and Legacy Record Immunity
"""

import unittest
from unittest.mock import MagicMock, patch
import json
from decimal import Decimal

from app import app


class TestDonorContactPrivacy(unittest.TestCase):
    """Verifies that donor contact fields (phone) and account identifiers are strictly protected."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("app.find_best_donors")
    @patch("app.get_db_connection")
    def test_find_donors_redacts_phone_and_user_id_for_recipients(self, mock_get_db, mock_find_best_donors):
        """A recipient searching for donors via GET /find-donors cannot see donor phone numbers or user_ids."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 200
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_find_best_donors.return_value = [
            {
                "donor_id": 5,
                "user_id": 50,
                "name": "Pawan Patil",
                "blood_group": "O+",
                "phone": "9876543210",
                "location": "Pune",
                "availability": 1,
                "matching_score": 80
            }
        ]

        res = self.client.get("/find-donors?blood_group=O+&location=Pune")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["donors"]), 1)
        matched = data["donors"][0]

        # Verify phone and user_id are strictly redacted from recipient response
        self.assertNotIn("phone", matched)
        self.assertNotIn("user_id", matched)
        self.assertEqual(matched["donor_id"], 5)
        self.assertEqual(matched["name"], "Pawan Patil")

    @patch("app.find_best_donors")
    @patch("app.get_db_connection")
    def test_find_donors_retains_phone_and_user_id_for_admin(self, mock_get_db, mock_find_best_donors):
        """Admin searching donors retains full administrative details including phone and user_id."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Admin User"
            sess["user_role"] = "ADMIN"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        mock_find_best_donors.return_value = [
            {
                "donor_id": 5,
                "user_id": 50,
                "name": "Pawan Patil",
                "blood_group": "O+",
                "phone": "9876543210",
                "location": "Pune",
                "availability": 1,
                "matching_score": 80
            }
        ]

        res = self.client.get("/find-donors?blood_group=O+&location=Pune")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        matched = data["donors"][0]
        self.assertIn("phone", matched)
        self.assertEqual(matched["phone"], "9876543210")
        self.assertIn("user_id", matched)
        self.assertEqual(matched["user_id"], 50)

    def test_donor_directory_blocked_for_non_admin(self):
        """Non-admin users cannot scrape the general donor directory GET /donors."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 10
            sess["user_role"] = "DONOR"
        res = self.client.get("/donors")
        self.assertEqual(res.status_code, 403)

        with self.client.session_transaction() as sess:
            sess["user_id"] = 20
            sess["user_role"] = "RECIPIENT"
        res2 = self.client.get("/donors")
        self.assertEqual(res2.status_code, 403)

    @patch("app.get_db_connection")
    def test_donor_can_retrieve_own_contact_via_self_service(self, mock_get_db):
        """A donor can safely retrieve their own contact phone number via GET /donor/me."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 10
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            "donor_id": 1,
            "user_id": 10,
            "name": "Donor Self",
            "blood_group": "A+",
            "phone": "9876543210",
            "location": "Pune"
        }

        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["donor_id"], 1)
        self.assertEqual(data["phone"], "9876543210")


class TestSessionAndAccountSecurity(unittest.TestCase):
    """Verifies that protected requests check account existence, active status, and refresh stale permissions."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("app.verify_user_in_db")
    def test_deactivated_account_rejected_on_api(self, mock_verify_user):
        """An authenticated session whose account was deactivated (is_active=0) gets 403 on API and session is cleared."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 10
            sess["user_name"] = "Deactivated Donor"
            sess["user_role"] = "DONOR"

        # Database returns account with is_active = 0
        mock_verify_user.return_value = {
            "user_id": 10,
            "name": "Deactivated Donor",
            "email": "donor@example.com",
            "role": "DONOR",
            "is_active": 0
        }

        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 403)
        self.assertIn("deactivated", res.get_json()["error"].lower())

        # Verify session was cleared
        with self.client.session_transaction() as sess_after:
            self.assertNotIn("user_id", sess_after)

    @patch("app.verify_user_in_db")
    def test_deactivated_account_redirects_on_page(self, mock_verify_user):
        """An authenticated session whose account was deactivated gets redirected to /login on page requests."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 10
            sess["user_name"] = "Deactivated Donor"
            sess["user_role"] = "DONOR"

        mock_verify_user.return_value = {
            "user_id": 10,
            "name": "Deactivated Donor",
            "email": "donor@example.com",
            "role": "DONOR",
            "is_active": 0
        }

        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

    @patch("app.verify_user_in_db")
    def test_deleted_account_rejected_on_api(self, mock_verify_user):
        """An authenticated session whose account was deleted from the database gets 401 on API and session is cleared."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 999
            sess["user_name"] = "Deleted User"
            sess["user_role"] = "DONOR"

        # Database returns None (user row does not exist)
        mock_verify_user.return_value = None

        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 401)
        self.assertIn("not found", res.get_json()["error"].lower())

        # Verify session was cleared
        with self.client.session_transaction() as sess_after:
            self.assertNotIn("user_id", sess_after)

    @patch("app.verify_user_in_db")
    def test_deleted_account_redirects_on_page(self, mock_verify_user):
        """An authenticated session whose account was deleted gets redirected to /login on page requests."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 999
            sess["user_name"] = "Deleted User"
            sess["user_role"] = "ADMIN"

        mock_verify_user.return_value = None

        res = self.client.get("/admin/dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

    @patch("app.verify_user_in_db")
    def test_stale_role_in_session_is_synchronized_and_enforced(self, mock_verify_user):
        """A session with stale user_role='ADMIN' is refreshed to 'DONOR' from the database and blocked from admin resources."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 15
            sess["user_name"] = "Demoted User"
            sess["user_role"] = "ADMIN"  # Stale session role

        # Database reports user is now a DONOR
        mock_verify_user.return_value = {
            "user_id": 15,
            "name": "Demoted User",
            "email": "demoted@example.com",
            "role": "DONOR",
            "is_active": 1
        }

        # Attempt to access admin dashboard
        res = self.client.get("/admin/dashboard")
        self.assertEqual(res.status_code, 403)

        # Attempt to access admin API
        res_api = self.client.get("/donors")
        self.assertEqual(res_api.status_code, 403)
        self.assertIn("forbidden", res_api.get_json()["error"].lower())

        # Verify session role was updated in place to the fresh database role
        with self.client.session_transaction() as sess_after:
            self.assertEqual(sess_after.get("user_role"), "DONOR")

    @patch("app.verify_user_in_db")
    @patch("app.get_db_connection")
    def test_active_valid_account_proceeds_normally(self, mock_get_db, mock_verify_user):
        """An active user with valid matching role succeeds normally."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 10
            sess["user_name"] = "Valid Donor"
            sess["user_role"] = "DONOR"

        mock_verify_user.return_value = {
            "user_id": 10,
            "name": "Valid Donor",
            "email": "valid@example.com",
            "role": "DONOR",
            "is_active": 1
        }

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            "donor_id": 1,
            "user_id": 10,
            "name": "Valid Donor",
            "blood_group": "O+",
            "location": "Pune"
        }

        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 200)


class TestProfileCreationAndLinking(unittest.TestCase):
    """Verifies duplicate profile prevention and protection of existing legacy records."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("app.get_db_connection")
    def test_donor_cannot_create_duplicate_profile(self, mock_get_db):
        """A user who already has a registered donor profile cannot create a second profile (returns 409 Conflict)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 10
            sess["user_name"] = "Existing Donor"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Existing profile lookup returns an existing donor_id
        mock_cursor.fetchone.return_value = {"donor_id": 1}

        payload = {
            "name": "Duplicate Donor",
            "age": 25,
            "blood_group": "O+",
            "phone": "9876543210",
            "location": "Pune"
        }

        res = self.client.post("/donors", json=payload)
        self.assertEqual(res.status_code, 409)
        self.assertIn("already exists", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_cannot_create_duplicate_profile(self, mock_get_db):
        """A user who already has a registered recipient profile cannot create a second profile (returns 409 Conflict)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 20
            sess["user_name"] = "Existing Recipient"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Existing profile lookup returns an existing recipient_id
        mock_cursor.fetchone.return_value = {"recipient_id": 2}

        payload = {
            "name": "Duplicate Recipient",
            "age": 30,
            "blood_group": "B+",
            "phone": "9000000002",
            "location": "Pune"
        }

        res = self.client.post("/recipients", json=payload)
        self.assertEqual(res.status_code, 409)
        self.assertIn("already exists", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_admin_can_create_unassigned_legacy_donor(self, mock_get_db):
        """Admin can create unassigned legacy demo records with user_id = NULL."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Admin"
            sess["user_role"] = "ADMIN"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 88

        payload = {
            "user_id": None,
            "name": "Demo Clinic Donor",
            "age": 28,
            "blood_group": "AB+",
            "phone": "9876543288",
            "location": "Pune"
        }

        res = self.client.post("/donors", json=payload)
        self.assertEqual(res.status_code, 201)

        sql_call = mock_cursor.execute.call_args[0]
        self.assertIn("INSERT INTO donors", sql_call[0])
        values = sql_call[1]
        self.assertIsNone(values[0])  # user_id is None

    @patch("app.get_db_connection")
    def test_admin_can_create_unassigned_legacy_recipient(self, mock_get_db):
        """Admin can create unassigned legacy demo recipient with user_id = NULL."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Admin"
            sess["user_role"] = "ADMIN"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.lastrowid = 99

        payload = {
            "user_id": None,
            "name": "Demo Clinic Recipient",
            "age": 35,
            "blood_group": "O-",
            "phone": "9000000099",
            "location": "Mumbai"
        }

        res = self.client.post("/recipients", json=payload)
        self.assertEqual(res.status_code, 201)

        sql_call = mock_cursor.execute.call_args[0]
        self.assertIn("INSERT INTO recipients", sql_call[0])
        values = sql_call[1]
        self.assertIsNone(values[0])  # user_id is None

    @patch("app.get_db_connection")
    def test_user_cannot_claim_legacy_donor_record(self, mock_get_db):
        """Ordinary donor cannot modify or claim a legacy donor record (user_id=NULL)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 10
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            "donor_id": 99,
            "user_id": None,
            "name": "Legacy Demo Donor"
        }

        res = self.client.put("/donors/99", json={"name": "Claim Attempt", "age": 25, "blood_group": "O+", "phone": "9876543299", "location": "Pune"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_user_cannot_claim_legacy_recipient_record(self, mock_get_db):
        """Ordinary recipient cannot modify or claim a legacy recipient record (user_id=NULL)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 20
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            "recipient_id": 99,
            "user_id": None,
            "name": "Legacy Demo Recipient"
        }

        res = self.client.put("/recipients/99", json={"name": "Claim Attempt", "age": 30, "blood_group": "B+", "phone": "9000000099", "location": "Pune"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())


if __name__ == "__main__":
    unittest.main()
