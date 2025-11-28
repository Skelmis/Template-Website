import datetime
from datetime import timedelta
from typing import Any

import arrow
import httpx
import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from litestar import Litestar
from litestar.testing import AsyncTestClient
from piccolo.utils.sync import run_sync

from template.tables import APIToken, Users
from tests.conftest import BaseGiven


Given = BaseGiven()


class Then:
    data: dict[str, Any] = {}

    @property
    def request_initial_auth_token(self):
        resp = run_sync(
            self.data["test_client"].post(
                "/auth/token/initial",
                data={"_csrf_token": self.data["csrf_token"]},
                cookies={
                    "csrf_token": self.data["csrf_token"],
                    "id": self.data["session_cookie"],
                },
                follow_redirects=False,
            )
        )
        return resp


async def test_getting_token_from_session(
    test_client: AsyncTestClient[Litestar],
    patch_saq,
):
    csrf_token = Given.csrf_token(test_client)
    session_cookie = Given.user("user_1").session_cookie
    then = Then()
    then.data["test_client"] = test_client
    then.data["csrf_token"] = csrf_token
    then.data["session_cookie"] = session_cookie

    resp: httpx.Response = then.request_initial_auth_token
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data
    assert "expiry_date" in data
    assert "max_expiry_date" in data
    # assert resp.json() == {
    #     "expiry_date": "2025-11-02T09:34:19.118230Z",
    #     "max_expiry_date": "2025-11-05T07:34:19.118332Z",
    #     "token": "5a18649831c61bbc570126dc32eb78711ed88bc98d00a331a3bfcc5ad9ca964e",
    # }


async def test_guard(
    test_client: AsyncTestClient[Litestar],
    patch_saq,
):
    csrf_token = Given.csrf_token(test_client)
    session_cookie = Given.user("user_1").session_cookie
    resp_1: httpx.Response = await test_client.post(
        "/auth/token/refresh",
        data={"_csrf_token": csrf_token},
        cookies={"csrf_token": csrf_token, "id": session_cookie},
        follow_redirects=False,
    )
    assert resp_1.status_code == 401
    resp_2: httpx.Response = await test_client.post(
        "/auth/token/refresh",
        headers={"X-API-KEY": "test"},
        follow_redirects=False,
    )
    assert resp_2.status_code == 401


@freeze_time("2013-04-09")
async def test_token_extension_route(
    test_client: AsyncTestClient[Litestar],
    patch_saq,
):
    csrf_token = Given.csrf_token(test_client)
    session_cookie = Given.user("user_1").session_cookie
    resp: httpx.Response = await test_client.post(
        "/auth/token/initial",
        data={"_csrf_token": csrf_token},
        cookies={"csrf_token": csrf_token, "id": session_cookie},
        follow_redirects=False,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data
    assert "expiry_date" in data
    assert "max_expiry_date" in data

    resp_2: httpx.Response = await test_client.post(
        "/auth/token/refresh",
        headers={"X-API-KEY": data["token"]},
        follow_redirects=False,
    )
    assert resp_2.status_code == 200
    data_2 = resp_2.json()
    assert "token" in data_2
    assert "expiry_date" in data_2
    assert "max_expiry_date" in data_2
    assert data["token"] == data_2["token"]
    assert (
        arrow.get(data_2["expiry_date"]).datetime
        == arrow.get(data["expiry_date"]).shift(hours=2).datetime
    )
    assert data["max_expiry_date"] == data_2["max_expiry_date"]


@freeze_time("2013-04-09")
async def test_token_extension(patch_saq):
    t_1 = await APIToken.create_api_token(
        await Users.objects().first(), timedelta(hours=2), timedelta(days=2)
    )

    t_2 = await APIToken.validate_token_is_valid(t_1.token)
    assert t_2 is True

    # noinspection PyTypeChecker
    t_3: APIToken = await APIToken.get_token(
        t_1.token,
        increase_window=timedelta(hours=2),
        expiry_window=timedelta(hours=2),
        max_expiry_window=timedelta(days=2),
    )
    assert t_1.token == t_3.token
    assert t_3.expiry_date == arrow.get(t_1.expiry_date).shift(hours=2).datetime


async def test_token_extension_new_token(patch_saq):
    with freeze_time(datetime.datetime(2020, 1, 1, 5, 5)):
        t_1 = await APIToken.create_api_token(
            await Users.objects().first(), timedelta(hours=2), timedelta(hours=3)
        )

    with freeze_time(datetime.datetime(2020, 1, 1, 6, 50)):
        # noinspection PyTypeChecker
        t_3: APIToken = await APIToken.get_token(
            t_1.token,
            increase_window=timedelta(hours=2),
            expiry_window=timedelta(hours=2),
            max_expiry_window=timedelta(days=2),
        )

    assert t_3 is not None
    assert t_1.token != t_3.token


async def test_delete(
    test_client: AsyncTestClient[Litestar],
    patch_saq,
):
    csrf_token = Given.csrf_token(test_client)
    session_cookie = Given.user("user_1").session_cookie
    resp: httpx.Response = await test_client.post(
        "/auth/token/initial",
        data={"_csrf_token": csrf_token},
        cookies={"csrf_token": csrf_token, "id": session_cookie},
        follow_redirects=False,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data
    assert "expiry_date" in data
    assert "max_expiry_date" in data

    resp_2: httpx.Response = await test_client.post(
        "/auth/token/refresh",
        headers={"X-API-KEY": data["token"]},
        follow_redirects=False,
    )
    assert resp_2.status_code == 200

    resp_3: httpx.Response = await test_client.delete(
        "/auth/token",
        headers={"X-API-KEY": data["token"]},
        follow_redirects=False,
    )
    assert resp_3.status_code == 200

    resp_4: httpx.Response = await test_client.post(
        "/auth/token/refresh",
        headers={"X-API-KEY": data["token"]},
        follow_redirects=False,
    )
    assert resp_4.status_code == 401
