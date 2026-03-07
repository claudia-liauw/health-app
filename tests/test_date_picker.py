"""Tests: date picker works correctly on all dashboard routes."""


class TestStepsDatePicker:
    """Date picker on the steps page (Fitbit user only — no-Fitbit ignores it)."""

    def test_default_date_loads(self, fitbit_client, mock_fitbit_api):
        """Steps page loads with today's date when no date param is given."""
        resp = fitbit_client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Steps" in resp.data

    def test_valid_past_date(self, fitbit_client, mock_fitbit_api):
        """Steps page loads successfully with a valid past date."""
        resp = fitbit_client.get("/?date=2025-01-15", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Steps" in resp.data
        # The date value should appear in the date input
        assert b"2025-01-15" in resp.data

    def test_invalid_date_does_not_crash(self, fitbit_client, mock_fitbit_api):
        """An invalid date string falls back to today — page still loads."""
        resp = fitbit_client.get("/?date=not-a-date", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Steps" in resp.data

    def test_future_date_clamped(self, fitbit_client, mock_fitbit_api):
        """A future date is clamped to today — page still loads."""
        resp = fitbit_client.get("/?date=2099-01-01", follow_redirects=True)
        assert resp.status_code == 200
        assert b"2099-01-01" not in resp.data

    def test_no_fitbit_date_picker_ignored(self, no_fitbit_client):
        """No-Fitbit user always sees the demo date regardless of ?date param."""
        resp = no_fitbit_client.get("/?date=2025-01-15", follow_redirects=True)
        assert resp.status_code == 200
        # Should show the hardcoded demo date, not the requested one
        assert b"2016-04-12" in resp.data
        assert b"13162" in resp.data


class TestSleepDatePicker:
    """Date picker on the sleep page."""

    def test_valid_past_date(self, fitbit_client, mock_fitbit_api):
        resp = fitbit_client.get("/sleep?date=2025-01-15", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Hours slept" in resp.data
        assert b"2025-01-15" in resp.data

    def test_invalid_date_does_not_crash(self, fitbit_client, mock_fitbit_api):
        resp = fitbit_client.get("/sleep?date=bad", follow_redirects=True)
        assert resp.status_code == 200

    def test_no_fitbit_shows_demo_date(self, no_fitbit_client):
        resp = no_fitbit_client.get("/sleep?date=2025-01-15", follow_redirects=True)
        assert resp.status_code == 200
        assert b"2016-04-17" in resp.data


class TestHeartDatePicker:
    """Date picker on the heart-rate page."""

    def test_valid_past_date(self, fitbit_client, mock_fitbit_api):
        resp = fitbit_client.get("/heart-rate?date=2025-01-15", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Heart" in resp.data

    def test_date_stored_in_session(self, fitbit_client, mock_fitbit_api):
        """After visiting with a date, re-visiting without a date reuses it."""
        fitbit_client.get("/heart-rate?date=2025-01-15", follow_redirects=True)
        resp = fitbit_client.get("/heart-rate", follow_redirects=True)
        assert resp.status_code == 200
        # The stored date should still be reflected
        assert b"2025-01-15" in resp.data

    def test_invalid_date_does_not_crash(self, fitbit_client, mock_fitbit_api):
        resp = fitbit_client.get("/heart-rate?date=xyz", follow_redirects=True)
        assert resp.status_code == 200

    def test_no_fitbit_shows_demo_date(self, no_fitbit_client):
        resp = no_fitbit_client.get("/heart-rate?date=2025-01-15", follow_redirects=True)
        assert resp.status_code == 200
        assert b"2016-04-12" in resp.data
