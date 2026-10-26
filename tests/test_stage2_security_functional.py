"""
Unit and Integration Tests for BloodLink Stage 2:
Advanced CSRF & Referer Verification, Matching DSA Optimizations, and Edge Case Handling.
Covers:
- CSRF Same-Origin acceptance (Origin matches Host)
- CSRF Cross-Origin rejection (Origin != Host -> HTTP 403)
- CSRF Referer Fallback acceptance (Same-origin Referer when Origin is omitted)
- CSRF Referer Fallback rejection (Cross-origin Referer -> HTTP 403)
- CSRF W3C Sec-Fetch-Site: cross-site rejection (HTTP 403)
- CSRF Missing Origin and Referer (API / CLI / test client allowed through)
- CSRF Malformed Origin / Referer error handling (HTTP 403)
- Bubble Sort early-termination optimization and stability
- Blood group string normalization (whitespace and case-insensitivity)
- Resilient dictionary lookup (.get) in donor matching
"""

import unittest
from unittest.mock import MagicMock, patch

from app import app
from matching import is_compatible, bubble_sort, find_best_donors


class TestStage2SecurityAndFunctional(unittest.TestCase):
    """Test suite covering Stage 2 CSRF, Referer, and DSA edge case handling."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # =========================================================================
    # 1. Advanced CSRF & Same-Origin Verification
    # =========================================================================

    @patch("app.get_db_connection")
    def test_csrf_same_origin_accepted(self, mock_get_db):
        """Request with matching Origin header succeeds."""
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
        mock_cursor.lastrowid = 301

        headers = {
            "Host": "localhost:5000",
            "Origin": "http://localhost:5000"
        }
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14}, headers=headers)
        self.assertEqual(res.status_code, 201)

    def test_csrf_cross_origin_rejected_with_403(self):
        """Request with mismatched Origin header is rejected with 403."""
        headers = {
            "Host": "localhost:5000",
            "Origin": "https://attacker-phishing-site.org"
        }
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14}, headers=headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("cross-origin request rejected", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_csrf_missing_origin_with_same_origin_referer_accepted(self, mock_get_db):
        """When Origin is omitted, a valid same-origin Referer is accepted."""
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
        mock_cursor.lastrowid = 302

        headers = {
            "Host": "localhost:5000",
            "Referer": "http://localhost:5000/donor/dashboard"
        }
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14}, headers=headers)
        self.assertEqual(res.status_code, 201)

    def test_csrf_missing_origin_with_cross_origin_referer_rejected(self):
        """When Origin is omitted, a cross-origin Referer is rejected with 403."""
        headers = {
            "Host": "localhost:5000",
            "Referer": "https://malicious-external-forum.net/post"
        }
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14}, headers=headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("cross-origin referer rejected", res.get_json()["error"].lower())

    def test_csrf_sec_fetch_site_cross_site_rejected(self):
        """W3C Fetch Metadata Sec-Fetch-Site: cross-site is rejected with 403."""
        headers = {
            "Host": "localhost:5000",
            "Sec-Fetch-Site": "cross-site"
        }
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14}, headers=headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("cross-origin request rejected", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_csrf_missing_origin_and_referer_allowed_for_api_clients(self, mock_get_db):
        """When both Origin and Referer are omitted (e.g. non-browser API clients or unit tests), request proceeds."""
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
        mock_cursor.lastrowid = 303

        # Neither Origin nor Referer provided
        headers = {
            "Host": "localhost:5000"
        }
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14}, headers=headers)
        self.assertEqual(res.status_code, 201)

    def test_csrf_malformed_origin_rejected(self):
        """Malformed Origin header is safely handled and rejected with 403."""
        headers = {
            "Host": "localhost:5000",
            "Origin": "http://"  # Missing netloc / invalid host
        }
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14}, headers=headers)
        self.assertEqual(res.status_code, 403)

    # =========================================================================
    # 2. DSA & Matching Optimization Tests
    # =========================================================================

    def test_bubble_sort_optimizes_already_sorted_donors(self):
        """Bubble sort correctly terminates early when donors are already in descending score order."""
        donors = [
            {"donor_id": 1, "name": "A", "matching_score": 80},
            {"donor_id": 2, "name": "B", "matching_score": 60},
            {"donor_id": 3, "name": "C", "matching_score": 40}
        ]
        sorted_donors = bubble_sort(donors)
        self.assertEqual([d["donor_id"] for d in sorted_donors], [1, 2, 3])

    def test_bubble_sort_correctly_orders_unsorted_donors(self):
        """Bubble sort sorts donors in descending order of matching_score."""
        donors = [
            {"donor_id": 1, "name": "A", "matching_score": 40},
            {"donor_id": 2, "name": "B", "matching_score": 80},
            {"donor_id": 3, "name": "C", "matching_score": 60}
        ]
        sorted_donors = bubble_sort(donors)
        self.assertEqual([d["donor_id"] for d in sorted_donors], [2, 3, 1])
        self.assertEqual(sorted_donors[0]["matching_score"], 80)
        self.assertEqual(sorted_donors[1]["matching_score"], 60)
        self.assertEqual(sorted_donors[2]["matching_score"], 40)

    def test_compatibility_normalization_whitespace_and_case(self):
        """is_compatible normalizes leading/trailing whitespace and case."""
        self.assertTrue(is_compatible(" o- ", " AB+ "))
        self.assertTrue(is_compatible("o+", "a+"))
        self.assertTrue(is_compatible("a-", "ab-"))
        self.assertFalse(is_compatible("b+", "a+"))
        self.assertFalse(is_compatible("invalid", "O+"))

    def test_find_best_donors_normalizes_case_and_handles_missing_keys(self):
        """find_best_donors works with lowercase blood groups and missing dictionary keys."""
        donors = [
            {"donor_id": 1, "name": "Ravi", "blood_group": "o+", "availability": 1, "location": "Pune"},
            {"donor_id": 2, "name": "Sita", "blood_group": "A+", "availability": 1, "location": "Mumbai"},
            {"donor_id": 3, "name": "Incomplete Donor"}  # Missing blood_group and availability
        ]
        # Recipient needing O+ in Pune
        matched = find_best_donors(donors, "o+", "Pune")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["donor_id"], 1)
        self.assertEqual(matched[0]["matching_score"], 80)


if __name__ == "__main__":
    unittest.main()
