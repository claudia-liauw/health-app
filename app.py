from flask import Flask, request, render_template, session, redirect
from flask_session import Session
import pandas as pd
import plotly.express as px
from src.utils import get_anomalies
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3

app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

db_path = "data/users.db"

@app.route("/")
def steps():
    steps = 2000

    # check if target is met
    with sqlite3.connect("data/users.db") as db:
        step_goal = db.execute(
            "SELECT step_goal FROM goals WHERE username = ?", (session['user_id'],)
        ).fetchall()
    step_goal = step_goal[0][0]
    if step_goal == 'Create one':
        target = '<p>No goal set. <a href="/profile">Create one!</a></p>'
    elif steps >= int(step_goal):
        target = '<p>Target reached!</p>'
    else:
        target = '<p>Target not yet reached.</p>'

    hourly_steps = pd.read_csv('data/fitbit_apr/hourlySteps_merged.csv')
    hourly_steps = hourly_steps.rename(columns={'ActivityHour': 'Hour', 'StepTotal': 'Steps'})
    hourly_steps.Hour = pd.to_datetime(hourly_steps.Hour)
    hourly = hourly_steps.loc[(hourly_steps.Id == hourly_steps.Id.unique()[0]) & (hourly_steps.Hour < '2016-04-13')]
    hourly_fig = px.bar(hourly, x='Hour', y='Steps')

    daily_steps = pd.read_csv('data/fitbit_apr/dailySteps_merged.csv')
    daily_steps = daily_steps.rename(columns={'ActivityDay': 'Date', 'StepTotal': 'Steps'})
    daily_steps.Date = pd.to_datetime(daily_steps.Date)
    daily = daily_steps.loc[(daily_steps.Id == daily_steps.Id.unique()[0]) & (daily_steps.Date < '2016-04-19')]
    daily_fig = px.bar(daily, x='Date', y='Steps')
    return render_template("steps.html",
                           steps=steps,
                           target=target,
                           hourly_fig=hourly_fig.to_html(full_html=False),
                           daily_fig=daily_fig.to_html(full_html=False))

@app.route("/sleep")
def sleep():
    daily_sleep = pd.read_csv('data/fitbit_apr/sleepDay_merged.csv')
    daily_sleep = daily_sleep.rename(columns={'SleepDay': 'Date', 'TotalMinutesAsleep': 'Total Minutes Asleep'})
    daily_sleep.Date = pd.to_datetime(daily_sleep.Date)
    sleep = daily_sleep.loc[(daily_sleep.Id == daily_sleep.Id.unique()[0]) & (daily_sleep.Date < '2016-04-19')]
    fig = px.bar(sleep, x='Date', y='Total Minutes Asleep')
    return render_template("sleep.html", fig=fig.to_html(full_html=False))

@app.route("/heart-rate", methods=["GET", "POST"])
def heart_rate():
    if request.method == "POST":
        data = pd.read_csv('data/fitbit_apr/heartrate_seconds_merged.csv')
        data.Time = pd.to_datetime(data.Time)
        hr = data.loc[(data.Id == data.Id.unique()[0]) & (data.Time < '2016-04-20')]

        from momentfm import MOMENTPipeline
        model = MOMENTPipeline.from_pretrained(
            "AutonLab/MOMENT-1-large", 
            model_kwargs={"task_name": "reconstruction"},  # For anomaly detection, we will load MOMENT in `reconstruction` mode
            local_files_only=True,  # Whether or not to only look at local files (i.e., do not try to download the model).
        )
        anomalies = get_anomalies(hr, model).reset_index(drop=True)
        return render_template("heart.html", tables=[anomalies.to_html(classes='data', header='true')])
    else:
        return render_template("heart.html", tables=None)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        confirmation = request.form['confirmation']

        # Ensure username is submitted
        if not username:
            return render_template("register.html", invalid="Must provide username!")

        # Ensure password is submitted
        elif not password:
            return render_template("register.html", invalid="Must provide password!")

        # Ensure passwords match
        elif password != confirmation:
            return render_template("register.html", invalid="Passwords do not match!")

        hash = generate_password_hash(password)
        with sqlite3.connect(db_path) as db:
            try:
                db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, hash))
                db.execute("INSERT INTO goals (username, step_goal, sleep_goal) VALUES (?, 'Create one', 'Create one')", (username,))
                db.commit()
                return redirect("/login")
            # If username already exists
            except:
                return render_template("register.html", invalid="Username already exists!")

    else:
        return render_template("register.html")
    
@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return render_template("login.html", invalid="Must provide username!")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return render_template("login.html", invalid="Must provide password!")

        # Query database for username
        with sqlite3.connect("data/users.db") as db:
            rows = db.execute(
                "SELECT * FROM users WHERE username = ?", (request.form.get("username"),)
            ).fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0][1], request.form.get("password")
        ):
            return render_template("login.html", invalid='Invalid username or password!')

        # Remember which user has logged in
        session["user_id"] = rows[0][0]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")
    
@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/login")

@app.route("/profile", methods=["GET", "POST"])
def profile():
    username = session['user_id']
    with sqlite3.connect("data/users.db") as db:
        rows = db.execute(
            "SELECT * FROM goals WHERE username = ?", (username,)
        ).fetchall()

        ori_step_goal = rows[0][1]
        ori_sleep_goal = rows[0][2]
    
    if request.method == "POST":
        step_goal = request.form['step']
        # if empty, set to existing data
        step_goal = step_goal if step_goal else ori_step_goal
        sleep_goal = request.form['sleep']
        sleep_goal = sleep_goal if sleep_goal else ori_sleep_goal

        with sqlite3.connect(db_path) as db:
            db.execute("UPDATE goals SET step_goal = ?, sleep_goal = ? WHERE username = ?", 
                       (step_goal, sleep_goal, username))
            db.commit()
        return redirect("/profile")
    else:
        return render_template("profile.html", username=username, step_goal=ori_step_goal, sleep_goal=ori_sleep_goal)