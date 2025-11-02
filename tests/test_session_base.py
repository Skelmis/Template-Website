from datetime import timedelta

import arrow
from freezegun import freeze_time
from piccolo_api.session_auth.tables import SessionsBase

from home.util.table_mixins import utc_now


async def test_session_base():
    """Testing to ensure sessions behave how I expect"""
    # I sometimes cant understand < > at face value,
    # so this is how I validate my understanding of things
    with freeze_time("2025-01-14"):
        # Create a session that expires in 1 day,
        # but can be expanded up to 3 days
        now = arrow.get(utc_now())
        session = await SessionsBase.create_session(
            1,
            expiry_date=now.shift(days=1).naive,
            max_expiry_date=now.shift(days=3).naive,
        )
        assert session.expiry_date == now.shift(days=1).naive
        assert session.max_expiry_date == now.shift(days=3).naive

    with freeze_time("2025-01-18"):
        # Sessions shouldn't be valid more than 3 days
        user_id = await SessionsBase.get_user_id(session.token)
        assert (
            user_id is None
        ), "Session was valid despite being outside max_expiry_date"

    with freeze_time("2025-01-14"):
        # Sessions should be valid same day
        user_id = await SessionsBase.get_user_id(session.token)
        assert user_id == 1

    with freeze_time(now.shift(hours=12).datetime):
        # Sessions should be valid same day
        user_id = await SessionsBase.get_user_id(session.token)
        assert user_id == 1

    with freeze_time(now.shift(days=2).datetime):
        # Sessions should not be valid if after expiry_date
        # but is still before max_expiry_date
        user_id = await SessionsBase.get_user_id(session.token)
        assert user_id is None, (
            "Session was still valid despite being outside "
            "expiry_date but within max_expiry_date"
        )

    with freeze_time(now.shift(hours=12).datetime):
        user_id = await SessionsBase.get_user_id(session.token, timedelta(days=1))
        assert user_id == 1

        with freeze_time(now.shift(hours=12, days=1).datetime):
            user_id = await SessionsBase.get_user_id(session.token, timedelta(days=1))
            assert user_id == 1
