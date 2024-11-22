from flask import Flask, request, render_template, session, redirect, flash
from flask_session import Session
import numpy as np
import pandas as pd
import plotly.express as px
from src.utils import *
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
import urllib.parse
import datetime

app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

DB_PATH = "data/users.db"
TODAY_DATE = datetime.date.today()

@app.route("/")
@login_required
@auth_required
def steps():
    # get user ID and access token
    fitbit_id = session['fitbit_id']
    access_token = session['access_token']

    # retrieve today's data via fitbit API
    today_json = retrieve_data('steps', fitbit_id, access_token, TODAY_DATE, '1d')
    try: 
        total_steps = today_json['activities-steps'][0]['value']
    except KeyError:
        return redirect('/authenticate')

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

    # display steps by hour on chosen date
    date = request.args.get('date', TODAY_DATE)
    day_json = retrieve_data('steps', fitbit_id, access_token, date, '1d')
    day_steps = pd.DataFrame(day_json['activities-steps-intraday']['dataset'])
    day_steps.time = pd.to_datetime(str(date) + ' ' + day_steps.time)
    hourly_steps = day_steps.groupby(pd.Grouper(key='time', freq='h')).sum().reset_index()
    hourly_steps = hourly_steps.rename(columns={'time': 'Hour', 'value': 'Steps'})
    hourly_fig = px.bar(hourly_steps, x='Hour', y='Steps')

    # retrieve week data via fitbit API
    week_json = retrieve_data('steps', fitbit_id, access_token, date, '7d')

    # display week's steps
    week_steps = pd.DataFrame(week_json['activities-steps'])
    week_steps['Steps'] = pd.to_numeric(week_steps.value)
    week_steps = week_steps.rename(columns={'dateTime': 'Date'})
    daily_fig = px.bar(week_steps, x='Date', y='Steps')
    
    return render_template("steps.html",
                           steps=total_steps,
                           target=target,
                           date=date,
                           hourly_fig=hourly_fig.to_html(full_html=False),
                           daily_fig=daily_fig.to_html(full_html=False))

@app.route("/sleep")
@login_required
@auth_required
def sleep():
    # get user ID and access token
    fitbit_id = session['fitbit_id']
    access_token = session['access_token']

    # retrieve today's data via fitbit API
    today_json = retrieve_data('sleep', fitbit_id, access_token, TODAY_DATE, version=1.2)
    try: 
        hours_slept = np.round(today_json['summary']['totalMinutesAsleep'] / 60, 2)
    except KeyError:
        return redirect('/authenticate')
    
    # check if target is met
    with sqlite3.connect(DB_PATH) as db:
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

    # retrieve week data via fitbit API and display
    date = request.args.get('date', TODAY_DATE)
    date = pd.Timestamp(date) 
    start_date = date - pd.Timedelta('7 days')
    week_sleep = []
    for day in pd.date_range(start_date, date):
        day_json = retrieve_data('sleep', fitbit_id, access_token, day.date(), version=1.2)
        week_sleep.append({'Date': day.date(), 'Total Minutes Asleep': day_json['summary']['totalMinutesAsleep']})
    fig = px.bar(week_sleep, x='Date', y='Total Minutes Asleep')

    return render_template("sleep.html", 
                           hours_slept=hours_slept,
                           target=target,
                           date=date,
                           fig=fig.to_html(full_html=False))

