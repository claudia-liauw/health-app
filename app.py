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
    data = pd.read_csv('data/fitbit_apr/hourlySteps_merged.csv')
    data = data.rename(columns={'ActivityHour': 'Hour', 'StepTotal': 'Steps'})
    data.Hour = pd.to_datetime(data.Hour)
    steps = data.loc[(data.Id == data.Id.unique()[0]) & (data.Hour < '2016-04-13')]
    fig = px.bar(steps, x='Hour', y='Steps')
    return render_template("index.html", fig=fig.to_html(full_html=False))

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