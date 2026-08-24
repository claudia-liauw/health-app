# About Home, GitHub Link, Fitbit Disclaimer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/` a public About page, move the steps dashboard to `/steps`, add a GitHub link in the navbar (and on About), and default register to no Fitbit with a show/hide disclaimer.

**Architecture:** Split routes so `/` always renders `about.html` with no login required. The existing `steps()` view keeps `@login_required` and `@auth_required` but is mounted at `/steps`. Successful login, register, and Fitbit OAuth redirect to `/steps`; logout still redirects to `/`. Navbar brand stays `/`; the Steps item points at `/steps`. Register checkbox starts unchecked; checking it reveals “Untested with other Fitbit devices”.

**Tech Stack:** Flask, Jinja2 templates, Bootstrap 5.3 (already in `layout.html`), pytest + Flask test client (`uv run pytest`).

**Spec:** `docs/superpowers/specs/2026-08-24-about-home-design.md`

---

## File map

| File | Responsibility |
|---|---|
| Create `templates/about.html` | Public About copy, GitHub button, “This is not medical advice.” |
| Modify `app.py` | `index()` at `/`; `steps()` at `/steps`; login/register/callback redirect to `/steps` |
| Modify `templates/layout.html` | Steps `href="/steps"`; GitHub nav link for logged-in and logged-out |
| Modify `templates/register.html` | Unchecked Fitbit checkbox; disclaimer + toggle script |
| Create `tests/test_about.py` | Public `/`, GitHub URL, medical-advice line |
| Modify `tests/test_login.py` | Dashboard URLs → `/steps`; logout asserts `/steps` → `/login`; login/register redirects |
| Modify `tests/test_goals.py` | Step-dashboard GETs → `/steps` |
| Modify `tests/test_date_picker.py` | Steps date URLs → `/steps` and `/steps?date=...` |
| Modify `tests/README.md` | Document `/` as About and `/steps` as dashboard |

Do not change Fitbit OAuth logic, chat, sleep/heart routes, or the database schema.

---

### Task 1: Point existing dashboard tests at `/steps`

Existing tests treat `GET /` as the steps dashboard. Change those URLs first so they fail (no `/steps` route yet). Then later tasks make them pass.

**Files:**
- Modify: `tests/test_login.py`
- Modify: `tests/test_goals.py`
- Modify: `tests/test_date_picker.py`

- [ ] **Step 1: Update `tests/test_login.py` dashboard and logout URLs**

In `TestNoFitbitLogin` and `TestFitbitLogin`, every `get("/")` that expects the steps dashboard becomes `get("/steps")`.

`test_login_redirects_to_authenticate`: `client.get("/")` → `client.get("/steps")`.

`test_logout_clears_session`: after logout, assert **`/steps`** redirects to `/login` (not `/`). Replace the method with:

```python
    def test_logout_clears_session(self, no_fitbit_client):
        no_fitbit_client.get("/logout")
        resp = no_fitbit_client.get("/steps")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
```

- [ ] **Step 2: Update `tests/test_goals.py`**

In `TestGoalOnStepsPlot` and `test_step_goal_with_fitbit`, change `get("/", follow_redirects=True)` to `get("/steps", follow_redirects=True)`. Leave `/sleep` and `/profile` unchanged.

- [ ] **Step 3: Update `tests/test_date_picker.py` `TestStepsDatePicker` only**

Replace:

- `get("/", ...)` → `get("/steps", ...)`
- `get("/?date=...` → `get("/steps?date=...`

Do not change `/sleep` or `/heart-rate` tests.

- [ ] **Step 4: Run the retargeted tests to confirm they fail**

Run:

```bash
uv run pytest tests/test_login.py::TestNoFitbitLogin::test_login_reaches_steps_dashboard tests/test_login.py::TestFitbitLogin::test_login_redirects_to_authenticate tests/test_goals.py::TestGoalOnStepsPlot::test_no_goal_shows_create_link tests/test_date_picker.py::TestStepsDatePicker::test_no_fitbit_default_date -v
```

