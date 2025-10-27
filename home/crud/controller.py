from __future__ import annotations

import base64
import dataclasses
from typing import Any, TypeVar, Generic, Annotated, Mapping

from litestar import Controller, Request
from litestar.openapi import ResponseSpec
from litestar.openapi.spec import Example
from litestar.params import Parameter
from piccolo.columns import Column, ForeignKey
from piccolo.query import Objects, Count
from piccolo.table import Table
from pydantic import BaseModel, Field

from home.exception_handlers import APIRedirectForAuth

TableT = TypeVar("TableT")
ModelOutT = TypeVar("ModelOutT", bound=BaseModel)
ModelInT = TypeVar("ModelInT", bound=BaseModel)
ModelInPatchT = TypeVar("ModelInPatchT", bound=BaseModel)
QueryT = TypeVar("QueryT", Objects, Count)

CRUD_BASE_OPENAPI_RESPONSES: Mapping[int, ResponseSpec] = {
    401: ResponseSpec(
        data_container=APIRedirectForAuth,
        description="You are not authenticated",
        examples=[
            Example(
                value=APIRedirectForAuth(
                    redirect_uri="https://example.com/auth/sign_in",
                    status_code=401,
                    message=(
                        "You are attempting to access an authenticated "
                        "resource without providing authentication."
                    ),
                ).model_dump_json(),
            )
        ],
    )
}


class GetAllResponseModel(BaseModel, Generic[TableT]):
    data: list[TableT] = Field(description="A list of the data fetched")
    next_cursor: str | None = Field(
        default=None,
        description="The cursor to fetch the next page. Null if no more data",
    )


class GetCountResponseModel(BaseModel):
    total_records: int = Field(
        description="The total number of records available to the current requester"
    )


@dataclasses.dataclass
class CRUDMeta:
    BASE_CLASS: type[Table]
    """The table to make queries against"""
    BASE_CLASS_PK: Column
    """The primary key to be used for filtering against"""
    BASE_CLASS_CURSOR_COL: Column
    """The column to build cursors from"""
    BASE_CLASS_ORDER_BY: Column
    """The column to order queries by. Usually .id works here"""
    DTO_OUT: type[BaseModel]
    """Model for an outgoing row"""
    PREFETCH_COLUMNS: list[ForeignKey] = dataclasses.field(default_factory=list)
    """A list of columns to always pre-fetch"""


# noinspection PyMethodMayBeStatic
class CRUDController(Controller, Generic[ModelOutT]):
    """A CRUD base controller to inherit.

    No routes are exposed by default and
    users are expected to `super()` call
    every route as well as registering routes.
    This has the positive side effect of easy
    guards / middleware + correct openapi docs.

    Pagination is based on cursor pagination:
        https://slack.engineering/evolving-api-pagination-at-slack/
    """

    tags = ["CRUD"]
    opt = {"is_api_route": True}
    META: CRUDMeta

    def _encode_cursor(self, value: Any) -> str | None:
        if value is None:
            return None

        return base64.urlsafe_b64encode(str(value).encode("ascii")).decode("ascii")

    def _decode_cursor(self, value: str | None) -> Any:
        if value is None:
            return None

        return self._value_to_cursor_value(
            base64.urlsafe_b64decode(value.encode("ascii"))
        )

    def _value_to_cursor_value(self, value: Any) -> Any:
        return self.META.BASE_CLASS_CURSOR_COL.value_type(value)

    def _value_to_pk_value(self, value: Any) -> Any:
        """Turns a value into the correct type for the primary key"""
        return self.META.BASE_CLASS_PK.value_type(value)

    def _transform_row_to_output(self, row: Table) -> ModelOutT:
        return self.META.DTO_OUT(**row.to_dict())

    async def add_custom_where(self, request: Request, query: QueryT) -> QueryT:
        """Override this method to add custom clauses
        to all queries issue by this controller.
        """
        return query

    async def get_record_count(self, request: Request) -> GetCountResponseModel:
        # TODO Support distinct and allowing the user to provide
        #   the column to filter based on
        base_query = self.META.BASE_CLASS.count()
        base_query = await self.add_custom_where(request, base_query)
        result = await base_query.run()
        return GetCountResponseModel(total_records=result)

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
    ) -> GetAllResponseModel[TableT]:
        """Fetch all records from this table."""
        base_query = (
            self.META.BASE_CLASS.objects(*self.META.PREFETCH_COLUMNS)
            .limit(page_size + 1)
            .order_by(self.META.BASE_CLASS_ORDER_BY)
        )
        base_query = await self.add_custom_where(request, base_query)
        next_cursor = self._decode_cursor(next_cursor)
        if next_cursor is not None:
            base_query = base_query.where(self.META.BASE_CLASS_PK >= next_cursor)

        rows: list[TableT] = await base_query.run()
        next_cursor = None
        if len(rows) > page_size:
            final_row = rows.pop(-1)
            # noinspection PyProtectedMember
            next_cursor = getattr(
                final_row,
                self.META.BASE_CLASS_CURSOR_COL._meta.name,  # type: ignore
            )

        return GetAllResponseModel(
            data=[self._transform_row_to_output(row) for row in rows],
            next_cursor=self._encode_cursor(next_cursor),
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
    ) -> ModelOutT:
        primary_key = self._value_to_pk_value(primary_key)
        base_query = (
            self.META.BASE_CLASS.objects(*self.META.PREFETCH_COLUMNS)
            .where(self.META.BASE_CLASS_PK == primary_key)
            .first()
        )
        base_query = await self.add_custom_where(
            request,
            base_query,  # type: ignore
        )
        row: CRUDMeta.BASE_CLASS = await base_query.run()
        return self.META.DTO_OUT(**row.to_dict())

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
    ):
        primary_key = self._value_to_pk_value(primary_key)
        base_query = self.META.BASE_CLASS.delete().where(
            self.META.BASE_CLASS_PK == primary_key
        )
        base_query = await self.add_custom_where(
            request,
            base_query,  # type: ignore
        )
        await base_query.run()
        return None

    async def get_csrf_token(self, request: Request) -> None:
        # Purely exists so API clients can get a CSRF token
        # without running a DB query at the same time
        return None

    async def create_object(self, request: Request, data: ModelInT) -> ModelOutT:
        object_cls = self.META.BASE_CLASS(**data.model_dump())
        await object_cls.save()

        # Ensure the response actually has the foreignkey objects
        for col in self.META.PREFETCH_COLUMNS:
            item = await object_cls.get_related(col)
            setattr(object_cls, col._meta.name, item)

        return self.META.DTO_OUT(**object_cls.to_dict())

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
        data: dict[str, Any],
    ) -> ModelOutT:
        primary_key = self._value_to_pk_value(primary_key)
        base_query = (
            self.META.BASE_CLASS.objects(*self.META.PREFETCH_COLUMNS)
            .where(self.META.BASE_CLASS_PK == primary_key)
            .first()
        )
        base_query = await self.add_custom_where(
            request,
            base_query,  # type: ignore
        )
        row: CRUDMeta.BASE_CLASS = await base_query.run()
        await row.update_self(data)
        return self.META.DTO_OUT(**row.to_dict())
