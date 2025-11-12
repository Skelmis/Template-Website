import logging

import commons
from litestar import MediaType
from litestar.exceptions import InternalServerException, NotFoundException
from litestar.response import Redirect, Response
from pydantic import BaseModel, Field
from starlette.requests import Request

from template.util import html_template

logger = logging.getLogger(__name__)


class RedirectForAuth(Exception):
    """Mark this authentication failure as a request to receive it"""

    def __init__(self, next_route: str):
        self.next_route = next_route


class APIRedirectForAuth(BaseModel):
    status_code: int = 401
    message: str = (
        "You are attempting to access an authenticated "
        "resource without providing authentication."
    )
    redirect_uri: str = Field(description="Where to send a UI user for authentication")


def redirect_for_auth(
    request: Request, exc: RedirectForAuth
) -> Response[Redirect] | Response[APIRedirectForAuth]:
    """Where auth is required, redirect for it. If its an API just dump an error"""
    next_url = (
        str(request.url_for("select_auth_provider")).rstrip("?")
        + f"?next_route={exc.next_route}"
    )
    if (
        hasattr(request, "route_handler")
        and "is_api_route" in request.route_handler.opt
        and request.route_handler.opt["is_api_route"] is True
    ):
        return Response(APIRedirectForAuth(redirect_uri=next_url), status_code=401)

    return Redirect(next_url)


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
