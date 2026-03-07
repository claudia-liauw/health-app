# Test Suite Documentation

## Overview

This test suite verifies the core user-facing features of the Health is Wealth app using **pytest** and Flask's built-in test client. All tests run against the real SQLite database (cleaned and re-seeded per test) with mocked Fitbit API calls — no network access or real Fitbit account required.

**Run tests:**

```bash
pytest -v
```

---

## Fixtures (`tests/conftest.py`)

| Fixture | Description |
|---|---|
| `app` | Flask app with `TESTING=True`, temp filesystem session dir. Cleans the DB and seeds two test users before every test. |
| `client` | Unauthenticated `app.test_client()`. |
| `no_fitbit_client` | Logged-in client for **testuser** (no Fitbit). Session has `fitbit_id='no_fitbit'`. Sees demo CSV data. |
| `fitbit_client` | Logged-in client for **fitbituser** (has Fitbit). OAuth is bypassed — fake `fitbit_id` and `access_token` are injected into the session. |
| `mock_fitbit_api` | Patches `requests.get` in `src.utils` to return canned JSON. Required by any test that hits a dashboard route as a Fitbit user. |

### Seeded test users

| Username | Password | has_fitbit | Default goals |
|---|---|---|---|
| `testuser` | `testpass` | `False` | `'Create one'` / `'Create one'` |
| `fitbituser` | `fitbitpass` | `True` | `'Create one'` / `'Create one'` |

### Canned Fitbit API data (used by `mock_fitbit_api`)

| Endpoint | Key values |
|---|---|
| Steps (today) | 8 500 total steps |
| Steps (intraday) | 350 steps/hour × 24 hours |
| Steps (7-day) | Jan 9 → 9 000, Jan 10 → 10 000, … Jan 15 → 15 000 |
| Sleep | 420 min asleep (7 h), 480 min in bed |
| Heart rate (intraday) | Resting 62 bpm, hourly values 70–93 bpm |
| Heart rate (7-day) | Resting HR 69–75 bpm |

---

## Test Files

### `test_login.py` — Login Flows

Verifies that both user types can log in and reach their respective dashboards.

| Test | What it checks |
|---|---|
| **TestNoFitbitLogin** | |
| `test_login_reaches_steps_dashboard` | After login, no-Fitbit user lands on `/` (steps page) with HTTP 200. |
| `test_warning_shown` | The "WARNING: You are not connected to Fitbit…" banner is visible. |
| `test_demo_steps_shown` | Demo total steps (13 162) appear on the page. |
| `test_sleep_page_loads` | `/sleep` returns 200 with "Hours slept". |
| `test_heart_page_loads` | `/heart-rate` returns 200 with heart rate content. |
| **TestFitbitLogin** | |
| `test_login_redirects_to_authenticate` | Fitbit user without completed OAuth is redirected to `/authenticate`. |
| `test_dashboard_loads_after_oauth` | After OAuth (simulated), Fitbit user sees the steps page without the no-Fitbit warning. |
| `test_sleep_loads_after_oauth` | Fitbit user can access `/sleep`. |
| `test_heart_loads_after_oauth` | Fitbit user can access `/heart-rate`. |
| **TestLoginValidation** | |
| `test_wrong_password` | Wrong password → "Invalid username or password" error. |
| `test_nonexistent_user` | Non-existent username → same generic error. |
| `test_empty_username` | Blank username → "Must provide username". |
| `test_empty_password` | Blank password → "Must provide password". |
| `test_logout_clears_session` | `GET /logout` clears session; next request redirects to `/login`. |

---

### `test_date_picker.py` — Date Picker

Verifies the `?date=YYYY-MM-DD` query parameter on all three dashboards.

**Validation rules** (Fitbit users only):
- Missing → defaults to today.
- Invalid format → falls back to today.
- Future date → clamped to today.
- Valid past date → used as-is.

No-Fitbit users always see hardcoded demo dates regardless of the parameter.

