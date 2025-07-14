from dotenv import load_dotenv
from piccolo.conf.apps import AppRegistry
from piccolo.engine import SQLiteEngine

load_dotenv()

DB = SQLiteEngine(path="test_suite.sqlite")

APP_REGISTRY = AppRegistry(
    apps=[
        "home.piccolo_app",
        "piccolo_admin.piccolo_app",
        "piccolo_api.mfa.authenticator.piccolo_app",
    ]
)
