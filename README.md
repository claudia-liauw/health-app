# Health is Wealth
#### Video Demo:  [https://youtu.be/hkL0urMsANU](https://youtu.be/hkL0urMsANU)
#### Description:
A health tracker app for steps, sleep and heart rate with goal tracking for steps and sleep and anomaly detection for heart rate. Integrates with Fitbit API to retrieve data.

## How to run
Website: [endless-bobbette-claudia-liauw-a9f407dd.koyeb.app/](https://endless-bobbette-claudia-liauw-a9f407dd.koyeb.app/)

Does not include anomaly detection feature due to size limitations. To run with this feature, switch to branch `pre-deploy` and run locally:
```
docker compose up --build
```
Note: This will not work unless the redirect URL is updated within `app.py` and on the Fitbit app manager.

## Database
* Users table: username and hash
* Profile table: username, step goal and sleep goal

## Routes
### Register and login
The register and login pages are implemented similar to [Problem Set 9 (Finance)](https://cs50.harvard.edu/x/2024/psets/9/finance/). Users are prompted to provide a username, password and password confirmation. Fields are checked for completion, matching passwords and uniqueness of username. The password is hashed and stored in a users table. When a user is registered, a row is created in the profile table with default values of "Create one" for goals.

In login, the username and password are checked against the users table. The user is redirected to authenticate Fitbit.

### Authenticate and callback
Based on: [Fitbit OAuth Tutorial](https://dev.fitbit.com/build/reference/web-api/troubleshooting-guide/oauth2-tutorial/)

A PKCE code verifier and challenge and state are generated. Using the app's client ID, code challenge, state and requested scopes (activity, sleep and heart rate), the user is directed to the Fitbit authentication page. After allowing permissions, the user is redirected to the redirect URL.

The redirect URL comes with arguments for the authorisation code and state. Using the authorisation code and the earlier generated code verifier, a POST request is sent to Fitbit servers to generate the access token. This also pulls the user's Fitbit ID. Both are stored in Session.

### Profile
Profile displays the user's username, step goal and sleep goal as queried from the profile table. Goals are shown in a form for users to update with the current value as a placeholder. When goals have not been set, the placeholder shows the default value of "Create one". Users can set both goals or just one. If a field is left blank, the current value will be inserted back into the database. If an invalid value is entered, it will be set to "Create one".

### Steps
Upon visiting the page, Fitbit ID and access token are retrieved from the session. The page is decorated with `auth_required` which works similarly to [login_required](https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/) (also implemented), where the user is redirected to the authentication page if they have failed to successfully authenticate.

A GET request is sent to Fitbit servers to retrieve today's step data for the given user ID ([Fitbit Web API](https://dev.fitbit.com/build/reference/web-api/)). If the app cannot retrieve data as the user has not granted the required permissions, they will be redirected to the authentication page.

Today's total steps is checked against the step goal and the page displays whether the target has been met. If no goal has been set, a link will be displayed such that the user can click to go to the profile page.

Users can change the date for which to display graphs. The default value is today's date. If value entered is not a date or in the future, it will be set to today's date. A dataframe is constructed for data on the chosen date, summing the steps per hour. This is shown on a plotly graph.

Another GET request is sent to Fitbit servers to retrieve step data for the past 7 days from the specified date. Again, a dataframe is constructed and data is displayed as a plotly graph. If a goal has been set, the days where it has been achieved are highlighted.

### Sleep
Features are similar to steps, except only the week graph is shown.

Fitbit does not support automatic retrieval of 7 day data for sleep. The data is retrieved with a loop and displayed on a plotly graph. 

### Heart Rate
Features are similar to steps but there are no goals.

The chosen date is stored in Session so that anomaly detection will use the same date.

A dataframe is constructed for heart rate on the chosen date. Plotly graphs are shown displaying heart rate on the chosen date and the resting heart rate for the past 7 days. When resting heart rate is not available, it is set to 0.

A button to generate anomaly report will only be shown when there is heart rate data. When the button to generate the anomaly report is clicked, the [pre-trained anomaly detection MOMENT model](https://huggingface.co/AutonLab/MOMENT-1-large) is imported. There was no further fine-tuning or validation as that is not the focus of this project, thus the results are not to be taken seriously. The constructed dataframe is passed into the TimeSeriesDataset. Taking the first and last available timestamps, it constructs a new dataset with an interval of 5s, interpolating values up to 1 min. Then a list of sequences is constructed with a length of 512 each, as that is the input size to the MOMENT model. Only sequences with at least 50% data are used, using a mask to keep track.

The dataset is loaded into a PyTorch DataLoader and the MOMENT model is used for inference. It ignores masked data. The output is compared against the true signal and an anomaly score is calculated from the mean absolute percentage error. A dataframe is shown with timestamps where the anomaly score exceeds the anomaly threshold. Anomalies are also highlighted on the heart rate graph. The user can adjust the threshold. If an invalid value is provided, the threshold defaults to 5.