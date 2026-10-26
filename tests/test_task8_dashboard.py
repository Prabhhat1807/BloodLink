"""
Unit and Integration Tests for BloodLink Task 8:
Dashboard Overview — Real-time Telemetry, Statistics Cards, Recent Requests, and Error Handling.
Uses Flask test_client and unittest.mock to ensure the active database is NOT modified.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import datetime

from app import app


class TestDashboardApiMocked(unittest.TestCase):
    """Unit tests for GET /dashboard/stats with mocked database interactions."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("app.get_db_connection")
    def test_dashboard_stats_success(self, mock_get_db):
        """Test GET /dashboard/stats with populated counts and recent requests."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock query return values in sequence:
        # 1. total_donors
        # 2. available_donors
        # 3. active_emergency_requests
        mock_cursor.fetchone.side_effect = [
            {"total_donors": 15},
            {"available_donors": 11},
            {"active_emergency_requests": 4}
        ]

        # 4. recent emergency requests (5 latest)
        sample_requests = [
            {
                "request_id": 10,
                "blood_group_required": "O-",
                "units_required": 2,
                "emergency_level": "CRITICAL",
                "request_status": "ACTIVE",
                "request_date": datetime.datetime(2026, 10, 24, 12, 0, 0),
                "hospital_id": 1,
                "recipient_id": 2,
                "hospital_name": "City Care Hospital",
                "hospital_city": "Pune"
            },
            {
                "request_id": 9,
                "blood_group_required": "A+",
                "units_required": 1,
                "emergency_level": "URGENT",
                "request_status": "ACTIVE",
                "request_date": datetime.datetime(2026, 10, 24, 11, 30, 0),
                "hospital_id": 2,
                "recipient_id": 1,
                "hospital_name": "Metro Trauma Center",
                "hospital_city": "Mumbai"
            },
            {
                "request_id": 8,
                "blood_group_required": "B+",
                "units_required": 3,
                "emergency_level": "STANDARD",
                "request_status": "ACTIVE",
                "request_date": datetime.datetime(2026, 10, 24, 10, 15, 0),
                "hospital_id": 1,
                "recipient_id": None,
                "hospital_name": "City Care Hospital",
                "hospital_city": "Pune"
            },
            {
                "request_id": 7,
                "blood_group_required": "AB+",
                "units_required": 1,
                "emergency_level": "CRITICAL",
                "request_status": "CANCELLED",
                "request_date": datetime.datetime(2026, 10, 23, 18, 0, 0),
                "hospital_id": None,
                "recipient_id": None,
                "hospital_name": None,
                "hospital_city": None
            },
            {
                "request_id": 6,
                "blood_group_required": "O+",
                "units_required": 2,
                "emergency_level": "URGENT",
                "request_status": "FULFILLED",
                "request_date": datetime.datetime(2026, 10, 23, 15, 45, 0),
                "hospital_id": 2,
                "recipient_id": 3,
                "hospital_name": "Metro Trauma Center",
                "hospital_city": "Mumbai"
            }
        ]
        mock_cursor.fetchall.return_value = sample_requests

        response = self.client.get("/dashboard/stats")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data["total_donors"], 15)
        self.assertEqual(data["available_donors"], 11)
        self.assertEqual(data["active_emergency_requests"], 4)
        self.assertEqual(len(data["recent_requests"]), 5)

        first_req = data["recent_requests"][0]
        self.assertEqual(first_req["request_id"], 10)
        self.assertEqual(first_req["blood_group_required"], "O-")
        self.assertEqual(first_req["units_required"], 2)
        self.assertEqual(first_req["emergency_level"], "CRITICAL")
        self.assertEqual(first_req["request_status"], "ACTIVE")
        self.assertEqual(first_req["hospital_name"], "City Care Hospital")

        # Verify cursor and connection were properly closed
        mock_cursor.close.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.get_db_connection")
    def test_dashboard_stats_empty_tables(self, mock_get_db):
        """Test GET /dashboard/stats when all database tables have 0 rows."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"total_donors": 0},
            {"available_donors": 0},
            {"active_emergency_requests": 0}
        ]
        mock_cursor.fetchall.return_value = []

        response = self.client.get("/dashboard/stats")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data["total_donors"], 0)
        self.assertEqual(data["available_donors"], 0)
        self.assertEqual(data["active_emergency_requests"], 0)
        self.assertEqual(data["recent_requests"], [])

    @patch("app.get_db_connection")
    def test_dashboard_stats_fewer_than_five_requests(self, mock_get_db):
        """Test GET /dashboard/stats when only 2 requests exist in the database."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"total_donors": 5},
            {"available_donors": 3},
            {"active_emergency_requests": 1}
        ]
        mock_cursor.fetchall.return_value = [
            {
                "request_id": 2,
                "blood_group_required": "B-",
                "units_required": 1,
                "emergency_level": "URGENT",
                "request_status": "ACTIVE",
                "request_date": datetime.datetime(2026, 10, 24, 9, 0, 0),
                "hospital_id": 1,
                "recipient_id": None,
                "hospital_name": "City Care Hospital",
                "hospital_city": "Pune"
            },
            {
                "request_id": 1,
                "blood_group_required": "A+",
                "units_required": 2,
                "emergency_level": "STANDARD",
                "request_status": "FULFILLED",
                "request_date": datetime.datetime(2026, 10, 23, 8, 0, 0),
                "hospital_id": 1,
                "recipient_id": None,
                "hospital_name": "City Care Hospital",
                "hospital_city": "Pune"
            }
        ]

        response = self.client.get("/dashboard/stats")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data["total_donors"], 5)
        self.assertEqual(data["available_donors"], 3)
        self.assertEqual(data["active_emergency_requests"], 1)
        self.assertEqual(len(data["recent_requests"]), 2)
        self.assertEqual(data["recent_requests"][0]["request_id"], 2)
        self.assertEqual(data["recent_requests"][1]["request_id"], 1)

    @patch("app.get_db_connection")
    def test_dashboard_stats_handles_none_counts_safely(self, mock_get_db):
        """Test GET /dashboard/stats handles None/null count values gracefully."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"total_donors": None},
            {"available_donors": None},
            {"active_emergency_requests": None}
        ]
        mock_cursor.fetchall.return_value = []

        response = self.client.get("/dashboard/stats")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data["total_donors"], 0)
        self.assertEqual(data["available_donors"], 0)
        self.assertEqual(data["active_emergency_requests"], 0)
        self.assertEqual(data["recent_requests"], [])

    @patch("app.get_db_connection")
    def test_dashboard_stats_db_connection_failure(self, mock_get_db):
        """Test GET /dashboard/stats handles database connection errors with HTTP 500."""
        mock_get_db.side_effect = Exception("Can't connect to MySQL server on 'localhost'")

        response = self.client.get("/dashboard/stats")
        self.assertEqual(response.status_code, 500)

        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("Failed to load dashboard statistics", data["error"])

    @patch("app.get_db_connection")
    def test_dashboard_stats_query_execution_failure(self, mock_get_db):
        """Test GET /dashboard/stats safely rolls back/closes when query execution fails."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.execute.side_effect = Exception("Query execution error: Table crashed")

        response = self.client.get("/dashboard/stats")
        self.assertEqual(response.status_code, 500)

        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("Failed to load dashboard statistics", data["error"])
        mock_db.close.assert_called_once()


class TestDashboardTemplateMarkup(unittest.TestCase):
    """Test frontend template integration for the Dashboard Overview section."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_homepage_contains_dashboard_elements(self):
        """Ensure templates/index.html includes the dashboard section and all required element IDs."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Dashboard Section and Nav
        self.assertIn('id="dashboard-overview"', html)
        self.assertIn('href="#dashboard-overview"', html)

        # 4 Statistic Components
        self.assertIn('id="dash-total-donors"', html)
        self.assertIn('id="dash-available-donors"', html)
        self.assertIn('id="dash-active-emergencies"', html)
        self.assertIn('id="dash-recent-card-container"', html)

        # Recent Requests List / Table
        self.assertIn('id="dash-recent-table"', html)
        self.assertIn('id="dash-recent-tbody"', html)
        self.assertIn('id="dash-recent-count-tag"', html)

        # Interactive states & Refresh button
        self.assertIn('id="btn-refresh-dashboard"', html)
        self.assertIn('id="dash-error-state"', html)
        self.assertIn('id="dash-recent-loading"', html)
        self.assertIn('id="dash-recent-empty"', html)
        self.assertIn('id="dash-last-updated"', html)


if __name__ == "__main__":
    unittest.main()
