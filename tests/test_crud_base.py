from typing import Self, Any
from unittest.mock import AsyncMock

from piccolo.columns import Column

from template.controllers.api import APIAlertController
from template.crud.controller import (
    SearchModel,
    SearchItemIn,
    SearchAddons,
    SearchableColumn,
    SearchTableModel,
    JoinModel,
)
from template.tables import Alerts


class Given:
    data: dict[str, Any] = {}

    @classmethod
    def default_searchable_columns(cls) -> Self:
        af = [
            SearchableColumn(
                columns=[
                    SearchTableModel(
                        column=Alerts.target,
                        column_name="target",
                        expected_value_type=int,
                    ),
                    SearchTableModel(
                        column=Alerts.level,
                        column_name="level",
                        expected_value_type=str,
                    ),
                    SearchTableModel(
                        column=Alerts.has_been_shown,
                        column_name="has_been_shown",
                        expected_value_type=bool,
                    ),
                ],
                supports_equals=True,
            ),
            SearchableColumn(
                columns=[
                    SearchTableModel(
                        column=Alerts.message,
                        column_name="message",
                        expected_value_type=str,
                    ),
                ],
                supports_equals=True,
                supports_contains=True,
                supports_starts_with=True,
                supports_ends_with=True,
            ),
        ]
        obj = cls()
        obj.data["sc"] = af
        return obj

    @classmethod
    def searchable_columns(cls, sc: list[SearchableColumn] | SearchableColumn):
        obj = cls()
        obj.data["sc"] = sc if isinstance(sc, list) else [sc]
        return obj

    @property
    def filters(self) -> list[SearchableColumn]:
        return self.data["sc"]

    @property
    def sc(self) -> Self:
        return self

    @property
    def lookups(self) -> dict[str, tuple[Column, Any]]:
        lookups: dict[str, tuple[Column, Any]] = {}
        for sc in self.data["sc"]:
            for col in sc.columns:
                lookups[col.column_name] = (col.column, col.expected_value_type)

        return lookups


# noinspection PyProtectedMember
async def test_validate_filters_on_bad_data():
    r_1 = await SearchAddons.validate_search_input_filters(
        SearchModel(
            filters=[
                SearchItemIn(
                    column_name="test", operation="equals", search_value="test"
                )
            ]
        ),
        Given.default_searchable_columns().filters,
    )
    assert r_1 == {
        "detail": "Your submission had issues",
        "status_code": 400,
        "extra": {"errors": ["Column 'test' not supported"]},
    }

    r_2 = await SearchAddons.validate_search_input_filters(
        SearchModel(
            filters=[
                SearchItemIn(
                    column_name="target", operation="less_then", search_value="test"
                )
            ]
        ),
        Given.default_searchable_columns().filters,
    )
    assert r_2 == {
        "detail": "Your submission had issues",
        "status_code": 400,
        "extra": {"errors": ["Operation 'less_then' not supported on column 'target'"]},
    }

    r_3 = await SearchAddons.validate_search_input_filters(
        SearchModel(
            filters=[
                SearchItemIn(
                    column_name="target", operation="equals", search_value="test"
                )
            ]
        ),
        Given.default_searchable_columns().filters,
    )
    assert r_3 == {
        "detail": "Your submission had issues",
        "status_code": 400,
        "extra": {
            "errors": [
                "Value 'test' not a supported type for column 'target'. "
                "Expected 'int', got 'str is not an instance of int'"
            ]
        },
    }

    r_4 = await SearchAddons.validate_search_input_filters(
        SearchModel(
            filters=[
                JoinModel.model_construct(
                    operand="test",
                    filters=[
                        SearchItemIn(
                            column_name="message",
                            operation="equals",
                            search_value="test",
                        ),
                        SearchItemIn(
                            column_name="message",
                            operation="equals",
                            search_value="test",
                        ),
                    ],
                ),
            ]
        ),
        Given.default_searchable_columns().filters,
    )
    assert r_4 == {
        "detail": "Your submission had issues",
        "status_code": 400,
        "extra": {"errors": ["Value 'test' is not a supported join operand."]},
    }

    r_5 = await SearchAddons.validate_search_input_filters(
        SearchModel(
            filters=[
                JoinModel.model_construct(
                    operand="and",
                    filters=[
                        SearchItemIn(
                            column_name="message",
                            operation="equals",
                            search_value="test",
                        ),
                    ],
                ),
            ]
        ),
        Given.default_searchable_columns().filters,
    )
    assert r_5 == {
        "detail": "Your submission had issues",
        "status_code": 400,
        "extra": {"errors": ["Join 'and' requires two parameters"]},
    }


