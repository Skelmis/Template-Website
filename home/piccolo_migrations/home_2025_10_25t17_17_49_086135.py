from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import Timestamp
from piccolo.columns.column_types import Timestamptz


ID = "2025-10-25T17:17:49:086135"
VERSION = "1.30.0"
DESCRIPTION = ""


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="home", description=DESCRIPTION
    )

    manager.alter_column(
        table_class_name="OAuthEntry",
        tablename="oauth_entry",
        column_name="last_login",
        db_column_name="last_login",
        params={},
        old_params={},
        column_class=Timestamptz,
        old_column_class=Timestamp,
        schema=None,
    )

    manager.alter_column(
        table_class_name="Users",
        tablename="users",
        column_name="last_login",
        db_column_name="last_login",
        params={},
        old_params={},
        column_class=Timestamptz,
        old_column_class=Timestamp,
        schema=None,
    )

    return manager
