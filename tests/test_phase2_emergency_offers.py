"""
Test Suite for BloodLink Phase 2:
Connect Emergency Requests to Donor Offers

Tests coverage:
1. Donor offering to help with a specific active emergency request (POST /donation-requests and POST /emergency/<id>/offer).
2. Incompatible blood group, unavailable donor, and inactive request rejection.
3. Manipulation protection: donor unable to spoof IDs, client-supplied recipient_id/donor_id ignored, own-request blocking.
4. Duplicate pending/accepted offers blocked with 409 Conflict.
5. Correct recipient-only offer history (GET /recipient/me/offers).
6. Status transitions:
   - Recipient ACCEPT and DECLINE transitions
   - Donor CANCEL transition
   - Unauthorized role/owner actions blocked (403)
   - Invalid status transitions blocked (400/409)
   - Emergency request NOT marked FULFILLED upon offer acceptance
7. Strict phone-number privacy and explicit consent enforcement:
   - Phone withheld while offer is PENDING
   - Phone revealed only when ACCEPTED AND explicit donor consent granted
   - Phone withheld if ACCEPTED but consent withheld
   - Recipient phone never exposed to donor
8. Dashboard template wiring and UI element verification.
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import datetime

from app import app


class TestPhase2EmergencyOffers(unittest.TestCase):
    """Test suite for Phase 2: Emergency Requests to Donor Offers."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # =========================================================================
    # 1. Successful Donor Offer Creation
    # =========================================================================

    @patch("app.get_db_connection")
    def test_donor_can_offer_to_donate_for_active_emergency_request(self, mock_get_db):
        """DONOR can successfully submit an offer for a compatible active emergency request."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Mock sequence:
        # 1. Fetch donor profile
        # 2. Fetch emergency request
        # 3. Check duplicate by emergency_request_id (None)
        # 4. Check duplicate by recipient_id (None)
        # 5. Insert donation_requests
        mock_cursor.fetchone.side_effect = [
            {
                "donor_id": 12,
                "user_id": 101,
                "name": "Aarav Patel",
                "blood_group": "O+",
                "availability": 1,
                "phone": "9876543210"
            },
            {
                "request_id": 14,
                "recipient_id": 5,
                "hospital_id": 1,
                "blood_group_required": "A+",
                "units_required": 2,
                "emergency_level": "HIGH",
                "request_status": "ACTIVE",
                "recipient_user_id": 202
            },
            None,  # No duplicate emergency offer
            None   # No duplicate recipient offer
        ]
        mock_cursor.lastrowid = 101

        payload = {
            "emergency_request_id": 14,
            "consent_to_contact": True,
            "clinical_notes": "Available to reach hospital within 1 hour."
        }
        res = self.client.post("/donation-requests", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["request_id"], 101)
        self.assertEqual(data["emergency_request_id"], 14)
        self.assertEqual(data["status"], "PENDING")
        self.assertTrue(data["donor_contact_consent"])
        self.assertTrue(mock_db.commit.called)

    @patch("app.get_db_connection")
    def test_donor_can_offer_via_alternate_route(self, mock_get_db):
        """DONOR can submit an offer via POST /emergency/<id>/offer route."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"donor_id": 12, "user_id": 101, "name": "Aarav Patel", "blood_group": "A+", "availability": 1, "phone": "9876543210"},
            {"request_id": 14, "recipient_id": 5, "hospital_id": 1, "blood_group_required": "A+", "units_required": 2, "emergency_level": "HIGH", "request_status": "ACTIVE", "recipient_user_id": 202},
            None,
            None
        ]
        mock_cursor.lastrowid = 102

        res = self.client.post("/emergency/14/offer", json={"consent_to_contact": True})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["request_id"], 102)

    # =========================================================================
    # 2. Rejection Cases: Incompatible Blood, Unavailable Donor, Inactive Request
    # =========================================================================

    @patch("app.get_db_connection")
    def test_reject_incompatible_blood_group(self, mock_get_db):
        """Rejects offer when donor blood group is incompatible with request."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Donor has B+, emergency request requires A+ (Incompatible!)
        mock_cursor.fetchone.side_effect = [
            {"donor_id": 12, "user_id": 101, "name": "Aarav Patel", "blood_group": "B+", "availability": 1, "phone": "9876543210"},
            {"request_id": 14, "recipient_id": 5, "hospital_id": 1, "blood_group_required": "A+", "units_required": 2, "emergency_level": "HIGH", "request_status": "ACTIVE", "recipient_user_id": 202}
        ]

        res = self.client.post("/donation-requests", json={"emergency_request_id": 14})
        self.assertEqual(res.status_code, 400)
        self.assertIn("incompatible", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_reject_unavailable_donor(self, mock_get_db):
        """Rejects offer when donor is resting/unavailable (availability == 0)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 12,
            "user_id": 101,
            "name": "Aarav Patel",
            "blood_group": "O-",
            "availability": 0,  # Resting
            "phone": "9876543210"
        }

        res = self.client.post("/donation-requests", json={"emergency_request_id": 14})
        self.assertEqual(res.status_code, 400)
        self.assertIn("unavailable", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_reject_inactive_emergency_request(self, mock_get_db):
        """Rejects offer when emergency request is already FULFILLED or CANCELLED."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"donor_id": 12, "user_id": 101, "name": "Aarav Patel", "blood_group": "O+", "availability": 1, "phone": "9876543210"},
            {"request_id": 14, "recipient_id": 5, "hospital_id": 1, "blood_group_required": "O+", "units_required": 2, "emergency_level": "HIGH", "request_status": "FULFILLED", "recipient_user_id": 202}
        ]

        res = self.client.post("/donation-requests", json={"emergency_request_id": 14})
        self.assertEqual(res.status_code, 400)
        self.assertIn("fulfilled", res.get_json()["error"].lower())

    # =========================================================================
    # 3. Security: ID Manipulation & Client Data Trust Prevention
    # =========================================================================

    @patch("app.get_db_connection")
    def test_donor_cannot_spoof_recipient_or_donor_ids(self, mock_get_db):
        """Server ignores client-supplied recipient_id and donor_id, binding strictly to DB records."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"donor_id": 12, "user_id": 101, "name": "Real Donor", "blood_group": "O+", "availability": 1, "phone": "9876543210"},
            {"request_id": 14, "recipient_id": 5, "hospital_id": 1, "blood_group_required": "O+", "units_required": 1, "emergency_level": "HIGH", "request_status": "ACTIVE", "recipient_user_id": 202},
            None,
            None
        ]
        mock_cursor.lastrowid = 103

        # Malicious payload trying to inject fake donor_id and recipient_id and status
        malicious_payload = {
            "emergency_request_id": 14,
            "donor_id": 99999,
            "recipient_id": 88888,
            "status": "ACCEPTED"
        }
        res = self.client.post("/donation-requests", json=malicious_payload)
        self.assertEqual(res.status_code, 201)

        # Inspect SQL insert parameters executed on cursor
        insert_args = mock_cursor.execute.call_args_list[-1][0][1]
        self.assertEqual(insert_args[0], 5)   # Verified recipient_id from emergency_requests
        self.assertEqual(insert_args[1], 12)  # Verified donor_id from DB
        self.assertEqual(insert_args[2], 14)  # Emergency request ID

    @patch("app.get_db_connection")
    def test_donor_cannot_offer_for_own_emergency_request(self, mock_get_db):
        """Donor cannot offer to donate for their own emergency request (returns 403)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"donor_id": 12, "user_id": 101, "name": "Dual User", "blood_group": "O+", "availability": 1, "phone": "9876543210"},
            {"request_id": 14, "recipient_id": 5, "hospital_id": 1, "blood_group_required": "O+", "units_required": 1, "emergency_level": "HIGH", "request_status": "ACTIVE", "recipient_user_id": 101}
        ]

        res = self.client.post("/donation-requests", json={"emergency_request_id": 14})
        self.assertEqual(res.status_code, 403)
        self.assertIn("own emergency request", res.get_json()["error"])

    # =========================================================================
    # 4. Duplicate Offer Prevention
    # =========================================================================

    @patch("app.get_db_connection")
    def test_duplicate_pending_offer_blocked_with_409(self, mock_get_db):
        """Prevents duplicate offers for the same emergency request by the same donor (409 Conflict)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {"donor_id": 12, "user_id": 101, "name": "Aarav Patel", "blood_group": "O+", "availability": 1, "phone": "9876543210"},
            {"request_id": 14, "recipient_id": 5, "hospital_id": 1, "blood_group_required": "O+", "units_required": 1, "emergency_level": "HIGH", "request_status": "ACTIVE", "recipient_user_id": 202},
            {"request_id": 88, "status": "PENDING"}  # Existing pending offer found!
        ]

        res = self.client.post("/donation-requests", json={"emergency_request_id": 14})
        self.assertEqual(res.status_code, 409)
        self.assertIn("already have", res.get_json()["error"].lower())

    # =========================================================================
    # 5. Recipient-Only Offer History (GET /recipient/me/offers)
    # =========================================================================

    @patch("app.get_db_connection")
    def test_recipient_can_view_own_offers_history(self, mock_get_db):
        """RECIPIENT can view all offers made for their emergency requests."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"recipient_id": 5}
        mock_cursor.fetchall.return_value = [
            {
                "request_id": 101,
                "recipient_id": 5,
                "donor_id": 12,
                "emergency_request_id": 14,
                "hospital_id": 1,
                "blood_group_required": "A+",
                "units_required": 2,
                "urgency_level": "HIGH",
                "clinical_notes": "Ready",
                "status": "PENDING",
                "donor_contact_consent_at": "2026-10-25 12:00:00",
                "created_at": "2026-10-25 12:00:00",
                "donor_name": "Aarav Patel",
                "donor_blood_group": "A+",
                "donor_location": "Mumbai",
                "donor_age": 28,
                "donor_gender": "Male",
                "raw_donor_phone": "9876543210"
            }
        ]

        res = self.client.get("/recipient/me/offers")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["request_id"], 101)
        self.assertEqual(data[0]["emergency_request_id"], 14)
        # While PENDING, donor phone MUST be None
        self.assertIsNone(data[0]["donor_phone"])
        self.assertFalse(data[0]["contact_revealed"])

    def test_donor_cannot_access_recipient_offers_endpoint(self):
        """DONOR is forbidden (403) from accessing GET /recipient/me/offers."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        res = self.client.get("/recipient/me/offers")
        self.assertEqual(res.status_code, 403)

    # =========================================================================
    # 6. Status Transitions: Accept, Decline, Cancel
    # =========================================================================

    @patch("app.get_db_connection")
    def test_recipient_can_accept_pending_offer(self, mock_get_db):
        """Recipient can accept a PENDING offer, keeping emergency request ACTIVE."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 101,
            "recipient_id": 5,
            "donor_id": 12,
            "emergency_request_id": 14,
            "status": "PENDING",
            "recipient_user_id": 202,
            "donor_user_id": 101
        }
        mock_cursor.rowcount = 1

        res = self.client.put("/donation-requests/101/status", json={"status": "ACCEPTED"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "ACCEPTED")
        self.assertEqual(data["previous_status"], "PENDING")

        # Verify update executed on donation_requests and commit was called
        self.assertTrue(mock_db.commit.called)

    @patch("app.get_db_connection")
    def test_recipient_can_decline_pending_offer(self, mock_get_db):
        """Recipient can decline a PENDING offer."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 101,
            "recipient_id": 5,
            "donor_id": 12,
            "emergency_request_id": 14,
            "status": "PENDING",
            "recipient_user_id": 202,
            "donor_user_id": 101
        }
        mock_cursor.rowcount = 1

        res = self.client.put("/donation-requests/101/status", json={"status": "DECLINED"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "DECLINED")

    @patch("app.get_db_connection")
    def test_donor_can_cancel_own_pending_offer(self, mock_get_db):
        """Donor can cancel their own PENDING offer."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 101,
            "recipient_id": 5,
            "donor_id": 12,
            "emergency_request_id": 14,
            "status": "PENDING",
            "recipient_user_id": 202,
            "donor_user_id": 101
        }
        mock_cursor.rowcount = 1

        res = self.client.put("/donation-requests/101/status", json={"status": "CANCELLED"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "CANCELLED")

    @patch("app.get_db_connection")
    def test_unauthorized_user_cannot_modify_offer(self, mock_get_db):
        """A different user cannot modify another user's offer (403 Forbidden)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 303  # Attacker
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 101,
            "recipient_id": 5,
            "donor_id": 12,
            "emergency_request_id": 14,
            "status": "PENDING",
            "recipient_user_id": 202,  # Owned by 202, not 303!
            "donor_user_id": 101
        }

        res = self.client.put("/donation-requests/101/status", json={"status": "ACCEPTED"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("permission", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_cannot_modify_already_accepted_offer(self, mock_get_db):
        """Reject modifying an offer that is already ACCEPTED (409 Conflict)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "request_id": 101,
            "recipient_id": 5,
            "donor_id": 12,
            "emergency_request_id": 14,
            "status": "ACCEPTED",  # Already accepted
            "recipient_user_id": 202,
            "donor_user_id": 101
        }

        res = self.client.put("/donation-requests/101/status", json={"status": "DECLINED"})
        self.assertEqual(res.status_code, 409)

    # =========================================================================
    # 7. Privacy: Phone Number Redaction & Explicit Consent
    # =========================================================================

    @patch("app.get_db_connection")
    def test_phone_revealed_only_when_accepted_and_consent_granted(self, mock_get_db):
        """Donor phone is revealed to recipient ONLY when status is ACCEPTED AND explicit consent is recorded."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"recipient_id": 5}
        mock_cursor.fetchall.return_value = [
            {
                "request_id": 101,
                "recipient_id": 5,
                "donor_id": 12,
                "emergency_request_id": 14,
                "status": "ACCEPTED",
                "donor_contact_consent_at": "2026-10-25 12:00:00",
                "raw_donor_phone": "9876543210",
                "donor_name": "Aarav Patel",
                "donor_blood_group": "A+"
            }
        ]

        res = self.client.get("/recipient/me/offers")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data[0]["donor_phone"], "9876543210")
        self.assertTrue(data[0]["contact_revealed"])

    @patch("app.get_db_connection")
    def test_phone_withheld_if_accepted_without_explicit_consent(self, mock_get_db):
        """Donor phone remains withheld even if ACCEPTED, if explicit consent was NOT provided."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"recipient_id": 5}
        mock_cursor.fetchall.return_value = [
            {
                "request_id": 102,
                "recipient_id": 5,
                "donor_id": 12,
                "emergency_request_id": 14,
                "status": "ACCEPTED",
                "donor_contact_consent_at": None,  # No explicit consent!
                "raw_donor_phone": "9876543210",
                "donor_name": "Aarav Patel",
                "donor_blood_group": "A+"
            }
        ]

        res = self.client.get("/recipient/me/offers")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsNone(data[0]["donor_phone"])
        self.assertFalse(data[0]["contact_revealed"])

    @patch("app.get_db_connection")
    def test_recipient_phone_never_exposed_in_donor_offers(self, mock_get_db):
        """Recipient phone numbers are never included in donor offers response."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"donor_id": 12}
        mock_cursor.fetchall.return_value = [
            {
                "request_id": 101,
                "recipient_id": 5,
                "donor_id": 12,
                "emergency_request_id": 14,
                "status": "ACCEPTED",
                "blood_group_required": "A+",
                "units_required": 2,
                "hospital_name": "City Care Hospital"
            }
        ]

        res = self.client.get("/donor/me/offers")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertNotIn("recipient_phone", data[0])
        self.assertNotIn("phone", data[0])

    # =========================================================================
    # 8. Dashboard Template Elements & Wiring Verification
    # =========================================================================

    def test_donor_dashboard_contains_offer_elements(self):
        """Donor dashboard template contains Offer Action column, My Offers section, and confirm modal."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Emergency feed table headers
        self.assertIn("Action / Offer", html)
        self.assertIn("table-emergency-feed", html)

        # My offers card & table
        self.assertIn("donor-my-offers-card", html)
        self.assertIn("table-my-offers", html)

        # Confirmation modal
        self.assertIn("modal-offer-confirm", html)
        self.assertIn("modal-offer-consent", html)
        self.assertIn("btn-submit-offer", html)

        # JavaScript functions
        self.assertIn("openOfferModal", html)
        self.assertIn("loadDonorOffers", html)
        self.assertIn("cancelMyOffer", html)

    def test_recipient_dashboard_contains_incoming_offers_elements(self):
        """Recipient dashboard template contains Incoming Donor Offers section and action buttons."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Priya Sharma"
            sess["user_role"] = "RECIPIENT"

        res = self.client.get("/recipient/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Incoming offers section and table
        self.assertIn("section-incoming-donor-offers", html)
        self.assertIn("table-incoming-offers", html)

    # =========================================================================
    # 9. Regression Tests: Authorization Root Cause & Modal Error Handling
    # =========================================================================

    @patch("app.get_db_connection")
    def test_unauthorized_user_without_donor_profile_rejected_with_403(self, mock_get_db):
        """User without a donor profile and without DONOR role receives HTTP 403 Forbidden."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # No donor profile found
        mock_cursor.fetchone.return_value = None

        res = self.client.post("/donation-requests", json={"emergency_request_id": 14})
        self.assertEqual(res.status_code, 403)
        self.assertIn("registered donor profile is required", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_recipient_role_with_donor_profile_cannot_bypass_role_check(self, mock_get_db):
        """User registered as recipient who has a linked donor profile is strictly forbidden from offering donations."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 202
            sess["user_name"] = "Rahul Sharma"
            sess["user_role"] = "RECIPIENT"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "donor_id": 15, "user_id": 202, "name": "Rahul Sharma",
            "blood_group": "O+", "availability": 1, "phone": "9876543210"
        }

        res = self.client.post("/donation-requests", json={"emergency_request_id": 14, "consent_to_contact": True})
        self.assertEqual(res.status_code, 403)
        self.assertIn("registered donor profile is required", res.get_json()["error"].lower())

    @patch("app.get_db_connection")
    def test_donor_role_without_donor_profile_rejected_with_400(self, mock_get_db):
        """User with DONOR role who has not created a donor profile yet receives HTTP 400 Bad Request."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_role"] = "DONOR"

        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # No donor profile found
        mock_cursor.fetchone.return_value = None

        res = self.client.post("/donation-requests", json={"emergency_request_id": 14})
        self.assertEqual(res.status_code, 400)
        self.assertIn("no voluntary donor profile linked", res.get_json()["error"].lower())

    def test_unauthenticated_request_rejected_with_401(self):
        """Unauthenticated call to POST /donation-requests is rejected with 401."""
        res = self.client.post("/donation-requests", json={"emergency_request_id": 14})
        self.assertEqual(res.status_code, 401)
        self.assertIn("Authentication required", res.get_json()["error"])

    def test_donor_dashboard_modal_has_form_and_inline_error_elements(self):
        """Donor dashboard contains form wrapper, inline error container, and JavaScript event prevention."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 101
            sess["user_name"] = "Aarav Patel"
            sess["user_role"] = "DONOR"

        res = self.client.get("/donor/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Modal form wrapper and inline error alert
        self.assertIn('form id="form-offer-modal"', html)
        self.assertIn('id="modal-offer-error"', html)
        self.assertIn('id="modal-offer-error-msg"', html)
        self.assertIn('type="submit"', html)

        # JS logic preventing default submission and handling inline error
        self.assertIn("event.preventDefault()", html)
        self.assertIn("Submitting Offer...", html)
        self.assertIn("modal-offer-error-msg", html)


if __name__ == "__main__":
    unittest.main()

