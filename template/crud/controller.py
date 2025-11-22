from __future__ import annotations

import ast
import base64
import dataclasses
from typing import Any, TypeVar, Generic, Annotated, Mapping, Literal

from litestar import Controller, Request
from litestar.exceptions import ValidationException
from litestar.openapi import ResponseSpec
from litestar.openapi.spec import Example
from litestar.params import Parameter
from piccolo.columns import Column, ForeignKey, And, Or, Where
from piccolo.columns.operators import IsNull, IsNotNull, Equal, NotEqual
from piccolo.columns.operators.comparison import (
    ComparisonOperator,
    GreaterThan,
    LessThan,
    GreaterEqualThan,
    LessEqualThan,
    ILike,
    NotLike,
)
from piccolo.query import Objects, Count
from piccolo.table import Table
from pydantic import BaseModel, Field, ConfigDict
from typeguard import check_type, TypeCheckError

from template.exception_handlers import APIRedirectForAuth

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


class SearchItemInNulls(BaseModel):
    column_name: str = Field(description="The name of the column")
    operation: Literal["is_null", "is_not_null"] = Field(
        description="The operation to filter by"
    )


class SearchItemIn(SearchItemInNulls):
    column_name: str = Field(description="The name of the column")
    operation: str = Field(description="The operation to filter by")
    search_value: Any = Field(description="The value used in the filter operation")


class JoinModel(BaseModel):
    operand: Literal["and", "or"] = Field(
        description="Can be used for complex filterings. If JoinModel is not used, "
        "all filters are an implicit AND. Max nesting of 5."
    )
    filters: list[SearchItemIn | SearchItemInNulls | JoinModel]


class SearchModel(BaseModel):
    filters: list[SearchItemIn | SearchItemInNulls | JoinModel]


class RawSearchOption(BaseModel):
    column_name: str = Field(description="The name of the column")
    expected_type: Any = Field(description="Python type input must validate against")
    supported_filters: list[str] = Field(
        description="The operations supported for this column"
    )


class SearchTableModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    column: Column
    column_name: str = Field(description="How users will reference this table")
    expected_value_type: type[Any] = Field(
        description="Python type input must validate against"
    )


class SearchableColumn(BaseModel):
    columns: list[SearchTableModel] = Field(
        description="Columns to apply this search config to"
    )
    # All opposites are derived from these
    #   i.e. if supports_equals is True then supports_not_equals is also True
    supports_is_null: bool = Field(
        default=False, description="is column null or not null"
    )
    supports_equals: bool = Field(default=False, description="== check as well as !=")
    supports_greater_than: bool = Field(default=False, description="> check")
    supports_greater_than_equal: bool = Field(default=False, description=">= check")
    supports_less_than: bool = Field(default=False, description="< check")
    supports_less_than_equal: bool = Field(default=False, description="<= check")
    supports_starts_with: bool = Field(
        default=False,
        description="Does column start with value as well as not start with",
    )
    supports_ends_with: bool = Field(
        default=False, description="Does column end with value as well as not end with"
    )
    supports_contains: bool = Field(
        default=False, description="Does column contain value as well as not contains"
    )


class SearchRequestModel(BaseModel):
    filters: list[RawSearchOption]
    # column_configuration: list[SearchableColumn]


