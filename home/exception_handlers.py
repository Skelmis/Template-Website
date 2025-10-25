import logging

import commons
from litestar import MediaType
from litestar.exceptions import InternalServerException, NotFoundException
from litestar.response import Redirect, Response
from starlette.requests import Request

from home.util import html_template

logger = logging.getLogger(__name__)


class RedirectForAuth(Exception):
    """Mark this authentication failure as a request to receive it"""

    def __init__(self, next_route: str):
        self.next_route = next_route


def redirect_for_auth(request: Request, exc: RedirectForAuth) -> Response[Redirect]:
    """Where auth is required, redirect for it"""
    return Redirect(
        str(request.url_for("select_auth_provider")).rstrip("?")
        + f"?next_route={exc.next_route}"
    )


def handle_500(request: Request, exc: InternalServerException) -> Response:
    logger.error(
        "Internal Server Error",
        extra={"traceback": commons.exception_as_string(exc)},
    )
    if "user" not in request.scope:
        request.scope["user"] = None  # Needs something

    return html_template("codes/500.jinja", status_code=404)


def handle_404(request: Request, exc: NotFoundException) -> Response:
    if "user" not in request.scope:
        request.scope["user"] = None  # Needs something

    return html_template("codes/404.jinja", status_code=404)
