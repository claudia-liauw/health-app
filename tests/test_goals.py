"""Tests: user can set goals and they display correctly on the plots."""

from app import engine
from sqlalchemy import text


class TestProfileGoals:
    """Setting and updating goals via /profile."""

    def test_default_goals_are_create_one(self, no_fitbit_client):
        """New user's profile shows 'Create one' for both goals."""
        resp = no_fitbit_client.get("/profile")
        assert resp.status_code == 200
        assert b"Create one" in resp.data

    def test_set_step_goal(self, no_fitbit_client):
        """Setting a step goal persists and shows on the profile page."""
        no_fitbit_client.post("/profile", data={"step": "10000", "sleep": ""})
        resp = no_fitbit_client.get("/profile")
        assert b"10000" in resp.data

    def test_set_sleep_goal(self, no_fitbit_client):
        """Setting a sleep goal persists and shows on the profile page."""
        no_fitbit_client.post("/profile", data={"step": "", "sleep": "8"})
        resp = no_fitbit_client.get("/profile")
        assert b"8" in resp.data

    def test_negative_step_goal_resets(self, no_fitbit_client):
        """A negative step goal resets to 'Create one'."""
        no_fitbit_client.post("/profile", data={"step": "-5", "sleep": ""})
        resp = no_fitbit_client.get("/profile")
        assert b"Create one" in resp.data

    def test_non_numeric_step_goal_resets(self, no_fitbit_client):
        """A non-numeric step goal resets to 'Create one'."""
        no_fitbit_client.post("/profile", data={"step": "abc", "sleep": ""})
        resp = no_fitbit_client.get("/profile")
        assert b"Create one" in resp.data

    def test_blank_goal_preserves_original(self, no_fitbit_client):
        """Submitting a blank goal keeps the existing value."""
        # First set a goal
        no_fitbit_client.post("/profile", data={"step": "10000", "sleep": "8"})
        # Then submit empty — should keep 10000 and 8
        no_fitbit_client.post("/profile", data={"step": "", "sleep": ""})
        resp = no_fitbit_client.get("/profile")
        assert b"10000" in resp.data


class TestGoalOnStepsPlot:
    """Step goal appears on the steps dashboard."""

    def test_no_goal_shows_create_link(self, no_fitbit_client):
        """With default 'Create one', the steps page shows a link to set a goal."""
        resp = no_fitbit_client.get("/", follow_redirects=True)
        assert b"No goal set" in resp.data
        assert b"/profile" in resp.data

    def test_step_goal_displayed_on_steps_page(self, no_fitbit_client):
        """After setting a goal, steps page shows it formatted as '/10000'."""
        no_fitbit_client.post("/profile", data={"step": "10000", "sleep": ""})
        resp = no_fitbit_client.get("/", follow_redirects=True)
        assert b"/10000" in resp.data

    def test_target_reached_when_exceeded(self, no_fitbit_client):
        """Demo total steps (13162) exceed a goal of 5000 → 'Target reached!'."""
        no_fitbit_client.post("/profile", data={"step": "5000", "sleep": ""})
        resp = no_fitbit_client.get("/", follow_redirects=True)
        assert b"Target reached!" in resp.data

    def test_target_not_reached(self, no_fitbit_client):
        """Demo total steps (13162) do not reach a goal of 20000."""
        no_fitbit_client.post("/profile", data={"step": "20000", "sleep": ""})
        resp = no_fitbit_client.get("/", follow_redirects=True)
        assert b"Target not yet reached" in resp.data


class TestGoalOnSleepPlot:
    """Sleep goal appears on the sleep dashboard."""

    def test_no_goal_shows_create_link(self, no_fitbit_client):
        resp = no_fitbit_client.get("/sleep", follow_redirects=True)
        assert b"No goal set" in resp.data
        assert b"/profile" in resp.data

    def test_sleep_goal_displayed_on_sleep_page(self, no_fitbit_client):
        """After setting a goal, sleep page shows it formatted as '/8.0h'."""
        no_fitbit_client.post("/profile", data={"step": "", "sleep": "8"})
        resp = no_fitbit_client.get("/sleep", follow_redirects=True)
        assert b"/8.0h" in resp.data

    def test_sleep_target_reached(self, no_fitbit_client):
        """Demo hours slept (11.67) exceed a goal of 8 → 'Sleep target reached!'."""
        no_fitbit_client.post("/profile", data={"step": "", "sleep": "8"})
        resp = no_fitbit_client.get("/sleep", follow_redirects=True)
        assert b"Sleep target reached!" in resp.data

    def test_sleep_target_not_reached(self, no_fitbit_client):
        """Demo hours slept (11.67) don't reach 15 → 'Sleep target not reached.'."""
        no_fitbit_client.post("/profile", data={"step": "", "sleep": "15"})
        resp = no_fitbit_client.get("/sleep", follow_redirects=True)
        assert b"Sleep target not reached" in resp.data


class TestGoalOnFitbitPlot:
    """Goals also work for Fitbit users (mocked API)."""

    def test_step_goal_with_fitbit(self, fitbit_client, mock_fitbit_api):
        """Fitbit user sees step goal on the steps page after setting it."""
        fitbit_client.post("/profile", data={"step": "5000", "sleep": ""})
        resp = fitbit_client.get("/", follow_redirects=True)
        assert b"/5000" in resp.data
        # Mock returns 8500 total steps → target reached
        assert b"Target reached!" in resp.data

    def test_sleep_goal_with_fitbit(self, fitbit_client, mock_fitbit_api):
        """Fitbit user sees sleep goal on the sleep page after setting it."""
        fitbit_client.post("/profile", data={"step": "", "sleep": "6"})
        resp = fitbit_client.get("/sleep", follow_redirects=True)
        assert b"/6.0h" in resp.data
        # Mock returns 420 min (7h) → target reached
        assert b"Sleep target reached!" in resp.data
