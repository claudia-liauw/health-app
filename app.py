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
from sqlalchemy import create_engine, text

app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

DB_PATH = os.environ.get('DB_PATH', 'sqlite:///data/users.db')
TODAY_DATE = datetime.date.today()
WARNING = "WARNING: You are not connected to Fitbit. Certain features, such as the changing of dates, will not work."

# Database
engine = create_engine(DB_PATH)
# create tables if they don't exist
with engine.connect() as con:
    con.execute(text("""
                     CREATE TABLE IF NOT EXISTS users(
                        username TEXT NOT NULL UNIQUE, 
                        hash TEXT NOT NULL,
                        has_fitbit BOOL NOT NULL)
                     """))
    con.execute(text("""
                     CREATE TABLE IF NOT EXISTS profile(
                        username TEXT NOT NULL UNIQUE, 
                        step_goal TEXT NOT NULL,
                        sleep_goal TEXT NOT NULL,
                        FOREIGN KEY(username) REFERENCES users(username))
                     """))
    con.commit()

# day_steps = pd.read_csv('data/fitbit_apr/hourlySteps_merged.csv')
# day_steps.to_sql('day_steps', engine, index=False)
# daily_steps = pd.read_csv('data/fitbit_apr/dailySteps_merged.csv')
# daily_steps.to_sql('daily_steps', engine, index=False)
# daily_sleep = pd.read_csv('data/fitbit_apr/sleepDay_merged.csv')
# daily_sleep.to_sql('daily_sleep', engine, index=False)
# heart_data = pd.read_csv('data/fitbit_apr/heartrate_seconds_merged.csv')
# heart_data = heart_data.iloc[:5000]
# heart_data.to_sql('heart_data', engine, index=False)


