import datetime
from typing import Self, Any

import httpx
import pytest
from litestar import Litestar
from litestar.exceptions import NotFoundException
from litestar.testing import AsyncTestClient
from piccolo.testing import ModelBuilder
from piccolo.utils.sync import run_sync

from api_client_impls.alerts import NewAlertModel, AlertOutModel
from template.crud import CRUDClient
from template.piccolo_migrations.home_2025_10_27t13_31_08_066636 import Users
from template.tables import Alerts, APIToken
from tests.conftest import BaseGiven, BaseWhen


class CaseGiven(BaseGiven):
    def alert_api_client(
        self, test_client: AsyncTestClient[Litestar]
    ) -> CRUDClient[NewAlertModel, AlertOutModel]:
        client = CRUDClient(
            "/api/alerts",
            AlertOutModel,
        )
        client.client = test_client
        test_client.headers["X-API-KEY"] = self.api_token.token
        test_client.base_url = f"{test_client.base_url}/api/alerts"
        return client


Given = CaseGiven()


# noinspection PyMethodMayBeStatic
class CaseWhen(BaseWhen):
    def contains_no_alerts(self):
        assert Alerts.count().run_sync() == 0

    def contains_alerts(self, *, count: int, target: Users) -> list[Alerts]:
        results = []
        for _ in range(count):
            results.append(ModelBuilder.build_sync(Alerts, defaults={"target": target}))

        return results


When = CaseWhen()


async def test_alerts_get_all_with_empty_db(test_client: AsyncTestClient[Litestar]):
    client = Given.user("skelmis").alert_api_client(test_client)
    When.db.contains_no_alerts()
    assert await client.get_all_records_as_list() == []


async def test_alerts_get_all_with_one_page(test_client: AsyncTestClient[Litestar]):
    client = Given.user("skelmis").alert_api_client(test_client)
    When.db.contains_alerts(count=5, target=Given.user("skelmis").object)

    results = await client.get_all_records_as_list(page_size=5)
    assert len(results) == 5


async def test_alerts_get_all_with_two_pages(test_client: AsyncTestClient[Litestar]):
    client = Given.user("skelmis").alert_api_client(test_client)
    When.db.contains_alerts(count=9, target=Given.user("skelmis").object)

    r_1 = await client.get_record_page(page_size=5)
    assert len(r_1.data) == 5
    r_2 = await client.get_record_page(page_size=5, next_cursor=r_1.next_cursor)
    assert len(r_2.data) == 4

    # Ensure no duplicates
    r_3 = [r.uuid for r in r_1.data]
    r_3.extend(r.uuid for r in r_2.data)
    assert len(set(r_3)) == 9


async def test_crud_client(test_client: AsyncTestClient[Litestar]):
    """Asserts the get_all_records_as_list method does the same as the underlying methods"""
    client = Given.user("skelmis").alert_api_client(test_client)
    When.db.contains_alerts(count=9, target=Given.user("skelmis").object)

    r_1 = await client.get_record_page(page_size=5)
    assert len(r_1.data) == 5
    r_2 = await client.get_record_page(page_size=5, next_cursor=r_1.next_cursor)
    assert len(r_2.data) == 4

    # Ensure no duplicates
    r_3 = [r.uuid for r in r_1.data]
    r_3.extend(r.uuid for r in r_2.data)
    assert len(set(r_3)) == 9

    r_4 = await client.get_all_records_as_list(page_size=5)
    r_5 = [r.uuid for r in r_4]
    assert r_5 == r_3


async def test_valid_get_object(test_client: AsyncTestClient[Litestar]):
    client = Given.user("skelmis").alert_api_client(test_client)
    result = When.db.contains_alerts(count=1, target=Given.user("skelmis").object)[0]

    r_1 = await client.get_record(result.uuid)
    assert r_1.uuid == result.uuid


async def test_invalid_get_object(test_client: AsyncTestClient[Litestar]):
    client = Given.user("skelmis").alert_api_client(test_client)
    result = When.db.contains_alerts(
        count=1,
        target=Given.user("not_skelmis").object,
    )[0]

    with pytest.raises(httpx.HTTPStatusError) as e:
        await client.get_record(result.uuid)

    assert e.value.response.status_code == 404


async def test_delete_valid_object(test_client: AsyncTestClient[Litestar]):
    client = Given.user("skelmis").alert_api_client(test_client)
    result = When.db.contains_alerts(count=1, target=Given.user("skelmis").object)[0]

    await client.delete_record(result.uuid)
    assert await Alerts.count() == 0


async def test_delete_valid_object_with_multiple_present(
    test_client: AsyncTestClient[Litestar],
):
    client = Given.user("skelmis").alert_api_client(test_client)
    result = When.db.contains_alerts(count=1, target=Given.user("skelmis").object)[0]
    When.db.contains_alerts(
        count=1,
        target=Given.user("not_skelmis").object,
    )

    await client.delete_record(result.uuid)
    assert await Alerts.count() == 1


async def test_delete_on_non_existent_object(test_client: AsyncTestClient[Litestar]):
    client = Given.user("skelmis").alert_api_client(test_client)
    result = When.db.contains_alerts(count=1, target=Given.user("skelmis").object)[0]
    When.db.contains_alerts(
        count=1,
        target=Given.user("not_skelmis").object,
    )

    await client.delete_record(result.uuid)
    assert await Alerts.count() == 1

    with pytest.raises(httpx.HTTPStatusError) as e:
        await client.delete_record(result.uuid)

    assert e.value.response.status_code == 404


async def test_delete_invalid_object(test_client: AsyncTestClient[Litestar]):
    client = Given.user("skelmis").alert_api_client(test_client)
    result = When.db.contains_alerts(
        count=1,
        target=Given.user("not_skelmis").object,
    )[0]

    with pytest.raises(httpx.HTTPStatusError) as e:
        await client.delete_record(result.uuid)

    assert e.value.response.status_code == 404
    assert await Alerts.count() == 1


# TODO Add tests for POST, PATCH, Search
