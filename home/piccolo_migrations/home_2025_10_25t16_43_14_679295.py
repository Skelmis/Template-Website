from piccolo.apps.migrations.auto.migration_manager import MigrationManager


ID = "2025-10-25T16:43:14:679295"
VERSION = "1.30.0"
DESCRIPTION = ""


async def forwards():
    manager = MigrationManager(
        migration_id=ID, app_name="home", description=DESCRIPTION
    )

    manager.rename_table(
        old_class_name="OAuthEntry",
        old_tablename="o_auth_entry",
        new_class_name="OAuthEntry",
        new_tablename="oauth_entry",
        schema=None,
    )

    return manager
