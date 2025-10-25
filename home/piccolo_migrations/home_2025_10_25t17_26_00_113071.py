from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.column_types import ForeignKey
from piccolo.columns.column_types import Serial
from piccolo.columns.indexes import IndexMethod
from piccolo.table import Table


class BaseUser(Table, tablename="piccolo_user", schema=None):
    id = Serial(
        null=False,
        primary_key=True,
        unique=False,
        index=False,
        index_method=IndexMethod.btree,
        choices=None,
        db_column_name="id",
        secret=False,
    )


class Users(Table, tablename="users", schema=None):
    id = Serial(
        null=False,
        primary_key=True,
        unique=False,
        index=False,
        index_method=IndexMethod.btree,
        choices=None,
        db_column_name="id",
        secret=False,
    )


ID = "2025-10-25T17:26:00:113071"
VERSION = "1.30.0"
DESCRIPTION = ""


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="home", description=DESCRIPTION
    )

    manager.alter_column(
        table_class_name="Alerts",
        tablename="alerts",
        column_name="target",
        db_column_name="target",
        params={"references": Users, "null": False},
        old_params={"references": BaseUser, "null": True},
        column_class=ForeignKey,
        old_column_class=ForeignKey,
        schema=None,
    )

    return manager