@app.route("/")
@login_required
@auth_required
def steps():
    warning = ''

    # get user ID and access token
    fitbit_id = session['fitbit_id']
    
    if fitbit_id == 'no_fitbit':
        warning = WARNING
        date = datetime.date(2016, 4, 12)

        total_steps = 13162
        if DB_PATH.startswith('sqlite'):
            day_steps = pd.read_csv('data/fitbit_apr/hourlySteps_merged.csv')
        else: 
            day_steps = pd.read_sql_table('day_steps', con=engine)
        day_steps = day_steps.rename(columns={'ActivityHour': 'Hour', 'StepTotal': 'Steps'})
        day_steps.Hour = pd.to_datetime(day_steps.Hour)
        hourly_steps = day_steps.loc[(day_steps.Id == day_steps.Id.unique()[0]) & (day_steps.Hour < '2016-04-13')]

        if DB_PATH.startswith('sqlite'):
            daily_steps = pd.read_csv('data/fitbit_apr/dailySteps_merged.csv')
        else:
            daily_steps = pd.read_sql_table('daily_steps', con=engine)
        daily_steps = daily_steps.rename(columns={'ActivityDay': 'Date', 'StepTotal': 'Steps'})
        daily_steps.Date = pd.to_datetime(daily_steps.Date)
        week_steps = daily_steps.loc[(daily_steps.Id == daily_steps.Id.unique()[0]) & (daily_steps.Date < '2016-04-19')]

    else:
        access_token = session['access_token']

        # retrieve today's data via fitbit API
        today_json = retrieve_data('steps', fitbit_id, access_token, TODAY_DATE, period='1d')
        try: 
            total_steps = today_json['activities-steps'][0]['value']
        except KeyError:
            return redirect('/authenticate')

        # retrieve chosen date data via fitbit API
        date = request.args.get('date', TODAY_DATE)
        try:
            datetime.datetime.strptime(date, "%Y-%m-%d")
        except: # if date does not match format
            date = TODAY_DATE
        if pd.Timestamp(date).date() > TODAY_DATE: # if date in the future
            date = TODAY_DATE
        day_json = retrieve_data('steps', fitbit_id, access_token, date, period='1d', detail='1min')

        # get steps by hour
        day_steps = pd.DataFrame(day_json['activities-steps-intraday']['dataset'])
        day_steps.time = pd.to_datetime(str(date) + ' ' + day_steps.time)
        hourly_steps = day_steps.groupby(pd.Grouper(key='time', freq='h')).sum().reset_index()
        hourly_steps = hourly_steps.rename(columns={'time': 'Hour', 'value': 'Steps'})
    
        # retrieve week data via fitbit API
        week_json = retrieve_data('steps', fitbit_id, access_token, date, '7d')

        # get week's steps
        week_steps = pd.DataFrame(week_json['activities-steps'])
        week_steps['Steps'] = pd.to_numeric(week_steps.value)
        week_steps = week_steps.rename(columns={'dateTime': 'Date'})

    # check if target is met
    with engine.connect() as db:
        step_goal = db.execute(
            text("SELECT step_goal FROM profile WHERE username = :username"),
            {"username": session['user_id']}
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

    # display steps by hour
    hourly_fig = px.bar(hourly_steps, x='Hour', y='Steps')

    # display week's steps and if target has been met
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
                           warning=warning,
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
    warning = ''

    # get user ID and access token
    fitbit_id = session['fitbit_id']

    if fitbit_id == 'no_fitbit':
        warning = WARNING

        date = pd.Timestamp('2016-04-17')
        
        hours_slept = np.round(700 / 60, 2)

        if DB_PATH.startswith('sqlite'):
            daily_sleep = pd.read_csv('data/fitbit_apr/sleepDay_merged.csv')
        else:
            daily_sleep = pd.read_sql_table('daily_sleep', con=engine)
        daily_sleep = daily_sleep.rename(columns={'SleepDay': 'Date', 'TotalMinutesAsleep': 'Total Minutes Asleep'})
        daily_sleep.Date = pd.to_datetime(daily_sleep.Date)
        week_sleep = daily_sleep.loc[(daily_sleep.Id == daily_sleep.Id.unique()[0]) & (daily_sleep.Date < '2016-04-19')]

    else:
        access_token = session['access_token']

        # retrieve today's data via fitbit API
        today_json = retrieve_data('sleep', fitbit_id, access_token, TODAY_DATE, version=1.2)
        try: 
            hours_slept = np.round(today_json['summary']['totalMinutesAsleep'] / 60, 2)
        except KeyError:
            return redirect('/authenticate')
        
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
    
    # check if target is met
    with engine.connect() as db:
        sleep_goal = db.execute(text(
            "SELECT sleep_goal FROM profile WHERE username = :username"), 
            {"username": session['user_id']}
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
                           warning=warning,
                           hours_slept=hours_slept,
                           sleep_goal=sleep_goal_fmt,
                           target=target,
                           date=str(date.date()),
                           fig=fig.to_html(full_html=False))

@app.route("/heart-rate", methods=["GET", "POST"])
@login_required
@auth_required
def heart_rate():
    warning = ''

    # get user ID and access token
    fitbit_id = session['fitbit_id']

    if fitbit_id == 'no_fitbit':
        warning = WARNING

        date = datetime.date(2016, 4, 12)

        if DB_PATH.startswith('sqlite'):
            heart_data = pd.read_csv('data/fitbit_apr/heartrate_seconds_merged.csv')
        else:
            heart_data = pd.read_sql_table('heart_data', con=engine)
        heart_data = heart_data.rename(columns={'Value': 'Heart Rate'})
        heart_data.Time = pd.to_datetime(heart_data.Time)
        day_heart = heart_data.loc[(heart_data.Id == heart_data.Id.unique()[0]) & (heart_data.Time < '2016-04-13')]

    else:
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
        day_json = retrieve_data('heart', fitbit_id, access_token, date, period='1d', detail='1min')
        try: 
            day_heart = pd.DataFrame(day_json['activities-heart-intraday']['dataset'])
        except KeyError:
            return redirect('/authenticate')
        
        # if no data
        if len(day_heart) == 0:
            day_heart['time'] = date
            day_heart['value'] = 0
        day_heart.time = pd.to_datetime(str(date) + ' ' + day_heart.time)
        day_heart = day_heart.rename(columns={'time': 'Time', 'value': 'Heart Rate'})
        
        # retrieve week data via fitbit API
        week_json = retrieve_data('heart', fitbit_id, access_token, date, period='7d')
        week_heart = []
        for day in range(7):
            date = week_json['activities-heart'][day]['dateTime']
            try:
                resting_hr = week_json['activities-heart'][day]['value']['restingHeartRate']
            except KeyError: # set to 0 if no resting HR
                resting_hr = 0
            week_heart.append({'Date': date, 'Resting HR': resting_hr})
    
    # display heart rate on chosen date
    day_fig = px.line(day_heart, x='Time', y='Heart Rate', markers=True)

    # display week data
    if fitbit_id == 'no_fitbit':
        week_fig_html = "Resting heart rate: No data"
    else:
        week_fig = px.bar(week_heart, x='Date', y='Resting HR')
        week_fig_html = week_fig.to_html(full_html=False)
    
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
                            warning=warning,
                            tables=None, 
                            date=date,
                            data_exists=len(day_heart)>0,
                            thresh='',
                            day_fig=day_fig.to_html(full_html=False),
                            week_fig=week_fig_html)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        confirmation = request.form['confirmation']
        has_fitbit = 'fitbit' in request.form

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
        with engine.connect() as db:
            try:
                db.execute(text("INSERT INTO users (username, hash, has_fitbit) VALUES (:username, :hash, :has_fitbit)"), 
                           {"username": username, "hash": hash, "has_fitbit": has_fitbit})
                db.execute(text("""INSERT INTO profile (username, step_goal, sleep_goal)
                           VALUES (:username, 'Create one', 'Create one')"""),
                           {"username": username})
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
        with engine.connect() as db:
            rows = db.execute(
                text("SELECT * FROM users WHERE username = :username"), 
                {"username": request.form.get("username")}
            ).fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0][1], request.form.get("password")
        ):
            return render_template("login.html", invalid='Invalid username or password!')

        # Remember which user has logged in
        session["user_id"] = rows[0][0]
        session['heart_date'] = TODAY_DATE

        # Set fitbit id if user has no fitbit
        has_fitbit = rows[0][2]
        if not has_fitbit:
            session['fitbit_id'] = 'no_fitbit'

        # Redirect user to authenticate
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
    with engine.connect() as db:
        goals = db.execute(
            text("SELECT * FROM profile WHERE username = :username"),
            {"username": username}
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

        with engine.connect() as db:
            db.execute(text("UPDATE profile SET step_goal = :step_goal, sleep_goal = :sleep_goal WHERE username = :username"), 
                       {"step_goal": step_goal, "sleep_goal": sleep_goal, "username": username})
            db.commit()
        return redirect("/profile")
    else:
        return render_template("profile.html", 
                               username=username, 
                               step_goal=ori_step_goal, 
                               sleep_goal=ori_sleep_goal)

CLIENT_ID = '23PQH4'
REDIRECT_URL = os.environ.get('REDIRECT_URL', 'http://localhost:5000/callback')

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

if not os.environ.get('KOYEB'):
    if __name__ == '__main__': 
        app.run(host='0.0.0.0', debug=True) 