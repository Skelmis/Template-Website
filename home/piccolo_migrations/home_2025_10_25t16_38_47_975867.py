from piccolo.apps.migrations.auto.migration_manager import MigrationManager


ID = "2025-10-25T16:38:47:975867"
VERSION = "1.30.0"
DESCRIPTION = ""


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="home", description=DESCRIPTION
    )

    manager.rename_column(
        table_class_name="Users",
        tablename="users",
        old_column_name="auths_via_magic_link",
        new_column_name="auths_without_password",
        old_db_column_name="auths_via_magic_link",
        new_db_column_name="auths_without_password",
        schema=None,
    )

    return manager
