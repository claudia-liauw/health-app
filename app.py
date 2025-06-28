from flask import Flask, request, render_template, session, redirect, flash
from flask_session import Session
import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

DB_PATH = "/tmp/users.db"
TODAY_DATE = datetime.date.today()

# create database if it doesn't exist
if not os.path.exists(DB_PATH):
    with sqlite3.connect(DB_PATH) as con:
        con.execute('''CREATE TABLE users(
                    username NOT NULL UNIQUE, 
                    hash NOT NULL)''')
        con.execute('''CREATE TABLE profile(
                    username NOT NULL UNIQUE, 
                    step_goal NOT NULL,
                    sleep_goal NOT NULL,
                    FOREIGN KEY(username) REFERENCES users(username))''')

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
    with sqlite3.connect(DB_PATH) as db:
        step_goal = db.execute(
            "SELECT step_goal FROM profile WHERE username = ?", (session['user_id'],)
        ).fetchall()
    step_goal = step_goal[0][0]
    if step_goal == 'Create one':
        target = '<p>No goal set. <a href="/profile">Create one!</a></p>'
        step_goal_fmt = ''
    else:
        step_goal_fmt = '/' + str(step_goal)
        step_goal = int(step_goal)
        if int(total_steps) >= step_goal:
            target = '<p>Target reached!</p>'
        else:
            target = '<p>Target not yet reached.</p>'

    # retrieve chosen date data via fitbit API
    date = request.args.get('date', TODAY_DATE)
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
    except: # if date does not match format
        date = TODAY_DATE
    if pd.Timestamp(date).date() > TODAY_DATE: # if date in the future
        date = TODAY_DATE
    day_json = retrieve_data('steps', fitbit_id, access_token, date, '1d')

    # display steps by hour
    day_steps = pd.DataFrame(day_json['activities-steps-intraday']['dataset'])
    day_steps.time = pd.to_datetime(str(date) + ' ' + day_steps.time)
    hourly_steps = day_steps.groupby(pd.Grouper(key='time', freq='h')).sum().reset_index()
    hourly_steps = hourly_steps.rename(columns={'time': 'Hour', 'value': 'Steps'})
    hourly_fig = px.bar(hourly_steps, x='Hour', y='Steps')

    # retrieve week data via fitbit API
    week_json = retrieve_data('steps', fitbit_id, access_token, date, '7d')

    # display week's steps and whether target has been reached
    week_steps = pd.DataFrame(week_json['activities-steps'])
    week_steps['Steps'] = pd.to_numeric(week_steps.value)
    week_steps = week_steps.rename(columns={'dateTime': 'Date'})
    if step_goal == 'Create one':
        daily_fig = px.bar(week_steps, x='Date', y='Steps')
    else:
        week_steps['Target Reached'] = week_steps.Steps > step_goal
        daily_fig = px.bar(week_steps, x='Date', y='Steps', color='Target Reached', 
                    color_discrete_map={True: px.colors.qualitative.Plotly[2], 
                                        False: px.colors.qualitative.Plotly[1]})
        daily_fig.add_hline(y=step_goal, line_dash="dash")
        daily_fig.update_layout(showlegend=False)
    
    return render_template("steps.html",
                           steps=total_steps,
                           step_goal=step_goal_fmt,
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
        sleep_goal_fmt = ''
    else:
        sleep_goal_fmt = '/' + str(sleep_goal) + 'h'
        sleep_goal = float(sleep_goal)
        if hours_slept >= sleep_goal:
            target = '<p>Sleep target reached!</p>'
        else:
            target = '<p>Sleep target not reached.</p>'

    # retrieve week data via fitbit API
    date = request.args.get('date', TODAY_DATE)
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
        date = pd.Timestamp(date)
    except: # if date does not match format
        date = pd.Timestamp(TODAY_DATE)
    if date.date() > TODAY_DATE: # if in the future
        date = pd.Timestamp(TODAY_DATE)
    start_date = date - pd.Timedelta('7 days')
    week_sleep = []
    for day in pd.date_range(start_date, date):
        day_json = retrieve_data('sleep', fitbit_id, access_token, day.date(), version=1.2)
        week_sleep.append({'Date': day.date(), 'Total Minutes Asleep': day_json['summary']['totalMinutesAsleep']})
    
    # display week sleep and whether target has been reached
    if sleep_goal == 'Create one':
        fig = px.bar(week_sleep, x='Date', y='Total Minutes Asleep')
    else:
        week_sleep = pd.DataFrame(week_sleep)
        week_sleep['Target Reached'] = week_sleep['Total Minutes Asleep'] > (sleep_goal * 60)
        fig = px.bar(week_sleep, x='Date', y='Total Minutes Asleep', color='Target Reached', 
                     color_discrete_map={True: px.colors.qualitative.Plotly[2], 
                                         False: px.colors.qualitative.Plotly[1]})
        fig.add_hline(y=sleep_goal*60, line_dash="dash")
        fig.update_layout(showlegend=False)

    return render_template("sleep.html", 
                           hours_slept=hours_slept,
                           sleep_goal=sleep_goal_fmt,
                           target=target,
                           date=str(date.date()),
                           fig=fig.to_html(full_html=False))

@app.route("/heart-rate", methods=["GET", "POST"])
@login_required
@auth_required
def heart_rate():
    # get user ID and access token
    fitbit_id = session['fitbit_id']
    access_token = session['access_token']
    
    # retrieve data on chosen date via fitbit API
    date = request.args.get('date', session['heart_date'])
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
    except: # if date does not match format
        date = TODAY_DATE
    if pd.Timestamp(date).date() > TODAY_DATE: # if date in the future
        date = TODAY_DATE
    session['heart_date'] = date # store queried date
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
        except KeyError: # set to 0 if no resting HR
            resting_hr = 0
        week_heart.append({'Date': date, 'Resting HR': resting_hr})
    week_fig = px.bar(week_heart, x='Date', y='Resting HR')
    
    # if request.method == "POST":
    #     from momentfm import MOMENTPipeline
    #     model = MOMENTPipeline.from_pretrained(
    #         "AutonLab/MOMENT-1-large", 
    #         model_kwargs={"task_name": "reconstruction"},  # For anomaly detection, we will load MOMENT in `reconstruction` mode
    #         local_files_only=True,  # Whether or not to only look at local files (i.e., do not try to download the model).
    #     )
    #     # generate anomaly table
    #     anomalies = get_anomalies(day_heart, model).reset_index(drop=True)
    #     anomaly_thresh = request.form['thresh']
    #     try:
    #         anomaly_thresh = int(anomaly_thresh)
    #         assert anomaly_thresh > 0
    #     except:
    #         anomaly_thresh = 5

    #     # plot anomalies on graph
    #     anomalies['Anomaly'] = anomalies['Anomaly Score'] > anomaly_thresh
    #     day_fig = go.Figure()
    #     day_fig.add_trace(go.Scatter(x=anomalies.Time, y=anomalies['Recorded HR'],
    #                                  mode='lines+markers',
    #                                  name='Heart Rate'))
    #     day_fig.add_trace(go.Scatter(x=anomalies.loc[anomalies.Anomaly, 'Time'], 
    #                                  y=anomalies.loc[anomalies.Anomaly, 'Recorded HR'],
    #                                  mode='markers',
    #                                  name='Anomaly'))
    #     day_fig.update_layout(showlegend=False)

    #     anomalies = anomalies[anomalies['Anomaly']].drop(columns='Anomaly')

    #     return render_template("heart.html", 
    #                            tables=[anomalies.to_html(index=False, classes='data', header='true')],
    #                            date=date,
    #                            data_exists=True,
    #                            thresh=anomaly_thresh,
    #                            day_fig=day_fig.to_html(full_html=False),
    #                            week_fig=week_fig.to_html(full_html=False))
    # 
    # else:
    return render_template("heart.html", 
                            tables=None, 
                            date=date,
                            data_exists=len(day_heart)>0,
                            thresh='',
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
        session['heart_date'] = TODAY_DATE

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
        # if goal is "create one", will return empty, otherwise will already be set to original value
        step_goal = request.form['step'] or ori_step_goal
        sleep_goal = request.form['sleep'] or ori_sleep_goal

        if step_goal != 'Create one':
            try:
                step_goal = int(step_goal)
                assert step_goal >= 0
            except:
                step_goal = 'Create one'
        
        if sleep_goal != 'Create one':
            try:
                sleep_goal = float(sleep_goal)
                assert sleep_goal >= 0
            except:
                sleep_goal = 'Create one'

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

# if __name__ == '__main__': 
#     app.run(host='0.0.0.0', debug=True) 