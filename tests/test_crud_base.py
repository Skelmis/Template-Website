import json
from typing import Self, Any
from unittest.mock import AsyncMock

import pytest
from piccolo.columns import Column
from litestar.exceptions import ValidationException

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


async def test_type_checking_on_bad_types():
    with pytest.raises(ValidationException) as e:
        await SearchAddons.validate_search_input_filters(
            SearchModel(
                filters=[
                    SearchItemIn(
                        column_name="target", operation="equals", search_value="test"
                    )
                ]
            ),
            Given.default_searchable_columns().filters,
        )

    assert e.value.detail == json.dumps(
        ["Value 'test' not a supported type for column 'target', expected 'int'."]
    )


# noinspection PyProtectedMember
async def test_validate_filters_on_bad_data():
    with pytest.raises(ValidationException) as e:
        await SearchAddons.validate_search_input_filters(
            SearchModel(
                filters=[
                    SearchItemIn(
                        column_name="test", operation="equals", search_value="test"
                    )
                ]
            ),
            Given.default_searchable_columns().filters,
        )

    assert e.value.detail == json.dumps(["Column 'test' not supported"])

    with pytest.raises(ValidationException) as e:
        await SearchAddons.validate_search_input_filters(
            SearchModel(
                filters=[
                    SearchItemIn(
                        column_name="target", operation="less_then", search_value="test"
                    )
                ]
            ),
            Given.default_searchable_columns().filters,
        )

    assert e.value.detail == json.dumps(
        ["Operation 'less_then' not supported on column 'target'"]
    )

    with pytest.raises(ValidationException) as e:
        await SearchAddons.validate_search_input_filters(
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

    assert e.value.detail == json.dumps(
        ["Value 'test' is not a supported join operand."]
    )

    with pytest.raises(ValidationException) as e:
        await SearchAddons.validate_search_input_filters(
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

    assert e.value.detail == json.dumps(["Join 'and' requires two parameters"])


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