Expected: FAIL — `/steps` is not a route (404) or does not show the dashboard.

- [ ] **Step 5: Commit**

```bash
git add tests/test_login.py tests/test_goals.py tests/test_date_picker.py
git commit -m "$(cat <<'EOF'
test: point steps dashboard assertions at /steps

EOF
)"
```

---

### Task 2: Mount steps at `/steps` and redirect auth success there

**Files:**
- Modify: `app.py:58-61` (route decorator)
- Modify: `app.py` register success redirect (`return redirect("/")` after insert)
- Modify: `app.py` login success redirect (`return redirect("/")` after setting session)
- Modify: `app.py` callback (`return redirect("/")` after storing tokens)

- [ ] **Step 1: Change the steps route decorator**

Replace:

```python
@app.route("/")
@login_required
@auth_required
def steps():
```

with:

```python
@app.route("/steps")
@login_required
@auth_required
def steps():
```

Do not change the body of `steps()`.

- [ ] **Step 2: Redirect login, register, and callback to `/steps`**

Three replacements of `return redirect("/")` (not logout):

Register (success after `db.commit()`):

```python
                return redirect("/steps")
```

Login (after setting `session['fitbit_id']` for no-Fitbit users):

```python
        return redirect("/steps")
```

Callback (after `session['fitbit_id'] = ...`):

```python
    return redirect("/steps")
```

Leave logout as:

```python
    return redirect("/")
```

- [ ] **Step 3: Run retargeted dashboard tests**

Run:

```bash
uv run pytest tests/test_login.py tests/test_goals.py tests/test_date_picker.py -v
```

Expected: PASS (About is not implemented yet; nothing in these files still `GET /` expecting Steps except we already moved those).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "$(cat <<'EOF'
feat: serve steps dashboard at /steps

EOF
)"
```

---

### Task 3: Public About page at `/`

**Files:**
- Create: `tests/test_about.py`
- Create: `templates/about.html`
- Modify: `app.py` (add `index` immediately above the `/steps` route)

- [ ] **Step 1: Write failing About tests**

Create `tests/test_about.py`:

```python
"""Tests: public About page at /."""

GITHUB = b"https://github.com/claudia-liauw/health-app"


