import asyncio
import datetime
from uuid import UUID

from pydantic import Field, BaseModel

from template.crud import CRUDClient
from template.crud.controller import SearchModel, SearchItemIn, JoinModel
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

    # The CRUDClient even smoothly handles 429's!
    for _ in range(8):  # Ratelimit is 5/sec
        await client.get_all_records_as_list()

    # Create an alert, mark it as seen and then delete it
    alert = await client.create_record(
        NewAlertModel(target=1, message="Hello World!", level=AlertLevels.INFO)
    )
    await client.patch_record(
        alert.uuid, AlertPatchModel(has_been_shown=True, was_shown_at=utc_now())
    )
    await client.delete_record(alert.uuid)

    # Create some alerts, iterate over them and refetch some
    await client.create_record(
        NewAlertModel(target=1, message="Hello World!", level=AlertLevels.INFO)
    )
    alert_1 = await client.create_record(
        NewAlertModel(target=1, message="Oh no", level=AlertLevels.WARNING)
    )
    await client.patch_record(
        alert_1.uuid, AlertPatchModel(was_shown_at=utc_now(), has_been_shown=True)
    )
    # Oops, undo that
    await client.patch_record(
        alert_1.uuid, AlertPatchModel(has_been_shown=False, was_shown_at=None)
    )
    alert_2 = await client.create_record(
        NewAlertModel(target=1, message="Not good!", level=AlertLevels.ERROR)
    )
    await client.patch_record(
        alert_2.uuid, AlertPatchModel(was_shown_at=utc_now(), has_been_shown=True)
    )
    total_records = await client.get_total_record_count()
    print(f"We currently have {total_records.total_records} alerts!")

    have_been_seen = 0
    async for group in client.get_all_records():
        for row in group:
            if row.has_been_shown:
                have_been_seen += 1

            await client.delete_record(row.uuid)

    print(
        f"Only {have_been_seen} alerts have been shown though!"
        f"\n\tP.s. I deleted all alerts mwaha!"
    )

    # --- No alerts exist at this stagee ---
    await client.create_record(
        NewAlertModel(target=1, message="Not good!", level=AlertLevels.WARNING)
    )
    await client.create_record(
        NewAlertModel(target=1, message="Its fine", level=AlertLevels.ERROR)
    )
    await client.create_record(
        NewAlertModel(target=1, message="Hello World", level=AlertLevels.INFO)
    )
    await client.create_record(
        NewAlertModel(target=2, message="Nice!", level=AlertLevels.SUCCESS)
    )

    available_filters = await client.get_search_filters()
    print("Search options", available_filters.filters)

    r_1 = await client.search_records_as_list(
        SearchModel(
            filters=[
                SearchItemIn(
                    column_name="target",
                    operation="equals",
                    search_value="1",
                ),
            ]
        )
    )
    print(f"Found {len(r_1)} alerts where the target had the id 1!")
    r_2 = await client.search_records_as_list(
        SearchModel(
            filters=[
                SearchItemIn(
                    column_name="message",
                    operation="starts_with",
                    search_value="Hello",
                ),
                SearchItemIn(
                    column_name="target",
                    operation="equals",
                    search_value="1",
                ),
            ]
        )
    )
    print(
        f"Found {len(r_2)} alerts where the message starts with 'Hello' and is targeting user 1"
    )
    r_3 = await client.search_records_as_list(
        SearchModel(
            filters=[
                JoinModel(
                    operand="or",
                    filters=[
                        SearchItemIn(
                            column_name="level",
                            operation="equals",
                            search_value="success",
                        ),
                        SearchItemIn(
                            column_name="target",
                            operation="equals",
                            search_value="1",
                        ),
                    ],
                ),
            ]
        )
    )
    print(f"Found {len(r_3)} alerts with complex query")


if __name__ == "__main__":
    asyncio.run(main())
