from __future__ import annotations

from piccolo.apps.user.tables import BaseUser
from piccolo.columns import ForeignKey, Serial, Boolean
from piccolo.table import Table


class Profile(Table, tablename="piccolo_user_profile"):
    id: Serial
    user = ForeignKey(
        BaseUser,
        index=True,
        unique=True,
        help_text="The user this profile is for",
    )
    email_is_verified = Boolean(
        default=False,
        help_text="Is the users current email address verified?",
    )

    @classmethod
    async def get_or_create(cls, user: BaseUser) -> Profile:
        return await cls.objects().get_or_create(cls.user == user)
