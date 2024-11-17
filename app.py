from flask import Flask, request, render_template, session
from flask_session import Session
import pandas as pd
import plotly.express as px
from src.utils import get_anomalies

app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

@app.route("/")
def index():
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
    return render_template("index.html", 
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

@app.route("/heart-rate")
def heart_rate():
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