from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
from copy import deepcopy
from functools import reduce
from typing import Any, TypeVar, Generic, Annotated, Mapping, Literal, Final

import commons
import orjson
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
from piccolo.query import Objects, Count, OrderByRaw
from piccolo.table import Table
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    model_validator,
    create_model,
    ValidationError,
)

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
                dynamic_model = create_model(
                    "TestCastModel", test=supported_operations[entry.column_name][0]
                )
                dynamic_model(test=entry.search_value)
            except ValidationError:
                issues.append(
                    f"Value {repr(entry.search_value)} not a supported type for column {repr(entry.column_name)}, "
                    f"expected {repr(supported_operations[entry.column_name][0].__name__)}."
                )
                continue

        if issues:
            raise ValidationException(issues)

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
            elif wrapper is bool:
                search_value = commons.value_to_bool(entry.search_value)
            else:
                # Safer then an eval
                dynamic_model = create_model("TestCastModel", search_value=wrapper)
                search_value = dynamic_model(
                    search_value=entry.search_value
                ).search_value  # noqa

            output.append(
                Where(
                    lookups[entry.column_name][0],
                    search_value,
                    operator=cls.operators[entry.operation],
                )
            )

        return output


class OrderBy(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    column: Column
    column_name: str
    length_function: Literal["length", "array_length"] = Field(
        default="length", description="The SQL function to use when computing length"
    )


class OrderByFilters(BaseModel):
    column_name: str = Field(description="The column to order by")
    order: Literal["ascending", "descending"] = Field(
        default="ascending", description="The order to apply for this column"
    )
    order_by_length: bool = Field(
        default=False,
        description="If set to true, becomes 'ORDER BY LENGTH(Column)' instead of 'ORDER BY Column'",
    )


class OrderByRequestModel(BaseModel):
    fields: list[OrderByFilters]

    @model_validator(mode="before")
    @classmethod
    def cast_to_expected(cls, data: Any) -> Any:
        if data is None or data and isinstance(data, dict):
            return data

        return orjson.loads(data)


@dataclasses.dataclass
class CRUDMeta:
    BASE_CLASS: type[Table]
    """The table to make queries against"""
    BASE_CLASS_PK: Column
    """The primary key to be used for filtering against"""
    BASE_CLASS_CURSOR_COL: Column
    """The column to build cursors from"""
    FOREIGN_KEY_CURSOR_COLS: dict[Table, Column]
    """The column to build cursors from when finding a foreign key"""
    BASE_CLASS_ORDER_BY: Column
    """The column to order queries by. Usually .id works here"""
    DTO_OUT: type[BaseModel]
    """Model for an outgoing row"""
    PREFETCH_COLUMNS: list[ForeignKey] = dataclasses.field(default_factory=list)
    """A list of columns to always pre-fetch"""
    AVAILABLE_FILTERS: list[SearchableColumn] = dataclasses.field(default_factory=list)
    """A list of columns that can be filtered by for what operations"""
    AVAILABLE_ORDER_BY_OPTIONS: list[OrderBy] = dataclasses.field(default_factory=list)
    """Ways end users can order results. All columns must NOT be nullable or results will be missing."""


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
    CURSOR_SEP: Final[str] = "¦"
    CURSOR_SENTINEL: Final[str] = "😞"

    def _build_order_matches(self) -> dict[str, OrderBy]:
        return {o.column_name: o for o in self.META.AVAILABLE_ORDER_BY_OPTIONS}

    def _get_cursor_order_hash(self, order_by: OrderByRequestModel | None) -> str:
        if order_by is None:
            return "null"

        return hashlib.sha256(
            orjson.dumps(order_by.model_dump_json())
        ).hexdigest()  # [:7]

    def _build_cursor(self, value: Any, order_by: OrderByRequestModel | None) -> str:
        return f"{value}{self.CURSOR_SEP}{self._get_cursor_order_hash(order_by)}"

    def _encode_cursor(
        self, value: Any, order_by: OrderByRequestModel | None, extras: list[str]
    ) -> str | None:
        if value is None:
            return None

        cursor = self._build_cursor(value, order_by)
        if extras:
            cursor = f"{cursor}{self.CURSOR_SEP}{self.CURSOR_SEP.join(extras)}"

        return base64.urlsafe_b64encode(cursor.encode("utf-8")).decode("utf-8")

    def _decode_cursor(
        self, value: str | None, order_by: OrderByRequestModel | None
    ) -> tuple[Any, list[tuple[Column, Any]]]:
        if value is None or not value:
            return None, []

        out = (
            base64.urlsafe_b64decode(value.encode("utf-8"))
            .decode("utf-8")
            .split(self.CURSOR_SEP)
        )
        if len(out) < 2:
            raise ValidationException(
                "Next cursor is malformed, try not modifying it next time."
            )

        cursor_raw = out.pop(0)
        order_by_raw = out.pop(0)
        # Anything left should be turned into where clauses

        if not hmac.compare_digest(self._get_cursor_order_hash(order_by), order_by_raw):
            raise ValidationException(
                "The ordering has changed between calls. "
                "Please ensure your order stays consistent across pagination."
            )

        extra: list[tuple[Column, Any]] = []
        if out:
            matches = self._build_order_matches()
            for item in out:
                col, val = item.split(",", maxsplit=1)
                if col not in matches:
                    raise ValidationException("Next cursor is malformed")

                column = matches[col].column
                extra.append((column, self._value_to_cursor_value(val, column=column)))

        return self._value_to_cursor_value(cursor_raw), extra

    def _value_to_cursor_value(self, value: Any, *, column: Column = None) -> Any:
        if column is None:
            column = self.META.BASE_CLASS_CURSOR_COL

        if value == self.CURSOR_SENTINEL:
            # It's a sentinel value anywho
            return None

        if column._meta.null:
            out_type = column.value_type | None
        else:
            out_type = column.value_type

        dynamic_model = create_model("TestCastModel", test=out_type)
        return dynamic_model(test=value).test

    def _value_to_pk_value(self, value: Any) -> Any:
        """Turns a value into the correct type for the primary key"""
        return self.META.BASE_CLASS_PK.value_type(value)

    def _transform_row_to_output(self, row: Table) -> ModelOutT:
        return self.META.DTO_OUT(**row.to_dict())

    async def build_base_query(
        self,
        request: Request,
        *,
        page_size: int,
        next_cursor: str | None,
        order_by: OrderByRequestModel | None,
    ) -> QueryT:
        base_query = self.META.BASE_CLASS.objects(*self.META.PREFETCH_COLUMNS).limit(
            page_size + 1
        )
        base_query = await self.add_custom_where(request, base_query)
        if order_by is None:
            base_query = base_query.order_by(self.META.BASE_CLASS_ORDER_BY)
        else:
            base_query = await self.apply_custom_ordering(request, base_query, order_by)

        next_cursor, extras = self._decode_cursor(next_cursor, order_by)
        if next_cursor is not None:
            if order_by is None:
                base_query = base_query.where(
                    self.META.BASE_CLASS_CURSOR_COL >= next_cursor
                )

            else:
                # Cursor based pagination with custom order
                # means we also need wheres for order_bny items
                # https://medium.com/@george_16060/cursor-based-pagination-with-arbitrary-ordering-b4af6d5e22db
                possible_and_clauses: list[And | Where] = []
                equalities: list[Where] = []
                for col, val in extras:
                    if not equalities:
                        # First one, don't use AND's
                        possible_and_clauses.append(
                            Where(col, val, operator=GreaterThan)
                        )
                        equalities.append(Where(col, val, operator=Equal))
                        continue

                    possible_and_clauses.append(
                        And(
                            Where(col, val, operator=GreaterThan),
                            reduce(
                                lambda acc, x: And(acc, x),
                                equalities[1:],
                                equalities[0],
                            ),
                        )
                    )
                    equalities.append(Where(col, val, operator=Equal))

                possible_and_clauses.append(
                    And(
                        Where(
                            self.META.BASE_CLASS_CURSOR_COL,
                            next_cursor,
                            operator=GreaterEqualThan,
                        ),
                        reduce(
                            lambda acc, x: And(acc, x), equalities[1:], equalities[0]
                        ),
                    )
                )
                base_query = base_query.where(
                    reduce(
                        lambda acc, x: Or(acc, x),
                        possible_and_clauses[1:],
                        possible_and_clauses[0],
                    )
                )
                print(base_query)
                print(1)
                # base_query = base_query.where(
                #     And(self.META.BASE_CLASS_CURSOR_COL >= next_cursor)
                # )
                # for column, value in extras:
                #     base_query = base_query.where()

        return base_query

    async def _apply_filters_to_query(
        self,
        query: QueryT,
        search_filters: SearchModel,
    ) -> QueryT:
        return await SearchAddons.apply_filters_to_query(
            query, search_filters, available_filters=self.META.AVAILABLE_FILTERS
        )

    def _build_order_by_extras(
        self, final_row, order_by: OrderByRequestModel
    ) -> list[str]:
        extras = []
        # We can assume the object has already been validated
        match: dict[str, OrderBy] = self._build_order_matches()
        for field in order_by.fields:
            value = getattr(
                final_row,
                match[field.column_name].column._meta.name,  # type: ignore
            )
            if value is None:
                value = self.CURSOR_SENTINEL

            elif type(value) in self.META.FOREIGN_KEY_CURSOR_COLS:
                # Likely a foreign key
                value = getattr(
                    value,
                    self.META.FOREIGN_KEY_CURSOR_COLS[type(value)]._meta.name,
                )

            extras.append(f"{field.column_name},{value}")

        return extras

    async def get_available_order_by(self, request: Request) -> OrderByRequestModel:
        out_filters: list[OrderByFilters] = []
        for ob in self.META.AVAILABLE_ORDER_BY_OPTIONS:
            out_filters.append(OrderByFilters(column_name=ob.column_name))

        return OrderByRequestModel(
            fields=out_filters,
        )

    async def add_custom_where(self, request: Request, query: QueryT) -> QueryT:
        """Override this method to add custom clauses
        to all queries issue by this controller.
        """
        return query

    async def apply_custom_ordering(
        self, request: Request, query: QueryT, order_by: OrderByRequestModel | None
    ) -> QueryT:
        if order_by is None:
            return query

        issues: list[str] = []
        match: dict[str, OrderBy] = self._build_order_matches()
        for operand in order_by.fields:
            if operand.column_name not in match:
                issues.append(
                    f"Column {repr(operand.column_name)} is not available to order by"
                )
                continue

            model = match[operand.column_name]
            if not operand.order_by_length:
                query = query.order_by(
                    model.column, ascending=operand.order == "ascending"
                )
                continue

            # Piccolo doesnt have a Length() flag so do manually
            order = "ASC" if operand.order == "ascending" else "DESC"
            col_name = model.column._meta.get_full_name(with_alias=False)
            query = query.order_by(
                OrderByRaw(f"{model.length_function}({col_name}) {order}")
            )

        if issues:
            raise ValidationException(issues)

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
        order_by: OrderByRequestModel | None = Parameter(
            query="order_by", required=False
        ),
    ) -> GetAllResponseModel[TableT]:
        """Fetch all records from this table."""
        base_query = await self.build_base_query(
            request,
            page_size=page_size,
            next_cursor=next_cursor,
            order_by=order_by,
        )

        rows: list[TableT] = await base_query.run()
        extras = []
        next_cursor = None
        if len(rows) > page_size:
            final_row = rows.pop(-1)
            # noinspection PyProtectedMember
            next_cursor = getattr(
                final_row,
                self.META.BASE_CLASS_CURSOR_COL._meta.name,  # type: ignore
            )
            if order_by is not None:
                extras = self._build_order_by_extras(final_row, order_by)

        return GetAllResponseModel(
            data=[self._transform_row_to_output(row) for row in rows],
            next_cursor=self._encode_cursor(next_cursor, order_by, extras),
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
        order_by: OrderByRequestModel | None = Parameter(
            query="order_by", required=False
        ),
    ) -> GetAllResponseModel[TableT]:
        base_query = await self.build_base_query(
            request,
            page_size=page_size,
            next_cursor=next_cursor,
            order_by=order_by,
        )
        await self._apply_filters_to_query(base_query, search_filters)

        rows: list[TableT] = await base_query.run()
        extras = []
        next_cursor = None
        if len(rows) > page_size:
            final_row = rows.pop(-1)
            # noinspection PyProtectedMember
            next_cursor = getattr(
                final_row,
                self.META.BASE_CLASS_CURSOR_COL._meta.name,  # type: ignore
            )
            if order_by is not None:
                extras = self._build_order_by_extras(final_row, order_by)

        return GetAllResponseModel(
            data=[self._transform_row_to_output(row) for row in rows],
            next_cursor=self._encode_cursor(next_cursor, order_by, extras),
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