class TestAboutPage:
    def test_logged_out_home_is_about(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"About" in resp.data
        assert b"/login" not in resp.headers.get("Location", "")

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
```

- [ ] **Step 2: Run About tests to verify they fail**

Run:

```bash
uv run pytest tests/test_about.py -v
```

Expected: FAIL — `/` is 404 (steps moved away) or is not About.

- [ ] **Step 3: Add `index()` in `app.py`**

Place this **above** the `/steps` route:

```python
@app.route("/")
def index():
    return render_template("about.html")
```

No `@login_required`. No `@auth_required`.

- [ ] **Step 4: Create `templates/about.html`**

Match login/register card layout:

```html
{% extends "layout.html" %}

{% block title %}
    About
{% endblock %}

{% block main %}
    <div class="row justify-content-center">
        <div class="col-md-8 col-lg-6">
            <div class="card">
                <h2 class="mb-4">About</h2>
                <p>
                    A health tracker app for steps, sleep and heart rate with goal tracking
                    for steps and sleep and anomaly detection (currently inactive) for heart
                    rate. Integrates with Fitbit API to retrieve data. Includes a built-in
                    AI chat sidebar for health and activity questions.
                </p>
                <p>
                    <a class="btn btn-primary" href="https://github.com/claudia-liauw/health-app"
                       target="_blank" rel="noopener noreferrer">View on GitHub</a>
                </p>
                <p class="text-muted mb-0">This is not medical advice.</p>
            </div>
        </div>
    </div>
{% endblock %}
```

- [ ] **Step 5: Run About tests to verify they pass**

Run:

```bash
uv run pytest tests/test_about.py -v
```

Expected: PASS. If `test_github_link` fails because the URL is only on About and layout is not updated yet, the About template already contains the URL so it should pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_about.py templates/about.html app.py
git commit -m "$(cat <<'EOF'
feat: public About page at /

EOF
)"
```

---

### Task 4: Navbar Steps href and GitHub link

**Files:**
- Modify: `tests/test_about.py` (add nav assertions)
- Modify: `templates/layout.html`

- [ ] **Step 1: Add failing navbar tests to `tests/test_about.py`**

```python
class TestNavbar:
    def test_logged_out_nav_has_github(self, client):
        resp = client.get("/")
        assert b"https://github.com/claudia-liauw/health-app" in resp.data
        assert b">GitHub<" in resp.data

    def test_logged_in_nav_steps_goes_to_steps(self, no_fitbit_client):
        resp = no_fitbit_client.get("/")
        assert b'href="/steps"' in resp.data
        assert b">Steps<" in resp.data

    def test_logged_in_nav_has_github(self, no_fitbit_client):
        resp = no_fitbit_client.get("/")
        assert b">GitHub<" in resp.data
```

- [ ] **Step 2: Run navbar tests to verify they fail**

Run:

```bash
uv run pytest tests/test_about.py::TestNavbar -v
```

Expected: FAIL — Steps still `href="/"` and/or no GitHub label in the nav.

- [ ] **Step 3: Update `templates/layout.html`**

Change the Steps item:

```html
                            <li class="nav-item"><a class="nav-link" href="/steps">Steps</a></li>
```

Keep brand `href="/"`.

Add GitHub as the first item in **both** `ms-auto` lists (logged-in and logged-out):

Logged-in (`session["user_id"]` true), right-side list:

```html
                        <ul class="navbar-nav ms-auto">
                            <li class="nav-item"><a class="nav-link" href="https://github.com/claudia-liauw/health-app" target="_blank" rel="noopener noreferrer">GitHub</a></li>
                            <li class="nav-item"><a class="nav-link" href="/profile">Profile</a></li>
                            <li class="nav-item"><a class="nav-link" href="/logout">Log Out</a></li>
                        </ul>
```

Logged-out:

```html
                        <ul class="navbar-nav ms-auto">
                            <li class="nav-item"><a class="nav-link" href="https://github.com/claudia-liauw/health-app" target="_blank" rel="noopener noreferrer">GitHub</a></li>
                            <li class="nav-item"><a class="nav-link" href="/register">Register</a></li>
                            <li class="nav-item"><a class="nav-link" href="/login">Log In</a></li>
                        </ul>
```

- [ ] **Step 4: Run About + navbar tests**

Run:

```bash
uv run pytest tests/test_about.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_about.py templates/layout.html
git commit -m "$(cat <<'EOF'
feat: GitHub nav link and Steps at /steps

EOF
)"
```

---

### Task 5: Register — no Fitbit default and disclaimer

**Files:**
- Modify: `tests/test_login.py` (add `TestRegister` at the end of the file)
- Modify: `templates/register.html`

Backend already sets `has_fitbit = 'fitbit' in request.form`. Do not change `app.py` register logic except the redirect already done in Task 2.

- [ ] **Step 1: Write failing register tests**

Append to `tests/test_login.py`:

```python
class TestRegister:
    def test_fitbit_checkbox_unchecked_by_default(self, client):
        resp = client.get("/register")
        html = resp.data.decode()
        assert 'id="fitbit"' in html
        assert 'type="checkbox" checked' not in html

    def test_disclaimer_text_present(self, client):
        resp = client.get("/register")
        assert b"Untested with other Fitbit devices" in resp.data

    def test_register_without_fitbit_redirects_to_steps(self, client):
        resp = client.post(
            "/register",
            data={
                "username": "newuser",
                "password": "secret",
                "confirmation": "secret",
            },
        )
        assert resp.status_code == 302
        assert "/steps" in resp.headers["Location"]

    def test_login_redirects_to_steps(self, client):
        resp = client.post(
            "/login",
            data={"username": "testuser", "password": "testpass"},
        )
        assert resp.status_code == 302
        assert "/steps" in resp.headers["Location"]
```

- [ ] **Step 2: Run register tests to verify they fail**

Run:

```bash
uv run pytest tests/test_login.py::TestRegister -v
```

Expected: FAIL on `test_fitbit_checkbox_unchecked_by_default` because the checkbox currently has `checked`. `test_disclaimer_text_present` also FAIL. Redirect tests should already PASS if Task 2 is done.

- [ ] **Step 3: Update `templates/register.html`**

Replace the Fitbit checkbox block with:

```html
                    <div class="mb-4">
                        <div class="form-check">
                            <input class="form-check-input" id="fitbit" name="fitbit" type="checkbox">
                            <label class="form-check-label" for="fitbit">I have a Fitbit account</label>
                        </div>
                        <div class="alert alert-warning d-none mt-2 mb-0" id="fitbit-disclaimer" role="alert">
                            Untested with other Fitbit devices
                        </div>
                    </div>
                    <button class="btn btn-primary w-100" type="submit">Create Account</button>
                </form>
                <script>
                (function () {
                    var box = document.getElementById("fitbit");
                    var note = document.getElementById("fitbit-disclaimer");
                    box.addEventListener("change", function () {
                        note.classList.toggle("d-none", !box.checked);
                    });
                })();
                </script>
```

Keep the rest of the form (username, password, confirmation, “Already have an account?”) unchanged. Do not add an extra “I understand” checkbox.

- [ ] **Step 4: Run register tests**

Run:

```bash
uv run pytest tests/test_login.py::TestRegister -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_login.py templates/register.html
git commit -m "$(cat <<'EOF'
feat: default register to no Fitbit with disclaimer

EOF
)"
```

---

### Task 6: Full suite and test docs

**Files:**
- Modify: `tests/README.md` (only the lines that still say `/` is the steps page)

- [ ] **Step 1: Run the full test suite**

Run:

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Update `tests/README.md` route wording**

In `test_login.py` section:

- `test_login_reaches_steps_dashboard`: “lands on `/steps` (steps page)”
- `test_logout_clears_session`: after logout, `GET /steps` redirects to `/login`; `GET /` is public About

Add a short bullet under Test Files (or a new `test_about.py` subsection):

- Logged-out and logged-in `GET /` returns About (200), GitHub URL, and “This is not medical advice.”
- Register: Fitbit checkbox not checked; disclaimer text in HTML; POST without `fitbit` redirects to `/steps`.

- [ ] **Step 3: Re-run tests**

Run:

```bash
uv run pytest -v
```

Expected: PASS (docs-only change).

- [ ] **Step 4: Commit**

```bash
git add tests/README.md
git commit -m "$(cat <<'EOF'
docs: record About home and /steps in test README

EOF
)"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|---|---|
| `/` public About | Task 3 |
| Brand always About | Task 3 + layout brand stays `/` |
| Steps at `/steps` | Tasks 1–2, 4 |
| Login / register / callback → `/steps` | Tasks 2, 5 tests |
| Logout → `/` | Task 2 (unchanged redirect) |
| GitHub in navbar for everyone | Task 4 |
| GitHub on About | Task 3 |
| README-style About copy | Task 3 |
| “This is not medical advice.” | Task 3 |
| Fitbit checkbox default off | Task 5 |
| Disclaimer exact text, show/hide, not blocking | Task 5 |
| Existing dashboard tests retargeted | Task 1 |
| Logout assertion uses `/steps` | Task 1 |
| No OAuth/chat/sleep/heart/schema changes | Out of scope, not tasked |