| Test | What it checks |
|---|---|
| **TestStepsDatePicker** | |
| `test_default_date_loads` | Steps page loads with no `?date` param. |
| `test_valid_past_date` | `?date=2025-01-15` → page loads, date appears in response. |
| `test_invalid_date_does_not_crash` | `?date=not-a-date` → page still loads (falls back to today). |
| `test_future_date_clamped` | `?date=2099-01-01` → that date does NOT appear in response. |
| `test_no_fitbit_date_picker_ignored` | No-Fitbit user with `?date=2025-01-15` still sees demo date `2016-04-12`. |
| **TestSleepDatePicker** | |
| `test_valid_past_date` | `/sleep?date=2025-01-15` → loads, date in response. |
| `test_invalid_date_does_not_crash` | `/sleep?date=bad` → page loads. |
| `test_no_fitbit_shows_demo_date` | No-Fitbit user always sees `2016-04-17`. |
| **TestHeartDatePicker** | |
| `test_valid_past_date` | `/heart-rate?date=2025-01-15` → loads. |
| `test_date_stored_in_session` | After `?date=2025-01-15`, revisiting without `?date` still shows `2025-01-15`. |
| `test_invalid_date_does_not_crash` | `/heart-rate?date=xyz` → page loads. |
| `test_no_fitbit_shows_demo_date` | No-Fitbit user always sees `2016-04-12`. |

---

### `test_goals.py` — Goal Setting & Plot Display

Verifies that goals can be created/updated via `/profile` and that they appear correctly on the steps and sleep dashboards.

**How goals work:**
- Default value is `'Create one'` (shows a link to `/profile`).
- Valid non-negative integers (steps) or floats (sleep) are accepted.
- Invalid values (negative, non-numeric) reset to `'Create one'`.
- Blank submission preserves the existing value.

**Demo data thresholds** (no-Fitbit user):
- Steps: **13 162** → goal below this = "Target reached!", above = "Target not yet reached."
- Sleep: **11.67 h** → goal below this = "Sleep target reached!", above = "Sleep target not reached."

| Test | What it checks |
|---|---|
| **TestProfileGoals** | |
| `test_default_goals_are_create_one` | New user sees `'Create one'` for both goals. |
| `test_set_step_goal` | POST `step=10000` → profile shows `10000`. |
| `test_set_sleep_goal` | POST `sleep=8` → profile shows `8`. |
| `test_negative_step_goal_resets` | POST `step=-5` → resets to `'Create one'`. |
| `test_non_numeric_step_goal_resets` | POST `step=abc` → resets to `'Create one'`. |
| `test_blank_goal_preserves_original` | Set 10000, then submit blank → still 10000. |
| **TestGoalOnStepsPlot** | |
| `test_no_goal_shows_create_link` | Default goal → "No goal set" with link to `/profile`. |
| `test_step_goal_displayed_on_steps_page` | Goal 10000 → `/10000` appears next to total. |
| `test_target_reached_when_exceeded` | Goal 5000 < 13162 → "Target reached!". |
| `test_target_not_reached` | Goal 20000 > 13162 → "Target not yet reached." |
| **TestGoalOnSleepPlot** | |
| `test_no_goal_shows_create_link` | Default → "No goal set" with link. |
| `test_sleep_goal_displayed_on_sleep_page` | Goal 8 → `/8.0h` appears. |
| `test_sleep_target_reached` | Goal 8 < 11.67 → "Sleep target reached!". |
| `test_sleep_target_not_reached` | Goal 15 > 11.67 → "Sleep target not reached." |
| **TestGoalOnFitbitPlot** | Canned API: 8 500 steps, 420 min (7 h) sleep. |
| `test_step_goal_with_fitbit` | Goal 5000 < 8500 → `/5000` shown, "Target reached!". |
| `test_sleep_goal_with_fitbit` | Goal 6 < 7 → `/6.0h` shown, "Sleep target reached!". |
