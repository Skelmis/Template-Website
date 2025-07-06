from __future__ import annotations

import uuid
from enum import Enum

from piccolo.apps.user.tables import BaseUser
from piccolo.columns import (
    UUID,
    ForeignKey,
    Text,
    Serial,
)
from piccolo.columns.indexes import IndexMethod
from piccolo.table import Table

from home.util import AuditMixin


class AlertLevels(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"

    @classmethod
    def from_str(cls, level) -> AlertLevels:
        return cls[level.upper()]


class Alerts(AuditMixin, Table):
    id: Serial
    uuid = UUID(default=uuid.uuid4, index=True, index_method=IndexMethod.hash)
    target = ForeignKey(BaseUser, index=True, help_text="Who should be notified?")
    message = Text(help_text="The text to show the target on next request?")
    level = Text(help_text="The level to show it at", choices=AlertLevels)

    @classmethod
    async def create_alert(
        cls, user: BaseUser, message: str, level: AlertLevels
    ) -> Alerts:
        notif = Alerts(
            target=user,
            message=message,
            level=level,
        )
        await notif.save()
        return notif
