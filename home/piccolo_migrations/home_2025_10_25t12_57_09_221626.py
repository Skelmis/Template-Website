from piccolo.apps.migrations.auto.migration_manager import MigrationManager


ID = "2025-10-25T12:57:09:221626"
VERSION = "1.30.0"
DESCRIPTION = ""


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="home", description=DESCRIPTION
    )

    manager.drop_column(
        table_class_name="Users",
        tablename="users",
        column_name="phone_number",
        db_column_name="phone_number",
        schema=None,
    )

    manager.drop_column(
        table_class_name="Users",
        tablename="users",
        column_name="signed_up_for_newsletter",
        db_column_name="signed_up_for_newsletter",
        schema=None,
    )

    return manager
