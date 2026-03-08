"""
Build a health-data context string from the user's session
to inject into the LLM system prompt.

Handles both demo users (CSV data) and Fitbit-connected users (live API).
"""

import datetime
import numpy as np
import pandas as pd
from sqlalchemy import text


def _get_goals(engine, username: str) -> dict:
    """Fetch step_goal and sleep_goal from the profile table."""
    with engine.connect() as db:
        row = db.execute(
            text("SELECT step_goal, sleep_goal FROM profile WHERE username = :u"),
            {"u": username},
        ).fetchone()
    return {
        "step_goal": row[0] if row else "Not set",
        "sleep_goal": row[1] if row else "Not set",
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _last_week_with_data(df, date_col="Date"):
    """Given a df with a date column, find the last date with data
    and return 7 days ending on that date."""
    if df.empty:
        return df
    df[date_col] = pd.to_datetime(df[date_col])
    last_date = df[date_col].max()
    start = last_date - pd.Timedelta("6 days")
    return df[(df[date_col] >= start) & (df[date_col] <= last_date)]


# ── Demo data (CSV) ─────────────────────────────────────────────────────────

def _demo_steps():
    df = pd.read_csv("data/fitbit_apr/dailySteps_merged.csv")
    df = df.rename(columns={"ActivityDay": "Date", "StepTotal": "Steps"})
    df.Date = pd.to_datetime(df.Date)
    uid = df.Id.unique()[0]
    df = df[df.Id == uid].sort_values("Date")[["Date", "Steps"]]
    df = df[df["Steps"] > 0]
    df = _last_week_with_data(df)
    period = f"{df['Date'].min().date()} to {df['Date'].max().date()}" if not df.empty else "No data"
    return df, period


def _demo_sleep():
    df = pd.read_csv("data/fitbit_apr/sleepDay_merged.csv")
    df = df.rename(columns={"SleepDay": "Date", "TotalMinutesAsleep": "Minutes Asleep"})
    df.Date = pd.to_datetime(df.Date)
    uid = df.Id.unique()[0]
    df = df[df.Id == uid].sort_values("Date")[["Date", "Minutes Asleep"]]
    df = df[df["Minutes Asleep"] > 0]
    df = _last_week_with_data(df)
    period = f"{df['Date'].min().date()} to {df['Date'].max().date()}" if not df.empty else "No data"
    return df, period


def _demo_heart():
    df = pd.read_csv("data/fitbit_apr/heartrate_seconds_merged.csv")
    df = df.rename(columns={"Value": "Heart Rate"})
    df.Time = pd.to_datetime(df.Time)
    uid = df.Id.unique()[0]
    daily = (
        df[df.Id == uid]
        .set_index("Time")["Heart Rate"]
        .resample("D")
        .agg(["mean", "min", "max"])
        .dropna()
        .round(1)
        .reset_index()
    )
    daily.columns = ["Date", "Avg HR", "Min HR", "Max HR"]
    daily = _last_week_with_data(daily)
    period = f"{daily['Date'].min().date()} to {daily['Date'].max().date()}" if not daily.empty else "No data"
    return daily, period


# ── Live Fitbit data ─────────────────────────────────────────────────────────

def _live_steps(fitbit_id, access_token, date, retrieve_data):
    # Fetch 1 year, filter to non-zero, take the last week with data
    j = retrieve_data("steps", fitbit_id, access_token, date, "1y")
    df = pd.DataFrame(j.get("activities-steps", []))
    if df.empty:
        return pd.DataFrame(columns=["Date", "Steps"]), "No data"
    df = df.rename(columns={"dateTime": "Date", "value": "Steps"})
    df["Steps"] = pd.to_numeric(df["Steps"])
    df = df[df["Steps"] > 0]
    df = _last_week_with_data(df)
    period = f"{df['Date'].min().date()} to {df['Date'].max().date()}" if not df.empty else "No data"
    return df[["Date", "Steps"]], period


def _live_sleep(fitbit_id, access_token, date, retrieve_data):
    # Range-based: fetch 1 year of sleep in one call
    end = pd.Timestamp(date)
    start = end - pd.Timedelta("365 days")
    j = retrieve_data("sleep", fitbit_id, access_token, start.date(),
                       period=str(end.date()), version=1.2)
    records = j.get("sleep", [])
    if not records:
        return pd.DataFrame(columns=["Date", "Minutes Asleep"]), "No data"
    rows = []
    for r in records:
        rows.append({
            "Date": r.get("dateOfSleep", r.get("startTime", "")[:10]),
            "Minutes Asleep": r.get("minutesAsleep", 0),
        })
    df = pd.DataFrame(rows)
    df = df[df["Minutes Asleep"] > 0]
    # Aggregate by date in case of multiple sleep records per day
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.groupby("Date", as_index=False)["Minutes Asleep"].sum()
    df = _last_week_with_data(df)
    period = f"{df['Date'].min().date()} to {df['Date'].max().date()}" if not df.empty else "No data"
    return df, period


def _live_heart(fitbit_id, access_token, date, retrieve_data):
    # Fetch 1 year, keep only days with resting HR, take last week
    j = retrieve_data("heart", fitbit_id, access_token, date, period="1y")
    rows = []
    for day in j.get("activities-heart", []):
        resting = day.get("value", {}).get("restingHeartRate", None)
        if resting:
            rows.append({"Date": day["dateTime"], "Resting HR": resting})
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Date", "Resting HR"])
    df = _last_week_with_data(df)
    period = f"{df['Date'].min().date()} to {df['Date'].max().date()}" if not df.empty else "No data"
    return df, period


# ── Public API ───────────────────────────────────────────────────────────────

def build_health_context(session, engine, retrieve_data_fn=None) -> str:
    """
    Build a concise text summary of the user's health data and goals.

    Returns a string suitable for inserting into an LLM system prompt.
    """
    username = session.get("user_id", "User")
    fitbit_id = session.get("fitbit_id", "no_fitbit")
    access_token = session.get("access_token", "")
    today = datetime.date.today()
    is_demo = fitbit_id == "no_fitbit"

    goals = _get_goals(engine, username)

    parts = [
        f"## User: {username}",
        f"**Today:** {today}",
        f"**Step goal:** {goals['step_goal']}",
        f"**Sleep goal:** {goals['sleep_goal']}"
        + (" hours" if goals["sleep_goal"] not in ("Not set", "Create one") else ""),
    ]

    # Steps
    try:
        if is_demo:
            df, period = _demo_steps()
        else:
            df, period = _live_steps(fitbit_id, access_token, today, retrieve_data_fn)
        parts.append(f"\n### Steps (data from {period})")
        parts.append(df.to_string(index=False))
    except Exception:
        parts.append("\n### Steps\nData unavailable.")

    # Sleep
    try:
        if is_demo:
            df, period = _demo_sleep()
        else:
            df, period = _live_sleep(fitbit_id, access_token, today, retrieve_data_fn)
        parts.append(f"\n### Sleep (data from {period})")
        parts.append(df.to_string(index=False))
    except Exception:
        parts.append("\n### Sleep\nData unavailable.")

    # Heart rate
    try:
        if is_demo:
            df, period = _demo_heart()
        else:
            df, period = _live_heart(fitbit_id, access_token, today, retrieve_data_fn)
        parts.append(f"\n### Heart Rate (data from {period})")
        parts.append(df.to_string(index=False))
    except Exception:
        parts.append("\n### Heart Rate\nData unavailable.")

    return "\n".join(parts)
