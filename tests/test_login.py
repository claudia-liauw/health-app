"""Tests: both Fitbit and no-Fitbit users can log in and see dashboards."""


class TestNoFitbitLogin:
    """User without a Fitbit account."""

    def test_login_reaches_steps_dashboard(self, no_fitbit_client):
        """After login, no-Fitbit user lands on the steps page (no OAuth redirect)."""
        resp = no_fitbit_client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Steps" in resp.data

    def test_warning_shown(self, no_fitbit_client):
        """No-Fitbit user sees the warning about limited features."""
        resp = no_fitbit_client.get("/", follow_redirects=True)
        assert b"WARNING" in resp.data

    def test_demo_steps_shown(self, no_fitbit_client):
        """No-Fitbit user sees the hardcoded demo total steps (13162)."""
        resp = no_fitbit_client.get("/", follow_redirects=True)
        assert b"13162" in resp.data

    def test_sleep_page_loads(self, no_fitbit_client):
        resp = no_fitbit_client.get("/sleep", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Hours Slept" in resp.data

    def test_heart_page_loads(self, no_fitbit_client):
        resp = no_fitbit_client.get("/heart-rate", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Heart" in resp.data


class TestFitbitLogin:
    """User with a Fitbit account."""

    def test_login_redirects_to_authenticate(self, client):
        """A Fitbit user who hasn't completed OAuth gets redirected to /authenticate."""
        # Log in as the Fitbit user
        client.post("/login", data={"username": "fitbituser", "password": "fitbitpass"})
        # Try to access the dashboard — should redirect to /authenticate
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/authenticate" in resp.headers["Location"]

    def test_dashboard_loads_after_oauth(self, fitbit_client, mock_fitbit_api):
        """After OAuth (simulated by fixture), Fitbit user sees the steps page."""
        resp = fitbit_client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Steps" in resp.data
        # Should NOT show the no-Fitbit warning
        assert b"WARNING: You are not connected to Fitbit" not in resp.data

    def test_sleep_loads_after_oauth(self, fitbit_client, mock_fitbit_api):
        resp = fitbit_client.get("/sleep", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Hours Slept" in resp.data

    def test_heart_loads_after_oauth(self, fitbit_client, mock_fitbit_api):
        resp = fitbit_client.get("/heart-rate", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Heart" in resp.data


class TestLoginValidation:
    """Edge cases for login."""

    def test_wrong_password(self, client):
        resp = client.post("/login", data={"username": "testuser", "password": "wrong"})
        assert b"Invalid username or password" in resp.data

    def test_nonexistent_user(self, client):
        resp = client.post("/login", data={"username": "nobody", "password": "x"})
        assert b"Invalid username or password" in resp.data

    def test_empty_username(self, client):
        resp = client.post("/login", data={"username": "", "password": "x"})
        assert b"Must provide username" in resp.data

    def test_empty_password(self, client):
        resp = client.post("/login", data={"username": "testuser", "password": ""})
        assert b"Must provide password" in resp.data

    def test_logout_clears_session(self, no_fitbit_client):
        no_fitbit_client.get("/logout")
        # After logout, accessing / should redirect to /login
        resp = no_fitbit_client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
