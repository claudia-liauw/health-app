"""Tests: public About page at /."""

GITHUB = b"https://github.com/claudia-liauw/health-app"


class TestAboutPage:
    def test_logged_out_home_is_about(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"About" in resp.data
        assert "/login" not in resp.headers.get("Location", "")

    def test_does_not_redirect_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 200

    def test_describes_the_app(self, client):
        resp = client.get("/")
        body = resp.data
        assert b"steps" in body.lower()
        assert b"sleep" in body.lower()
        assert b"heart" in body.lower()
        assert b"Fitbit" in body
        assert b"chat" in body.lower()

    def test_github_link(self, client):
        resp = client.get("/")
        assert GITHUB in resp.data

    def test_not_medical_advice(self, client):
        resp = client.get("/")
        assert b"This is not medical advice." in resp.data

    def test_logged_in_home_is_still_about(self, no_fitbit_client):
        resp = no_fitbit_client.get("/")
        assert resp.status_code == 200
        assert b"This is not medical advice." in resp.data
        assert b"13162" not in resp.data


class TestNavbar:
    def test_logged_out_nav_has_github(self, client):
        resp = client.get("/")
        assert b"https://github.com/claudia-liauw/health-app" in resp.data
        assert b'aria-label="GitHub"' in resp.data
        assert b"bi-github" in resp.data

    def test_logged_in_nav_steps_goes_to_steps(self, no_fitbit_client):
        resp = no_fitbit_client.get("/")
        assert b'href="/steps"' in resp.data
        assert b">Steps<" in resp.data

    def test_logged_in_nav_has_github(self, no_fitbit_client):
        resp = no_fitbit_client.get("/")
        assert b'aria-label="GitHub"' in resp.data
        assert b"bi-github" in resp.data
