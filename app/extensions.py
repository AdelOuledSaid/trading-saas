from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_caching import Cache

db = SQLAlchemy()

login_manager = LoginManager()
login_manager.login_view = "auth.login"

cache = Cache(config={
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
})