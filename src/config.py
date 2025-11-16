from datetime import datetime, timedelta
from flask import Flask

app = Flask(__name__)

app.config['DATABASE'] = 'wegewart.db'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)