import commons
import logoo
from litestar import MediaType
from litestar.exceptions import InternalServerException
from litestar.response import Redirect, Response
from starlette.requests import Request

logger = logoo.Logger(__name__)


class RedirectForAuth(Exception):
    """Mark this authentication failure as a request to receive it"""

    def __init__(self, next_route: str):
        self.next_route = next_route


def redirect_for_auth(request: Request, exc: RedirectForAuth) -> Response[Redirect]:
    """Where auth is required, redirect for it"""
    return Redirect(str(request.url_for("sign_in", next_route=exc.next_route)))


def handle_500(_: Request, exc: InternalServerException) -> Response:
    logger.error(
        "Internal Server Error",
        extra_metadata={"traceback": commons.exception_as_string(exc)},
    )
    return Response(
        media_type=MediaType.JSON,
        content={"status_code": 500, "detail": "Internal Server Error"},
        status_code=500,
    )
