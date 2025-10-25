import os

from dotenv import load_dotenv
from piccolo.conf.apps import AppRegistry
from piccolo.engine import PostgresEngine

load_dotenv()

DB = PostgresEngine(
    config={
        "database": "test",
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "host": os.environ["POSTGRES_HOST"],
        "port": int(os.environ["POSTGRES_PORT"]),
    },
)

APP_REGISTRY = AppRegistry(
    apps=[
        "home.piccolo_app",
        "piccolo_admin.piccolo_app",
        "piccolo_api.mfa.authenticator.piccolo_app",
    ]
)
