from __future__ import annotations

import datetime
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Self
from unittest.mock import AsyncMock

import pytest
from litestar.testing import AsyncTestClient
from piccolo.apps.tester.commands.run import refresh_db, set_env_var
from piccolo.conf.apps import Finder
from piccolo.table import create_db_tables, drop_db_tables
from piccolo.testing import ModelBuilder
from piccolo.utils.sync import run_sync

from template.controllers import AuthController
from template.saq.worker import SAQ_QUEUE
from template.tables import Users, APIToken

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
def patch_saq(monkeypatch) -> AsyncMock:
    saq_enqueue = AsyncMock()
    monkeypatch.setattr(SAQ_QUEUE, "enqueue", saq_enqueue)
    return saq_enqueue


class BaseGiven:
    data: dict[str, Any] = {}

    def user(
        self,
        username: str,
        *,
        admin: bool = False,
        superuser: bool = False,
        active: bool = True,
    ) -> Self:
        if not Users.objects().get(Users.username == username).run_sync():
            self.data["user"] = run_sync(
                ModelBuilder.build(
                    Users,
                    {
                        Users.username: username,
                        Users.admin: admin,
                        Users.active: active,
                        Users.superuser: superuser,
                    },
                )
            )
        else:
            self.data["user"] = (
                Users.objects().get(Users.username == username).run_sync()
            )
        return self

    @property
    def object(self) -> Users:
        return self.data["user"]

    @property
    def session_cookie(self) -> str:
        assert "user" in self.data, "Given must have called user first"
        return run_sync(AuthController.create_session_for_user(self.data["user"]))

    @property
    def api_token(self) -> APIToken:
        return run_sync(
            APIToken.create_api_token(
                self.data["user"],
                datetime.timedelta(hours=2),
                datetime.timedelta(days=1),
            )
        )

    def csrf_token(self, test_client: AsyncTestClient[Litestar]) -> str:
        resp = run_sync(test_client.get("/"))
        return resp.cookies["csrf_token"]


class BaseWhen:

    @property
    def db(self) -> Self:
        return self