async def test_filters_on_correct_data():
    af = [
        SearchableColumn(
            columns=[
                SearchTableModel(
                    column=Alerts.target,
                    column_name="target",
                    expected_value_type=int,
                ),
                SearchTableModel(
                    column=Alerts.level,
                    column_name="level",
                    expected_value_type=str,
                ),
                SearchTableModel(
                    column=Alerts.has_been_shown,
                    column_name="has_been_shown",
                    expected_value_type=bool,
                ),
            ],
            supports_equals=True,
        ),
        SearchableColumn(
            columns=[
                SearchTableModel(
                    column=Alerts.message,
                    column_name="message",
                    expected_value_type=str,
                ),
            ],
            supports_equals=True,
            supports_contains=True,
            supports_starts_with=True,
            supports_ends_with=True,
        ),
    ]
    r_1 = await SearchAddons.validate_search_input_filters(
        SearchModel(
            filters=[
                SearchItemIn(
                    column_name="message", operation="equals", search_value="test"
                )
            ]
        ),
        af,
    )
    assert r_1 is None

    r_2 = await SearchAddons.validate_search_input_filters(
        SearchModel(
            filters=[
                SearchItemIn(
                    column_name="message", operation="equals", search_value="test"
                ),
                JoinModel(
                    operand="and",
                    filters=[
                        SearchItemIn(
                            column_name="message",
                            operation="equals",
                            search_value="test",
                        ),
                        SearchItemIn(
                            column_name="message",
                            operation="equals",
                            search_value="world",
                        ),
                    ],
                ),
            ]
        ),
        af,
    )
    assert r_2 is None


async def test_build_basic_correct_where():
    given = Given.searchable_columns(
        SearchableColumn(
            columns=[
                SearchTableModel(
                    column=Alerts.message,
                    column_name="message",
                    expected_value_type=str,
                ),
            ],
            supports_equals=True,
            supports_contains=True,
            supports_starts_with=True,
            supports_ends_with=True,
        )
    )
    q_1 = SearchAddons._get_conditions(
        [SearchItemIn(column_name="message", operation="equals", search_value="test")],
        given.sc.lookups,
    )
    assert str(q_1[0]) == '"alerts"."message" = \'test\''

    q_2 = SearchAddons._get_conditions(
        [SearchItemIn(column_name="message", operation="equals", search_value="test'")],
        given.sc.lookups,
    )
    assert str(q_2[0]) == '"alerts"."message" = \'test\'\''

    q_3 = SearchAddons._get_conditions(
        [
            JoinModel(
                operand="or",
                filters=[
                    SearchItemIn(
                        column_name="message",
                        operation="equals",
                        search_value="test",
                    ),
                    SearchItemIn(
                        column_name="message",
                        operation="equals",
                        search_value="message",
                    ),
                ],
            ),
        ],
        given.sc.lookups,
    )
    assert (
        str(q_3[0])
        == '("alerts"."message" = \'test\' OR "alerts"."message" = \'message\')'
    )

    q_4 = SearchAddons._get_conditions(
        [
            JoinModel(
                operand="and",
                filters=[
                    SearchItemIn(
                        column_name="message",
                        operation="equals",
                        search_value="test",
                    ),
                    JoinModel(
                        operand="or",
                        filters=[
                            SearchItemIn(
                                column_name="message",
                                operation="equals",
                                search_value="hello",
                            ),
                            SearchItemIn(
                                column_name="message",
                                operation="equals",
                                search_value="world",
                            ),
                        ],
                    ),
                ],
            ),
        ],
        given.sc.lookups,
    )
    assert (
        str(q_4[0]) == '("alerts"."message" = \'test\' '
        'AND ("alerts"."message" = \'hello\' OR "alerts"."message" = \'world\'))'
    )
