from unittest.mock import AsyncMock

from template.controllers.api import APIAlertController
from template.crud.controller import (
    SearchModel,
    SearchItemIn,
    SearchAddons,
    SearchableColumn,
    SearchTableModel,
)
from template.tables import Alerts


# noinspection PyProtectedMember
async def test_validate_filters_on_bad_data():
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
                    column_name="test", operation="equals", search_value="test"
                )
            ]
        ),
        af,
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
        af,
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
        af,
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