@app.route("/heart-rate", methods=["GET", "POST"])
@login_required
@auth_required
def heart_rate():
    # get user ID and access token
    fitbit_id = session['fitbit_id']
    access_token = session['access_token']
    
    # retrieve data on chosen date via fitbit API
    date = request.args.get('date', TODAY_DATE)
    day_json = retrieve_data('heart', fitbit_id, access_token, date, period='1d')
    try: 
        day_heart = pd.DataFrame(day_json['activities-heart-intraday']['dataset'])
    except KeyError:
        return redirect('/authenticate')
    
    # display heart rate on chosen date
    # if no data
    if len(day_heart) == 0:
        day_heart['time'] = date
        day_heart['value'] = 0
    day_heart.time = pd.to_datetime(str(date) + ' ' + day_heart.time)
    day_heart = day_heart.rename(columns={'time': 'Time', 'value': 'Heart Rate'})
    day_fig = px.line(day_heart, x='Time', y='Heart Rate', markers=True)

    # retrieve week data via fitbit API and display
    week_json = retrieve_data('heart', fitbit_id, access_token, date, period='7d')
    week_heart = []
    for day in range(7):
        date = week_json['activities-heart'][day]['dateTime']
        try:
            resting_hr = week_json['activities-heart'][day]['value']['restingHeartRate']
        except KeyError:
            resting_hr = 0
        week_heart.append({'Date': date, 'Resting HR': resting_hr})
    week_fig = px.bar(week_heart, x='Date', y='Resting HR')
    
    if request.method == "POST":
        from momentfm import MOMENTPipeline
        model = MOMENTPipeline.from_pretrained(
            "AutonLab/MOMENT-1-large", 
            model_kwargs={"task_name": "reconstruction"},  # For anomaly detection, we will load MOMENT in `reconstruction` mode
            local_files_only=True,  # Whether or not to only look at local files (i.e., do not try to download the model).
        )
        anomalies = get_anomalies(day_heart, model, anomaly_thresh=5).reset_index(drop=True)
        return render_template("heart.html", tables=[anomalies.to_html(classes='data', header='true')],
                               date=date,
                               day_fig=day_fig.to_html(full_html=False),
                               week_fig=week_fig.to_html(full_html=False))
    
    else:
        return render_template("heart.html", tables=None, 
                               date=date,
                               day_fig=day_fig.to_html(full_html=False),
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
        with sqlite3.connect(DB_PATH) as db:
            try:
                db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, hash))
                db.execute("""INSERT INTO profile (username, step_goal, sleep_goal) 
                           VALUES (?, 'Create one', 'Create one')""", (username,))
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
        with sqlite3.connect(DB_PATH) as db:
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

        # Redirect user to authenticate
        return redirect("/authenticate")

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
    with sqlite3.connect(DB_PATH) as db:
        goals = db.execute(
            "SELECT * FROM profile WHERE username = ?", (username,)
        ).fetchall()

        ori_step_goal = goals[0][1]
        ori_sleep_goal = goals[0][2]
    
    if request.method == "POST":
        # if empty, set to existing data
        step_goal = request.form['step'] or ori_step_goal
        sleep_goal = request.form['sleep'] or ori_sleep_goal

        with sqlite3.connect(DB_PATH) as db:
            db.execute("UPDATE profile SET step_goal = ?, sleep_goal = ? WHERE username = ?", 
                       (step_goal, sleep_goal, username))
            db.commit()
        return redirect("/profile")
    else:
        return render_template("profile.html", 
                               username=username, 
                               step_goal=ori_step_goal, 
                               sleep_goal=ori_sleep_goal)

CLIENT_ID = '23PQH4'
REDIRECT_URL = 'http://localhost:5000/callback'

@app.route("/authenticate")
@login_required
def authenticate():
    session['auth_params'] = AppAuthenticator()()
    query_params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'scope': 'activity heartrate settings sleep',
        'code_challenge': session['auth_params']['code_challenge'],
        'code_challenge_method': 'S256',
        'state': session['auth_params']['state'],
        'redirect_uri': REDIRECT_URL,
    }
    url = f"https://www.fitbit.com/oauth2/authorize?{urllib.parse.urlencode(query_params)}"
    return redirect(url)

@app.route("/callback")
@login_required
def callback():
    code = request.args['code']
    state = request.args['state']
    if not code:
        return 'Error: no authorisation code', 400
    if state != session['auth_params']['state']:
        return 'Error: does not match original state', 400

    print('callback')
    response = requests.post('https://api.fitbit.com/oauth2/token',
                             headers={'Authorization': '',
                                      'Content-Type': 'application/x-www-form-urlencoded'},
                             data={'client_id': CLIENT_ID,
                                   'grant_type': 'authorization_code',
                                   'redirect_uri': REDIRECT_URL,
                                   'code': code,
                                   'code_verifier': session['auth_params']['code_verifier']})
    session['access_token'] = response.json()['access_token']
    session['fitbit_id'] = response.json()['user_id']
    return redirect("/")