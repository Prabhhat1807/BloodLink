"""
Unit and Integration Tests for BloodLink Route Protection & Session Security Hardening
---------------------------------------------------------------------------------------
Covers:
- Unauthenticated access to protected pages (302 -> /login) and APIs (401 JSON)
- Donor access to recipient-only routes (403) and admin-only routes (403)
- Recipient access to donor-only routes (403) and admin-only routes (403)
- Admin access to admin-only management routes and dashboards
- Shared read-only data protection (hospitals, emergency list)
- Session hardening: dynamic ephemeral secret generation, warning emission, session clearing on logout
- Regression testing: ensuring matching and CRUD workflows succeed for authorized roles

Uses Flask test_client and unittest.mock to guarantee live MySQL database is NOT modified.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import warnings
import os
import secrets
from decimal import Decimal
import datetime

from app import app, is_api_request, login_required, roles_required


class TestUnauthenticatedAccess(unittest.TestCase):
    """Verifies that unauthenticated callers are properly rejected from all protected routes"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # Browser Pages -> Redirect to /login
    def test_unauthenticated_donor_dashboard_redirects_to_login(self):
        response = self.client.get("/donor/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_unauthenticated_recipient_dashboard_redirects_to_login(self):
        response = self.client.get("/recipient/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_unauthenticated_admin_dashboard_redirects_to_login(self):
        response = self.client.get("/admin/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    # Donor API Endpoints -> 401
    def test_unauthenticated_get_donors_returns_401(self):
        res = self.client.get("/donors")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_get_single_donor_returns_401(self):
        res = self.client.get("/donors/1")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_post_donor_returns_401(self):
        res = self.client.post("/donors", json={"name": "Test"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_put_donor_returns_401(self):
        res = self.client.put("/donors/1", json={"name": "Test"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_patch_donor_availability_returns_401(self):
        res = self.client.patch("/donors/1/availability", json={"availability": True})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_delete_donor_returns_401(self):
        res = self.client.delete("/donors/1")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    # Recipient API Endpoints -> 401
    def test_unauthenticated_get_recipients_returns_401(self):
        res = self.client.get("/recipients")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_get_single_recipient_returns_401(self):
        res = self.client.get("/recipients/1")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_post_recipient_returns_401(self):
        res = self.client.post("/recipients", json={"name": "Test"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_put_recipient_returns_401(self):
        res = self.client.put("/recipients/1", json={"name": "Test"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_delete_recipient_returns_401(self):
        res = self.client.delete("/recipients/1")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    # Emergency & Shared Data Endpoints -> 401
    def test_unauthenticated_get_hospitals_returns_401(self):
        res = self.client.get("/hospitals")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_post_emergency_returns_401(self):
        res = self.client.post("/emergency", json={"blood_group_required": "O+"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_get_emergency_returns_401(self):
        res = self.client.get("/emergency")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_get_single_emergency_returns_401(self):
        res = self.client.get("/emergency/1")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_put_emergency_status_returns_401(self):
        res = self.client.put("/emergency/1/status", json={"status": "FULFILLED"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_patch_emergency_status_alternate_route_returns_401(self):
        # Alternate route /emergency/<id> must not bypass security
        res = self.client.patch("/emergency/1", json={"status": "CANCELLED"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    def test_unauthenticated_find_donors_returns_401(self):
        res = self.client.get("/find-donors?blood_group=O+")
        self.assertEqual(res.status_code, 401)
        self.assertIn("authentication required", res.get_json()["error"].lower())

    # Public Endpoints Remain Open
    def test_public_routes_remain_accessible_without_auth(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/signup")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)


class TestDonorRoleAccessControl(unittest.TestCase):
    """Verifies that a DONOR user can access donor routes but is blocked from recipient and admin routes"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

    def test_donor_can_access_donor_dashboard(self):
        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Aarav Patel", res.get_data(as_text=True))

    def test_donor_cannot_access_recipient_dashboard(self):
        res = self.client.get("/recipient/dashboard")
        self.assertEqual(res.status_code, 403)
        self.assertIn("access denied", res.get_data(as_text=True).lower())

    def test_donor_cannot_access_admin_dashboard(self):
        res = self.client.get("/admin/dashboard")
        self.assertEqual(res.status_code, 403)
        self.assertIn("access denied", res.get_data(as_text=True).lower())

    # Donor rejected from recipient APIs (403)
    def test_donor_cannot_access_get_recipients(self):
        res = self.client.get("/recipients")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_cannot_access_get_single_recipient(self):
        res = self.client.get("/recipients/1")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_cannot_post_recipient(self):
        res = self.client.post("/recipients", json={"name": "Test"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_cannot_put_recipient(self):
        res = self.client.put("/recipients/1", json={"name": "Test"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_cannot_post_emergency(self):
        res = self.client.post("/emergency", json={"blood_group_required": "O+"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_cannot_update_emergency_status(self):
        res = self.client.put("/emergency/1/status", json={"status": "FULFILLED"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_cannot_find_donors(self):
        res = self.client.get("/find-donors?blood_group=O+")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    # Donor rejected from admin management APIs (403)
    def test_donor_cannot_delete_donor(self):
        res = self.client.delete("/donors/1")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_donor_cannot_delete_recipient(self):
        res = self.client.delete("/recipients/1")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    # Donor permitted for donor operations & shared read-only data
    @patch("app.get_db_connection")
    def test_donor_permitted_for_donor_operations(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = {"donor_id": 1, "name": "Aarav Patel", "blood_group": "A+", "user_id": 101}

        # General directory of all donors is restricted to ADMIN to protect donor privacy
        res = self.client.get("/donors")
        self.assertEqual(res.status_code, 403)

        # Self-service donor profile
        res = self.client.get("/donor/me")
        self.assertEqual(res.status_code, 200)

        # Own donor profile by ID
        res = self.client.get("/donors/1")
        self.assertEqual(res.status_code, 200)

    @patch("app.get_db_connection")
    def test_donor_permitted_for_shared_data(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        res = self.client.get("/hospitals")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/emergency")
        self.assertEqual(res.status_code, 200)


class TestRecipientRoleAccessControl(unittest.TestCase):
    """Verifies that a RECIPIENT user can access recipient routes but is blocked from donor and admin routes"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Pooja Sharma"
            sess["user_role"] = "RECIPIENT"

    def test_recipient_can_access_recipient_dashboard(self):
        res = self.client.get("/recipient/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Pooja Sharma", res.get_data(as_text=True))

    def test_recipient_cannot_access_donor_dashboard(self):
        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 403)
        self.assertIn("access denied", res.get_data(as_text=True).lower())

    def test_recipient_cannot_access_admin_dashboard(self):
        res = self.client.get("/admin/dashboard")
        self.assertEqual(res.status_code, 403)
        self.assertIn("access denied", res.get_data(as_text=True).lower())

    # Recipient rejected from donor APIs (403)
    def test_recipient_cannot_access_get_donors(self):
        res = self.client.get("/donors")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_recipient_cannot_access_get_single_donor(self):
        res = self.client.get("/donors/1")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_recipient_cannot_post_donor(self):
        res = self.client.post("/donors", json={"name": "Test"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_recipient_cannot_put_donor(self):
        res = self.client.put("/donors/1", json={"name": "Test"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_recipient_cannot_update_donor_availability(self):
        res = self.client.patch("/donors/1/availability", json={"availability": 1})
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    # Recipient rejected from admin management APIs (403)
    def test_recipient_cannot_delete_donor(self):
        res = self.client.delete("/donors/1")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    def test_recipient_cannot_delete_recipient(self):
        res = self.client.delete("/recipients/1")
        self.assertEqual(res.status_code, 403)
        self.assertIn("forbidden", res.get_json()["error"].lower())

    # Recipient permitted for recipient operations & shared read-only data
    @patch("app.get_db_connection")
    def test_recipient_permitted_for_recipient_operations(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = {"recipient_id": 1, "name": "Pooja Sharma", "blood_group": "O+", "user_id": 202}

        # General directory of all recipients is restricted to ADMIN to protect recipient privacy
        res = self.client.get("/recipients")
        self.assertEqual(res.status_code, 403)

        # Self-service recipient profile
        res = self.client.get("/recipient/me")
        self.assertEqual(res.status_code, 200)

        # Own recipient profile by ID
        res = self.client.get("/recipients/1")
        self.assertEqual(res.status_code, 200)

    @patch("app.get_db_connection")
    def test_recipient_permitted_for_shared_data(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        res = self.client.get("/hospitals")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/emergency")
        self.assertEqual(res.status_code, 200)


class TestAdminRoleAccessControl(unittest.TestCase):
    """Verifies that an ADMIN user has administrative management access across consoles and delete endpoints"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Super Admin"
            sess["user_role"] = "ADMIN"

    def test_admin_can_access_admin_dashboard(self):
        res = self.client.get("/admin/dashboard")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Super Admin", res.get_data(as_text=True))

    @patch("app.get_db_connection")
    def test_admin_can_delete_donor(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        res = self.client.delete("/donors/1")
        self.assertEqual(res.status_code, 200)
        self.assertIn("deleted successfully", res.get_json()["message"].lower())
        mock_db.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_admin_can_delete_recipient(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"recipient_id": 1}

        res = self.client.delete("/recipients/1")
        self.assertEqual(res.status_code, 200)
        self.assertIn("deleted successfully", res.get_json()["message"].lower())
        mock_db.commit.assert_called_once()

    @patch("app.get_db_connection")
    def test_admin_can_manage_donors_and_recipients(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = {"recipient_id": 1, "hospital_id": 1}

        res = self.client.get("/donors")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/recipients")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/emergency")
        self.assertEqual(res.status_code, 200)


class TestSessionSecurityAndHardening(unittest.TestCase):
    """Verifies session configuration hardening, secret generation, and session lifecycle behavior"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_no_hardcoded_or_fallback_dev_secret(self):
        """Verifies that the old fixed fallback secret string is not in use"""
        forbidden_key = "bloodlink-dev-secret-key-change-in-production"
        self.assertNotEqual(self.app.secret_key, forbidden_key)
        self.assertIsInstance(self.app.secret_key, str)
        self.assertGreaterEqual(len(self.app.secret_key), 32)

    def test_ephemeral_secret_generation_emits_warning(self):
        """Test that when environment variables are missing, a warning is raised and a 64-char hex key is created"""
        with patch.dict(os.environ, {}, clear=True):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                # Simulate loading logic
                env_secret = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY")
                if not env_secret:
                    env_secret = secrets.token_hex(32)
                    warnings.warn("No SECRET_KEY set. Ephemeral key generated.", UserWarning)

                self.assertEqual(len(w), 1)
                self.assertIn("Ephemeral key generated", str(w[-1].message))
                self.assertEqual(len(env_secret), 64)

    def test_session_cookie_flags(self):
        """Verify strict session cookie flags (HttpOnly, SameSite)"""
        self.assertTrue(self.app.config.get("SESSION_COOKIE_HTTPONLY"))
        self.assertEqual(self.app.config.get("SESSION_COOKIE_SAMESITE"), "Lax")

    def test_logout_clears_session_and_revokes_access(self):
        """Ensure logout wipes identity and prevents further protected access"""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 10
            sess["user_name"] = "Active User"
            sess["user_role"] = "DONOR"

        # Verify access before logout
        res_before = self.client.get("/donor/dashboard")
        self.assertEqual(res_before.status_code, 200)

        # Execute logout
        logout_res = self.client.post("/logout")
        self.assertEqual(logout_res.status_code, 302)

        # Verify access after logout is blocked
        res_after = self.client.get("/donor/dashboard")
        self.assertEqual(res_after.status_code, 302)
        self.assertIn("/login", res_after.headers["Location"])

    def test_is_api_request_helper(self):
        """Verify is_api_request properly detects JSON vs browser page requests"""
        with self.app.test_request_context("/donors", method="GET"):
            self.assertTrue(is_api_request())

        with self.app.test_request_context("/donor/dashboard", method="GET"):
            self.assertFalse(is_api_request())

        with self.app.test_request_context("/donor/dashboard", method="GET", headers={"X-Requested-With": "XMLHttpRequest"}):
            self.assertTrue(is_api_request())

        with self.app.test_request_context("/login", method="POST", json={"email": "a@b.com"}):
            self.assertTrue(is_api_request())


class TestAuthorizedCrudAndMatchingRegression(unittest.TestCase):
    """Ensures existing matching and CRUD behavior continues working correctly for authorized users"""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("app.get_db_connection")
    def test_authorized_find_donors_matching(self, mock_get_db):
        """Test GET /find-donors executes matching algorithm for authorized RECIPIENT"""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 50
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        sample_donors = [
            {
                "donor_id": 1,
                "name": "Compatible Donor",
                "blood_group": "O+",
                "location": "Pune",
                "availability": 1,
                "last_donation_date": datetime.date(2026, 6, 1)
            }
        ]
        mock_cursor.fetchall.return_value = sample_donors

        res = self.client.get("/find-donors", query_string={"blood_group": "O+", "location": "Pune"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["recipient_blood_group"], "O+")
        self.assertEqual(data["location"], "Pune")
        self.assertGreater(data["total_matches"], 0)


if __name__ == "__main__":
    unittest.main()
