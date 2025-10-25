from __future__ import annotations

from typing import TYPE_CHECKING

from piccolo.columns import (
    Timestamp,
    Text,
    LazyTableReference,
    Timestamptz,
)
from piccolo.columns.column_types import Serial, ForeignKey
from piccolo.columns.indexes import IndexMethod
from piccolo.table import Table


class OAuthEntry(Table, tablename="oauth_entry"):
    if TYPE_CHECKING:
        id: Serial

    oauth_id = Text(
        help_text="The ID of this person in OAuth land",
        index=True,
        index_method=IndexMethod.hash,
    )
    oauth_email = Text(help_text="The email address of this person in OAuth land")
    provider = Text(help_text="The OAuth provider")
    user = ForeignKey(LazyTableReference("Users", module_path="home.tables"))
    last_login = Timestamptz(
        null=True,
        default=None,
        required=False,
        help_text="When this user last logged in using this provider.",
    )