class SearchAddons:
    operators: dict[str, ComparisonOperator] = {
        "is_null": IsNull,
        "is_not_null": IsNotNull,
        "equals": Equal,
        "not_equals": NotEqual,
        "greater_than": GreaterThan,
        "less_than": LessThan,
        "greater_than_equal": GreaterEqualThan,
        "less_than_equal": LessEqualThan,
        "starts_with": ILike,
        "not_starts_with": NotLike,
        "ends_with": ILike,
        "not_ends_with": NotLike,
        "contains": ILike,
        "not_contains": NotLike,
    }

    @classmethod
    def _searchable_column_to_operands(cls, sc: SearchableColumn) -> list[str]:
        data = []
        if sc.supports_is_null:
            data.append("is_null")
            data.append("is_not_null")

        if sc.supports_equals:
            data.append("equals")
            data.append("not_equals")

        if sc.supports_greater_than:
            data.append("greater_than")
        if sc.supports_less_than:
            data.append("less_than")
        if sc.supports_greater_than_equal:
            data.append("greater_than_equal")
        if sc.supports_less_than_equal:
            data.append("less_than_equal")

        if sc.supports_starts_with:
            data.append("starts_with")
            data.append("not_starts_with")

        if sc.supports_ends_with:
            data.append("ends_with")
            data.append("not_ends_with")

        if sc.supports_contains:
            data.append("contains")
            data.append("not_contains")

        return data

    @classmethod
    async def get_available_search_filters(
        cls,
        available_filters: list[SearchableColumn],
        *,
        return_raw_types: bool = False,
    ) -> SearchRequestModel:
        out_filters: list[RawSearchOption] = []
        for sc in available_filters:
            operations = cls._searchable_column_to_operands(sc)
            for col in sc.columns:
                out_filters.append(
                    RawSearchOption(
                        column_name=col.column_name,
                        expected_type=(
                            col.expected_value_type
                            if return_raw_types
                            else col.expected_value_type.__name__
                        ),
                        supported_filters=operations,
                    )
                )

        return SearchRequestModel(
            filters=out_filters,
            # column_configuration=self.META.AVAILABLE_FILTERS,
        )

    @classmethod
    async def validate_search_input_filters(
        cls,
        search_filters: (
            list[SearchItemIn | SearchItemInNulls | JoinModel] | SearchModel
        ),
        available_filters: list[SearchableColumn],
        *,
        issues: list[str] | None = None,
        raw_supported_operations=None,
        depth: int = 1,
    ):
        depth += 1
        if depth == 5:
            raise ValidationException(
                "Your nesting is too big, refusing to honour this filter request."
            )

        if raw_supported_operations is None:
            raw_supported_operations = await cls.get_available_search_filters(
                available_filters, return_raw_types=True
            )

        supported_operations: dict[str, tuple[Any, list[str]]] = {}
        for item in raw_supported_operations.filters:
            supported_operations[item.column_name] = (
                item.expected_type,
                item.supported_filters,
            )

        if isinstance(search_filters, SearchModel):
            search_filters = search_filters.filters

        if issues is None:
            issues: list[str] = []

        for entry in search_filters:
            if isinstance(entry, JoinModel):
                if entry.operand not in ["and", "or"]:
                    issues.append(
                        f"Value {repr(entry.operand)} is not a supported join operand."
                    )

                if len(entry.filters) != 2:
                    issues.append(f"Join {repr(entry.operand)} requires two parameters")

                await cls.validate_search_input_filters(
                    entry.filters,
                    available_filters,
                    issues=issues,
                    depth=depth,
                    raw_supported_operations=raw_supported_operations,
                )
                continue

            if entry.column_name not in supported_operations:
                issues.append(f"Column {repr(entry.column_name)} not supported")
                continue

            if entry.operation not in supported_operations[entry.column_name][1]:
                issues.append(
                    f"Operation {repr(entry.operation)} not supported on column {repr(entry.column_name)}"
                )
                continue

            try:
                check_type(
                    entry.search_value, supported_operations[entry.column_name][0]
                )
            except TypeCheckError as e:
                issues.append(
                    f"Value {repr(entry.search_value)} not a supported type for column {repr(entry.column_name)}. "
                    f"Expected {repr(supported_operations[entry.column_name][0].__name__)}, got {repr(str(e))}"
                )
                continue

        return (
            None
            if not issues
            else {
                "detail": "Your submission had issues",
                "status_code": 400,
                "extra": {"errors": issues},
            }
        )

    @classmethod
    async def apply_filters_to_query(
        cls,
        query: QueryT,
        search_filters: SearchModel,
        available_filters: list[SearchableColumn],
    ) -> QueryT:
        lookups: dict[str, tuple[Column, Any]] = {}
        for sc in available_filters:
            for col in sc.columns:
                lookups[col.column_name] = (col.column, col.expected_value_type)

        await cls.validate_search_input_filters(search_filters, available_filters)
        return query.where(*cls._get_conditions(search_filters.filters, lookups))

    @classmethod
    def _get_conditions(
        cls,
        search_filters: (
            list[SearchItemIn | SearchItemInNulls | JoinModel] | SearchModel
        ),
        lookups: dict[str, tuple[Column, Any]],
    ) -> list[And | Or | Where]:
        output: list[And | Or | Where] = []
        for entry in search_filters:
            if isinstance(entry, JoinModel):
                wrapper = Or if entry.operand == "or" else And
                output.append(wrapper(*cls._get_conditions(entry.filters, lookups)))
                continue

            wrapper = lookups[entry.column_name][1]
            if entry.operation in ("starts_with", "not_starts_with"):
                search_value = f"{entry.search_value}%"
            elif entry.operation in ("ends_with", "not_ends_with"):
                search_value = f"%{entry.search_value}"
            elif entry.operation in ("contains", "not_contains"):
                search_value = f"%{entry.search_value}%"
            else:
                search_value = wrapper(entry.search_value)

            output.append(
                Where(
                    lookups[entry.column_name][0],
                    search_value,
                    operator=cls.operators[entry.operation],
                )
            )

        return output


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
    AVAILABLE_FILTERS: list[SearchableColumn] = dataclasses.field(default_factory=list)
    """A list of columns that can be filtered by for what operations"""


def get_user_ratelimit_key(request: Request[Any, Any, Any]) -> str:
    """Get a cache-key from an authenticated ``Request``

    Notes
    -----
    This falls back to a global key if the request is not authenticated.

    You may wish to change this to fall back to IP instead
    """
    return f"user-{request.user.id}" if request.user else "global"


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

    async def _apply_filters_to_query(
        self,
        query: QueryT,
        search_filters: SearchModel,
    ) -> QueryT:
        return await SearchAddons.apply_filters_to_query(
            query, search_filters, available_filters=self.META.AVAILABLE_FILTERS
        )

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

    async def get_available_search_filters(
        self, request: Request
    ) -> SearchRequestModel:
        return await SearchAddons.get_available_search_filters(
            self.META.AVAILABLE_FILTERS
        )

    async def search(
        self,
        request: Request,
        search_filters: SearchModel,
        page_size: int = Parameter(
            query="_page_size",
            default=500,
            required=False,
            le=500,
            ge=1,
        ),
        next_cursor: str | None = Parameter(query="_next_cursor", required=False),
    ) -> GetAllResponseModel[TableT]:
        base_query = (
            self.META.BASE_CLASS.objects(*self.META.PREFETCH_COLUMNS)
            .limit(page_size + 1)
            .order_by(self.META.BASE_CLASS_ORDER_BY)
        )

        await self._apply_filters_to_query(base_query, search_filters)

        base_query = await self.add_custom_where(request, base_query)
        next_cursor = self._decode_cursor(next_cursor)
        if next_cursor is not None:
            base_query = base_query.where(self.META.BASE_CLASS_PK >= next_cursor)

        print(base_query)
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
