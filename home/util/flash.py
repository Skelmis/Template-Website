from typing import Literal

from litestar import Request
from litestar.connection import ASGIConnection
from litestar.plugins.flash import flash
from piccolo.apps.user.tables import BaseUser


def alert(
    request: Request | ASGIConnection,
    message: str,
    level: Literal["info", "warning", "error", "success"] = "info",
):
    """A helper function given we hard code level in templates"""
    flash(request, message, category=level)


async def inject_alerts(request: Request | ASGIConnection, user: BaseUser):
    """Ensure lazy alerts make it through to the user"""
    from home.tables import Alerts

    # noinspection PyTypeChecker
    alerts_to_show: list[Alerts] = await Alerts.objects().where(
        Alerts.target == user,
    )
    for alert_obj in alerts_to_show:
        alert(request, alert_obj.message, alert_obj.level)
        # noinspection PyTypeChecker
        await alert_obj.delete().where(
            Alerts.uuid == alert_obj.uuid,
        )
