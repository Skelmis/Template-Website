import datetime
from typing import Annotated, Any
from uuid import UUID

from litestar import patch, Request, post, get, delete
from litestar.params import Parameter
from pydantic import BaseModel, Field

from home.crud.controller import (
    CRUDController,
    GetAllResponseModel,
    CRUDMeta,
    GetCountResponseModel,
    CRUD_BASE_OPENAPI_RESPONSES,
)
from home.middleware.ensure_auth import EnsureAdmin
from home.tables import Alerts, AlertLevels


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
    has_been_shown: bool = Field(
        default=None, description="Has the user seen this yet?"
    )
    was_shown_at: datetime.datetime | None = Field(
        default=None, description="The time the user was shown the alert"
    )


crud_meta = CRUDMeta(
    BASE_CLASS=Alerts,
    BASE_CLASS_PK=Alerts.uuid,
    BASE_CLASS_CURSOR_COL=Alerts.id,
    BASE_CLASS_ORDER_BY=Alerts.id,
    DTO_OUT=AlertOutModel,
    PREFETCH_COLUMNS=[Alerts.target],
)


class APIAlertController[AlertOutModel](CRUDController):
    path = "/api/alerts"
    tags = ["Alerts"]
    META = crud_meta
    middleware = [EnsureAdmin]
    security = [{"adminSession": []}]

    @get(
        "/",
        responses=CRUD_BASE_OPENAPI_RESPONSES,
    )
    async def get_all_records(
        self,
        request: Request,
        page_size: int = Parameter(
            query="_page_size",
            default=500,
            required=False,
            le=500,
            ge=1,
        ),
        next_cursor: str | None = Parameter(query="_next_cursor", required=False),
    ) -> GetAllResponseModel[AlertOutModel]:
        return await super().get_all_records(
            request, page_size=page_size, next_cursor=next_cursor
        )

    @get(
        "/{primary_key:str}",
        responses=CRUD_BASE_OPENAPI_RESPONSES,
    )
    async def get_object(
        self,
        request: Request,
        primary_key: Annotated[
            Any,
            Parameter(
                title="Object ID",
                description="The ID of the object you wish to retrieve",
            ),
        ],
    ) -> AlertOutModel:
        return await super().get_object(request, primary_key)

    @delete(
        "/{primary_key:str}",
        responses=CRUD_BASE_OPENAPI_RESPONSES,
    )
    async def delete_object(
        self,
        request: Request,
        primary_key: Annotated[
            Any,
            Parameter(
                title="Object ID",
                description="The ID of the object you wish to delete",
            ),
        ],
    ) -> None:
        return await super().delete_object(request, primary_key)

    @get(
        "/meta/count",
        responses=CRUD_BASE_OPENAPI_RESPONSES,
    )
    async def get_record_count(self, request: Request) -> GetCountResponseModel:
        return await super().get_record_count(request)

    @get("/meta/csrf", include_in_schema=False)
    async def get_csrf_token(self, request: Request) -> None:
        return None

    @post(
        "/",
        responses=CRUD_BASE_OPENAPI_RESPONSES,
        status_code=201,
    )
    async def create_object(
        self, request: Request, data: NewAlertModel
    ) -> AlertOutModel:
        return await super().create_object(request, data)

    @patch(
        "/{primary_key:str}",
        responses=CRUD_BASE_OPENAPI_RESPONSES,
    )
    async def patch_object(
        self,
        request: Request,
        primary_key: Annotated[
            Any,
            Parameter(
                title="Object ID",
                description="The ID of the object you wish to delete",
            ),
        ],
        data: AlertPatchModel,
    ) -> AlertOutModel:
        return await super().patch_object(
            request,
            primary_key,
            data.model_dump(exclude_unset=True),
            # data.model_dump(exclude_unset=True, exclude_none=True),
        )
