"""Shared fixtures for all tests."""

import os
import tempfile
import pytest
from app import app as flask_app, engine
from sqlalchemy import text
from werkzeug.security import generate_password_hash


@pytest.fixture()
def app(tmp_path):
    """Create a test app with an in-memory SQLite DB and temp session dir."""
    # Use a temp dir for filesystem sessions
    session_dir = tmp_path / "flask_session"
    session_dir.mkdir()

    flask_app.config.update({
        "TESTING": True,
        "SESSION_FILE_DIR": str(session_dir),
    })

    # Set up tables and seed test users
    with engine.connect() as db:
        db.execute(text("DELETE FROM profile"))
        db.execute(text("DELETE FROM users"))
        db.commit()

        # User WITHOUT Fitbit
        db.execute(
            text("INSERT INTO users (username, hash, has_fitbit) VALUES (:u, :h, :f)"),
            {"u": "testuser", "h": generate_password_hash("testpass"), "f": False},
        )
        db.execute(
            text("INSERT INTO profile (username, step_goal, sleep_goal) VALUES (:u, 'Create one', 'Create one')"),
            {"u": "testuser"},
        )

        # User WITH Fitbit
        db.execute(
            text("INSERT INTO users (username, hash, has_fitbit) VALUES (:u, :h, :f)"),
            {"u": "fitbituser", "h": generate_password_hash("fitbitpass"), "f": True},
        )
        db.execute(
            text("INSERT INTO profile (username, step_goal, sleep_goal) VALUES (:u, 'Create one', 'Create one')"),
            {"u": "fitbituser"},
        )
        db.commit()

    yield flask_app

    # Clean up
    with engine.connect() as db:
        db.execute(text("DELETE FROM profile"))
        db.execute(text("DELETE FROM users"))
        db.commit()


@pytest.fixture()
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture()
def no_fitbit_client(app):
    """Logged-in test client for a user WITHOUT Fitbit (sees demo CSV data)."""
    c = app.test_client()
    c.post("/login", data={"username": "testuser", "password": "testpass"})
    return c


@pytest.fixture()
def fitbit_client(app):
    """Logged-in test client for a user WITH Fitbit.

    Bypasses real OAuth by injecting session values directly, so dashboard
    routes can be tested with mocked API responses.
    """
    c = app.test_client()
    c.post("/login", data={"username": "fitbituser", "password": "fitbitpass"})
    # Manually set the session keys that /callback would normally set
    with c.session_transaction() as sess:
        sess["fitbit_id"] = "FAKE_FITBIT_ID"
        sess["access_token"] = "FAKE_ACCESS_TOKEN"
    return c


# ---------------------------------------------------------------------------
# Canned Fitbit API responses used by mock_fitbit_api
# ---------------------------------------------------------------------------

STEPS_TODAY_JSON = {
    "activities-steps": [{"dateTime": "2025-01-15", "value": "8500"}],
}

STEPS_INTRADAY_JSON = {
    "activities-steps": [{"dateTime": "2025-01-15", "value": "8500"}],
    "activities-steps-intraday": {
        "dataset": [{"time": f"{h:02d}:00:00", "value": 350} for h in range(24)],
    },
}

STEPS_WEEK_JSON = {
    "activities-steps": [
        {"dateTime": f"2025-01-{d:02d}", "value": str(1000 * d)}
        for d in range(9, 16)
    ],
}

SLEEP_TODAY_JSON = {
    "sleep": [],
    "summary": {"totalMinutesAsleep": 420, "totalTimeInBed": 480},
}

SLEEP_DAY_JSON = {
    "sleep": [],
    "summary": {"totalMinutesAsleep": 400, "totalTimeInBed": 460},
}

HEART_INTRADAY_JSON = {
    "activities-heart": [
        {
            "dateTime": "2025-01-15",
            "value": {"restingHeartRate": 62},
        }
    ],
    "activities-heart-intraday": {
        "dataset": [{"time": f"{h:02d}:00:00", "value": 70 + h} for h in range(24)],
    },
}

HEART_WEEK_JSON = {
    "activities-heart": [
        {
            "dateTime": f"2025-01-{d:02d}",
            "value": {"restingHeartRate": 60 + d},
        }
        for d in range(9, 16)
    ],
}


def _fake_fitbit_get(url, **kwargs):
    """Return canned JSON for any Fitbit API GET request."""

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    if "activities/steps" in url:
        if "1min" in url:
            return FakeResponse(STEPS_INTRADAY_JSON)
        if "7d" in url:
            return FakeResponse(STEPS_WEEK_JSON)
        return FakeResponse(STEPS_TODAY_JSON)
    if "sleep" in url:
        return FakeResponse(SLEEP_TODAY_JSON)
    if "activities/heart" in url:
        if "1min" in url:
            return FakeResponse(HEART_INTRADAY_JSON)
        if "7d" in url:
            return FakeResponse(HEART_WEEK_JSON)
    return FakeResponse({})


@pytest.fixture()
def mock_fitbit_api(monkeypatch):
    """Patch requests.get so Fitbit API calls return canned data."""
    import src.utils
    monkeypatch.setattr(src.utils, "requests", type("mod", (), {"get": staticmethod(_fake_fitbit_get)})())
