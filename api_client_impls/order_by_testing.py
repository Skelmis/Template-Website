import asyncio
import datetime
from uuid import UUID

from pydantic import Field, BaseModel

from template.crud import CRUDClient
from template.crud.controller import (
    SearchModel,
    SearchItemIn,
    JoinModel,
    OrderByRequestModel,
    OrderByFilters,
)
from template.tables import AlertLevels, Users, APIToken
from template.util.table_mixins import utc_now


class NewAlertModel(BaseModel):
    target: int = Field(description="The ID of the user to show the alert to")
    message: str = Field(description="The message to display")
    level: AlertLevels = Field(description="The level of the alert when displayed")


class UserModel(BaseModel):
    username: str = Field(description="The username of the user")
    email: str = Field(description="The email of the user")


class AlertOutModel(NewAlertModel):
    target: UserModel = Field(description="The user who will receive this alert")
    uuid: UUID = Field(description="The UUID primary key of this alert")
    has_been_shown: bool = Field(description="Has the user seen this yet?")
    was_shown_at: datetime.datetime | None = Field(
        description="The time the user was shown the alert"
    )


class AlertPatchModel(BaseModel):
    has_been_shown: bool | None = Field(
        default=None,
        description="Has the user seen this yet?",
    )
    was_shown_at: datetime.datetime | None = Field(
        default=None, description="The time the user was shown the alert"
    )


async def main():
    # Fake an auth session
    user = await Users.objects().first()
    token = await APIToken.create_api_token(
        user, datetime.timedelta(hours=2), datetime.timedelta(days=1)
    )

    client: CRUDClient[NewAlertModel, AlertOutModel] = CRUDClient(
        "http://localhost:8000/api/alerts",
        AlertOutModel,
        headers={"X-API-KEY": token.token},
    )

    # Create an alert, mark it as seen and then delete it
    alert = await client.create_record(
        NewAlertModel(target=1, message="Hello World!", level=AlertLevels.INFO)
    )
    await client.create_record(
        NewAlertModel(target=1, message="Hello World!", level=AlertLevels.INFO)
    )
    alert_1 = await client.create_record(
        NewAlertModel(target=1, message="Oh no", level=AlertLevels.WARNING)
    )
    await client.patch_record(
        alert_1.uuid, AlertPatchModel(was_shown_at=utc_now(), has_been_shown=True)
    )
    alert_2 = await client.create_record(
        NewAlertModel(target=1, message="Not good!", level=AlertLevels.ERROR)
    )
    await client.patch_record(
        alert_2.uuid, AlertPatchModel(was_shown_at=utc_now(), has_been_shown=True)
    )
    total_records = await client.get_total_record_count()
    print(f"We currently have {total_records.total_records} alerts!")

    records_order_1 = await client.get_all_records_as_list(
        order_by=OrderByRequestModel(
            fields=[OrderByFilters(column_name="target", order="descending")]
        ),
        page_size=2,
    )
    print(
        len(set(r.uuid for r in records_order_1)),
        [(r.uuid, r.was_shown_at) for r in records_order_1],
    )


if __name__ == "__main__":
    asyncio.run(main())
