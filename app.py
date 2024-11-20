from flask import Flask, request, render_template, session, redirect, flash
from flask_session import Session
import numpy as np
import pandas as pd
import plotly.express as px
from src.utils import get_anomalies, login_required, retrieve_data, get_user_id
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3

app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

db_path = "data/users.db"

with open('data/fitbit_access_token.txt', 'r') as f:
    FITBIT_ACCESS_TOKEN = f.read()

@app.route("/")
@login_required
def steps():
    # get user ID
    user_id = get_user_id(db_path, session['user_id'])
    if user_id == 'Provide user ID':
        flash('Provide user ID')
        return redirect('/profile')

    # retrieve today's data via fitbit API
    date = '2024-10-10'
    today_json = retrieve_data('steps', user_id, FITBIT_ACCESS_TOKEN, date, '1d')
    try: 
        total_steps = today_json['activities-steps'][0]['value']
    except KeyError:
        flash('Invalid user ID')
        return redirect('/profile')

    # check if target is met
    with sqlite3.connect("data/users.db") as db:
        step_goal = db.execute(
            "SELECT step_goal FROM profile WHERE username = ?", (session['user_id'],)
        ).fetchall()
    step_goal = step_goal[0][0]
    if step_goal == 'Create one':
        target = '<p>No goal set. <a href="/profile">Create one!</a></p>'
    elif int(total_steps) >= int(step_goal):
        target = '<p>Target reached!</p>'
    else:
        target = '<p>Target not yet reached.</p>'

    # display today's steps by hour
    today_steps = pd.DataFrame(today_json['activities-steps-intraday']['dataset'])
    today_steps.time = pd.to_datetime(date + ' ' + today_steps.time)
    hourly_steps = today_steps.groupby(pd.Grouper(key='time', freq='h')).sum().reset_index()
    hourly_steps = hourly_steps.rename(columns={'time': 'Hour', 'value': 'Steps'})
    hourly_fig = px.bar(hourly_steps, x='Hour', y='Steps')

    # retrieve week data via fitbit API
    week_json = retrieve_data('steps', user_id, FITBIT_ACCESS_TOKEN, date, '7d')

    # display week's steps
    week_steps = pd.DataFrame(week_json['activities-steps'])
    week_steps['Steps'] = pd.to_numeric(week_steps.value)
    week_steps = week_steps.rename(columns={'dateTime': 'Date'})
    daily_fig = px.bar(week_steps, x='Date', y='Steps')
    
    return render_template("steps.html",
                           steps=total_steps,
                           target=target,
                           hourly_fig=hourly_fig.to_html(full_html=False),
                           daily_fig=daily_fig.to_html(full_html=False))

@app.route("/sleep")
@login_required
def sleep():
    # get user ID
    user_id = get_user_id(db_path, session['user_id'])
    if user_id == 'Provide user ID':
        flash('Provide user ID')
        return redirect('/profile')

    # retrieve today's data via fitbit API
    date = '2024-10-17'
    today_json = retrieve_data('sleep', user_id, FITBIT_ACCESS_TOKEN, date, version=1.2)
    try: 
        hours_slept = np.round(today_json['summary']['totalMinutesAsleep'] / 60, 2)
    except KeyError:
        flash('Invalid user ID')
        return redirect('/profile')
    
    # check if target is met
    with sqlite3.connect(db_path) as db:
        sleep_goal = db.execute(
            "SELECT sleep_goal FROM profile WHERE username = ?", (session['user_id'],)
        ).fetchall()
    sleep_goal = sleep_goal[0][0]
    if sleep_goal == 'Create one':
        target = '<p>No goal set. <a href="/profile">Create one!</a></p>'
    elif hours_slept >= float(sleep_goal):
        target = '<p>Sleep target reached!</p>'
    else:
        target = '<p>Sleep target not reached.</p>'

    # retrieve week data via fitbit API
    date = pd.Timestamp(date) 
    start_date = date - pd.Timedelta('7 days')
    week_sleep = []
    for day in pd.date_range(start_date, date):
        day_json = retrieve_data('sleep', user_id, FITBIT_ACCESS_TOKEN, day.date(), version=1.2)
        week_sleep.append({'Date': day.date(), 'Total Minutes Asleep': day_json['summary']['totalMinutesAsleep']})
    fig = px.bar(week_sleep, x='Date', y='Total Minutes Asleep')

    return render_template("sleep.html", 
                           hours_slept=hours_slept,
                           target=target,
                           fig=fig.to_html(full_html=False))

@app.route("/heart-rate", methods=["GET", "POST"])
@login_required
def heart_rate():
    # get user ID
    user_id = get_user_id(db_path, session['user_id'])
    if user_id == 'Provide user ID':
        flash('Provide user ID')
        return redirect('/profile')
    
    # retrieve today's data via fitbit API
    date = '2024-10-10'
    today_json = retrieve_data('heart', user_id, FITBIT_ACCESS_TOKEN, date, period='1d')
    try: 
        today_heart = pd.DataFrame(today_json['activities-heart-intraday']['dataset'])
    except KeyError:
        flash('Invalid user ID')
        return redirect('/profile')
    
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
        # display today's heart rate
        today_heart.time = pd.to_datetime(date + ' ' + today_heart.time)
        today_heart = today_heart.rename(columns={'time': 'Time', 'value': 'Heart Rate'})
        today_fig = px.line(today_heart, x='Time', y='Heart Rate', markers=True)

        # retrieve week data via fitbit API
        week_json = retrieve_data('heart', user_id, FITBIT_ACCESS_TOKEN, date, period='7d')
        week_heart = []
        for day in range(7):
            date = week_json['activities-heart'][day]['dateTime']
            try:
                resting_hr = week_json['activities-heart'][day]['value']['restingHeartRate']
            except KeyError:
                resting_hr = 0
            week_heart.append({'Date': date, 'Resting HR': resting_hr})
        week_fig = px.bar(week_heart, x='Date', y='Resting HR')
        
        return render_template("heart.html", tables=None, 
                               today_fig=today_fig.to_html(full_html=False),
                               week_fig=week_fig.to_html(full_html=False))

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
                db.execute("""INSERT INTO profile (username, step_goal, sleep_goal, user_id) 
                           VALUES (?, 'Create one', 'Create one', 'Provide user ID')""", (username,))
                db.commit()
                return redirect("/")
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
        with sqlite3.connect(db_path) as db:
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
    return redirect("/")

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    username = session['user_id']
    with sqlite3.connect(db_path) as db:
        goals = db.execute(
            "SELECT * FROM profile WHERE username = ?", (username,)
        ).fetchall()

        ori_step_goal = goals[0][1]
        ori_sleep_goal = goals[0][2]
        ori_user_id = goals[0][3]
    
    if request.method == "POST":
        step_goal = request.form['step']
        sleep_goal = request.form['sleep']
        user_id = request.form['user_id']

        # if empty, set to existing data
        step_goal = step_goal if step_goal else ori_step_goal
        sleep_goal = sleep_goal if sleep_goal else ori_sleep_goal
        user_id = user_id if user_id else ori_user_id

        with sqlite3.connect(db_path) as db:
            db.execute("UPDATE profile SET step_goal = ?, sleep_goal = ?, user_id = ? WHERE username = ?", 
                       (step_goal, sleep_goal, user_id, username))
            db.commit()
        return redirect("/profile")
    else:
        return render_template("profile.html", 
                               username=username, 
                               step_goal=ori_step_goal, 
                               sleep_goal=ori_sleep_goal, 
                               user_id=ori_user_id)