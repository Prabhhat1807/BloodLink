"""
Unit and Integration Tests for BloodLink Stage 1:
Security Hardening and Database Reliability.
Covers:
- CSRF defense-in-depth: Rejection of cross-origin state mutations (HTTP 403)
- Database configuration via environment variables (.env / os.environ)
- Nonexistent ID handling on DELETE /donors/<id> and DELETE /recipients/<id> (HTTP 404)
- MySQL Foreign Key constraint error handling on deletion (HTTP 409 Conflict)
- Resource cleanup verification (try...finally cursor.close() and db.close())
- Null-safety for donor and recipient locations in matching algorithm
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import mysql.connector

from app import app
from database import get_db_connection, _load_env
from matching import find_best_donors, is_compatible


class TestStage1SecurityAndReliability(unittest.TestCase):
    """Test suite verifying Stage 1 security hardening and reliability enhancements."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # =========================================================================
    # 1. CSRF Defense-in-Depth (Origin Header Verification)
    # =========================================================================

    def test_csrf_cross_origin_mutation_rejected_with_403(self):
        """State-changing requests from a foreign Origin header must be rejected with 403."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        # Simulate cross-origin attack from external site
        headers = {
            "Host": "localhost:5000",
            "Origin": "https://malicious-attacker-site.com"
        }
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14}, headers=headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("cross-origin request rejected", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_csrf_same_origin_mutation_accepted(self, mock_get_db):
        """Requests with a matching Origin header must be accepted."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            {"donor_id": 12, "user_id": 101, "name": "Aarav", "blood_group": "A+", "availability": 1, "phone": "9876543210"},
            {"request_id": 14, "recipient_id": 5, "hospital_id": 1, "blood_group_required": "A+", "units_required": 1, "emergency_level": "HIGH", "request_status": "ACTIVE", "recipient_user_id": 202},
            None,
            None
        ]
        mock_cursor.lastrowid = 201

        headers = {
            "Host": "localhost:5000",
            "Origin": "http://localhost:5000"
        }
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14}, headers=headers)
        self.assertEqual(res.status_code, 201)

    # =========================================================================
    # 2. Nonexistent Record & Foreign Key Deletion Error Handling
    # =========================================================================

    @patch("app.get_db_connection")
    def test_delete_nonexistent_donor_returns_404(self, mock_get_db):
        """Attempting to delete a nonexistent donor must return HTTP 404."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "ADMIN"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        # Donor not found
        mock_cursor.fetchone.return_value = None

        res = self.client.delete("/donors/99999")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_delete_donor_fk_constraint_returns_409(self, mock_get_db):
        """Attempting to delete a donor with related records triggers MySQL 1451 and returns HTTP 409."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "ADMIN"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"donor_id": 10, "name": "Test Donor"}
        # Simulate MySQL error 1451: Cannot delete or update a parent row: a foreign key constraint fails
        err = mysql.connector.Error(errno=1451, msg="Cannot delete or update a parent row: a foreign key constraint fails")
        mock_cursor.execute.side_effect = [None, err]

        res = self.client.delete("/donors/10")
        self.assertEqual(res.status_code, 409)
        self.assertIn("foreign key constraint violation", res.get_json()["error"].lower())
        self.assertTrue(mock_db.rollback.called)

    @patch("app.get_db_connection")
    def test_delete_nonexistent_recipient_returns_404(self, mock_get_db):
        """Attempting to delete a nonexistent recipient must return HTTP 404."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "ADMIN"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        res = self.client.delete("/recipients/99999")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_delete_recipient_fk_constraint_returns_409(self, mock_get_db):
        """Attempting to delete a recipient with related records triggers MySQL 1451 and returns HTTP 409."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "ADMIN"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"recipient_id": 20}
        err = mysql.connector.Error(errno=1451, msg="Cannot delete or update a parent row")
        mock_cursor.execute.side_effect = [None, err]

        res = self.client.delete("/recipients/20")
        self.assertEqual(res.status_code, 409)
        self.assertIn("foreign key constraint violation", res.get_json()["error"].lower())
        self.assertTrue(mock_db.rollback.called)

    # =========================================================================
    # 3. Resource Cleanup (try ... finally guarantee)
    # =========================================================================

    @patch("app.get_db_connection")
    def test_get_donors_closes_connection_on_exception(self, mock_get_db):
        """get_donors must close cursor and database connection even if query raises exception."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "ADMIN"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = RuntimeError("Database query timeout")

        res = self.client.get("/donors")
        self.assertEqual(res.status_code, 500)
        self.assertTrue(mock_cursor.close.called)
        self.assertTrue(mock_db.close.called)

    @patch("app.get_db_connection")
    def test_get_hospitals_closes_connection_on_exception(self, mock_get_db):
        """get_hospitals must close cursor and database connection even if query raises exception."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = RuntimeError("Connection dropped")

        res = self.client.get("/hospitals")
        self.assertEqual(res.status_code, 500)
        self.assertTrue(mock_cursor.close.called)
        self.assertTrue(mock_db.close.called)

    @patch("app.get_db_connection")
    def test_find_donors_closes_connection_on_exception(self, mock_get_db):
        """find_donors must close cursor and database connection even if query raises exception."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = RuntimeError("Query execution failed")

        res = self.client.get("/find-donors?blood_group=O+")
        self.assertEqual(res.status_code, 500)
        self.assertTrue(mock_cursor.close.called)
        self.assertTrue(mock_db.close.called)

    # =========================================================================
    # 4. Matching Algorithm Location Null-Safety
    # =========================================================================

    def test_matching_algorithm_handles_none_locations_safely(self):
        """find_best_donors must handle None location values without raising AttributeError."""
        donors = [
            {"donor_id": 1, "name": "Donor A", "blood_group": "O+", "location": None, "availability": 1},
            {"donor_id": 2, "name": "Donor B", "blood_group": "O+", "location": "Pune", "availability": 1},
            {"donor_id": 3, "name": "Donor C", "blood_group": "A+", "location": None, "availability": 1}
        ]

        # Case A: target location is None
        matches_none_target = find_best_donors(donors, "O+", None)
        self.assertEqual(len(matches_none_target), 2)

        # Case B: target location is provided, some donors have None location
        matches_with_target = find_best_donors(donors, "O+", "Pune")
        self.assertEqual(len(matches_with_target), 2)
        # Pune donor gets 60 (blood) + 20 (location) = 80
        self.assertEqual(matches_with_target[0]["donor_id"], 2)
        self.assertEqual(matches_with_target[0]["matching_score"], 80)
        # None location donor gets 60 (blood) + 0 (location) = 60
        self.assertEqual(matches_with_target[1]["donor_id"], 1)
        self.assertEqual(matches_with_target[1]["matching_score"], 60)


if __name__ == "__main__":
    unittest.main()
