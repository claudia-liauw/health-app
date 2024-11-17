from flask import Flask, request, render_template, session
from flask_session import Session
import pandas as pd
from src.utils import get_anomalies

app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

data = pd.read_csv('data/fitbit_apr/heartrate_seconds_merged.csv')
data.Time = pd.to_datetime(data.Time)
hr = data.loc[(data.Id == data.Id.unique()[0]) & (data.Time < '2016-04-20')]

from momentfm import MOMENTPipeline
model = MOMENTPipeline.from_pretrained(
    "AutonLab/MOMENT-1-large", 
    model_kwargs={"task_name": "reconstruction"},  # For anomaly detection, we will load MOMENT in `reconstruction` mode
    local_files_only=True,  # Whether or not to only look at local files (i.e., do not try to download the model).
)

@app.route("/")
def index():
    anomalies = get_anomalies(hr, model).reset_index(drop=True)
    return render_template("index.html", tables=[anomalies.to_html(classes='data', header='true')])