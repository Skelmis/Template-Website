from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from litestar.testing import AsyncTestClient
from piccolo.apps.tester.commands.run import refresh_db, set_env_var
from piccolo.conf.apps import Finder
from piccolo.table import create_db_tables, drop_db_tables

from home.controllers import AuthController
from home.saq.worker import SAQ_QUEUE
from home.tables import Users

if TYPE_CHECKING:
    from litestar import Litestar


async def scaffold_db():
    user_1 = await Users.create_user(
        "user_1",
        "password",
        email="user_1-templatewebsite@post.org.nz",
        name="user_1",
        active=True,
    )
    staff_1 = await Users.create_user(
        "staff_1",
        "password",
        email="staff_1-templatewebsite@post.org.nz",
        name="staff_1",
        active=True,
        admin=True,
    )


@pytest.fixture(scope="function", autouse=True)
async def configure_testing():
    # Setup DB per test
    with set_env_var(var_name="PICCOLO_CONF", temp_value="piccolo_conf_test"):
        from app import app

        app.debug = True

        refresh_db()
        tables = Finder().get_table_classes()
        # Ensure DB is cleared from any prior hanging tests
        await drop_db_tables(*tables)

        # Set up DB
        await create_db_tables(*tables)
        await scaffold_db()


@pytest.fixture(scope="function")
async def test_client() -> AsyncIterator[AsyncTestClient[Litestar]]:
    from app import app

    async with AsyncTestClient(app=app) as client:
        yield client


@pytest.fixture(scope="function")
async def session_cookie(request) -> str:
    user = await Users.objects().get(Users.username == request.param)
    return await AuthController.create_session_for_user(user)


@pytest.fixture(scope="function")
async def csrf_token(test_client: AsyncTestClient[Litestar]) -> str:
    resp = await test_client.get("/")
    return resp.cookies["csrf_token"]


@pytest.fixture(scope="function")
def patch_saq(monkeypatch) -> AsyncMock:
    saq_enqueue = AsyncMock()
    monkeypatch.setattr(SAQ_QUEUE, "enqueue", saq_enqueue)
    return saq_enqueue
