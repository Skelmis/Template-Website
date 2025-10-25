import os

import jinja2
from dotenv import load_dotenv
from litestar import Litestar, asgi, Request
from litestar.config.cors import CORSConfig
from litestar.config.csrf import CSRFConfig
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.contrib.opentelemetry import OpenTelemetryPlugin, OpenTelemetryConfig
from litestar.datastructures import ResponseHeader
from litestar.exceptions import NotFoundException
from litestar.middleware.rate_limit import RateLimitConfig
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.openapi.spec import SecurityScheme, Components
from litestar.plugins.flash import FlashPlugin, FlashConfig
from litestar.static_files import StaticFilesConfig
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from litestar.template import TemplateConfig
from litestar.types import Receive, Scope, Send, Empty
from piccolo.engine import engine_finder
from piccolo_admin.endpoints import create_admin, TableConfig
from piccolo_api.crud.endpoints import OrderBy
from piccolo_api.crud.hooks import HookType, Hook
from piccolo_api.mfa.authenticator.tables import AuthenticatorSecret

from home import constants
from home.constants import IS_PRODUCTION
from home.controllers import AuthController, OAuthController
from home.endpoints import (
    home,
)
from home.exception_handlers import (
    redirect_for_auth,
    RedirectForAuth,
    handle_500,
    handle_404,
)
from home.middleware import EnsureAuth
from home.tables import Users, OAuthEntry, MagicLinks
from home.util.flash import inject_alerts

load_dotenv()


def post_validate_password_changes(row: Users):
    """Given we dont subclass BaseUser we need to patch this in"""
    try:
        row.split_stored_password(row.password)
    except ValueError:
        row._validate_password(row.password)
        row.password = row.hash_password(row.password)

    return row


def patch_validate_password_changes(row_id: int, values: dict):
    """Given we dont subclass BaseUser we need to patch this in"""
    password: str | None = values.pop("password", None)
    if not password:
        return values

    try:
        Users.split_stored_password(password)
    except ValueError:
        Users._validate_password(password)
        values["password"] = Users.hash_password(password)

    return values


@asgi("/admin/", is_mount=True, copy_scope=True)
async def admin(scope: "Scope", receive: "Receive", send: "Send") -> None:
    user_tc = TableConfig(
        Users,
        menu_group="User Management",
        hooks=[
            Hook(hook_type=HookType.pre_save, callable=post_validate_password_changes),
            Hook(
                hook_type=HookType.pre_patch, callable=patch_validate_password_changes
            ),
        ],
    )
    oauth_entry_tc = TableConfig(OAuthEntry, menu_group="User Management")
    magic_link_tc = TableConfig(MagicLinks, menu_group="User Management")
    mfa_tc = TableConfig(
        AuthenticatorSecret,
        menu_group="User Management",
        exclude_visible_columns=[
            AuthenticatorSecret.secret,
            AuthenticatorSecret.recovery_codes,
            AuthenticatorSecret.last_used_code,
        ],
        order_by=[
            OrderBy(AuthenticatorSecret.id, ascending=False),
        ],
    )

    await create_admin(
        tables=[user_tc, mfa_tc, oauth_entry_tc, magic_link_tc],
        production=IS_PRODUCTION,
        allowed_hosts=constants.SERVING_DOMAIN,
        sidebar_links={"Site root": "/", "API documentation": "/docs/"},
        site_name=constants.SITE_NAME.rstrip() + " Admin",
        auto_include_related=True,
        mfa_providers=[constants.MFA_TOTP_PROVIDER],
        auth_table=Users,  # type: ignore
    )(scope, receive, send)


async def open_database_connection_pool():
    try:
        engine = engine_finder()
        await engine.start_connection_pool()
    except Exception:
        print("Unable to connect to the database")


async def close_database_connection_pool():
    try:
        engine = engine_finder()
        await engine.close_connection_pool()
    except Exception:
        print("Unable to connect to the database")


async def before_request_handler(request: Request) -> dict[str, str] | None:
    user = await EnsureAuth.get_user_from_connection(request, fail_on_not_set=False)
    request.scope["user"] = user
    if user is not None:
        await inject_alerts(request, user)

    return None


logging_config = None
if constants.IS_PRODUCTION:
    constants.configure_otel()

else:
    # Just print logs locally during dev
    logging_config = Empty

open_telemetry_config = OpenTelemetryConfig()
cors_config = CORSConfig(
    allow_origins=[],
    allow_headers=[],
    allow_methods=[],
    allow_credentials=False,
)
csrf_config = CSRFConfig(
    secret=constants.CSRF_TOKEN,
    # Aptly named so it doesnt clash
    # with piccolo 'csrftoken' cookies
    cookie_name="csrf_token",
    cookie_secure=True,
    cookie_httponly=True,
    # Exclude routes Piccolo handles itself
    # and our api routes
    exclude=[
        "/admin/",
        "/api",
        "/auth",
    ],
)
# noinspection PyTypeChecker
rate_limit_config = RateLimitConfig(
    rate_limit=("second", 10),
    exclude=[
        "/docs",
        "/admin/",
        "/api",
    ],
)
ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(
        searchpath=os.path.join(os.path.dirname(__file__), "home", "templates")
    ),
    autoescape=True,
)
template_config = TemplateConfig(
    directory="home/templates",
    engine=JinjaTemplateEngine.from_environment(ENVIRONMENT),
)
flash_plugin = FlashPlugin(
    config=FlashConfig(template_config=template_config),
)
session_config = CookieBackendConfig(secret=constants.SESSION_KEY)
exception_handlers: dict[..., ...] = {
    RedirectForAuth: redirect_for_auth,
    NotFoundException: handle_404,
}
if IS_PRODUCTION:
    exception_handlers[HTTP_500_INTERNAL_SERVER_ERROR] = handle_500

routes = [admin, home, AuthController]
if constants.HAS_IMPLEMENTED_OAUTH:
    routes.append(OAuthController)  # type: ignore

app = Litestar(
    route_handlers=routes,
    template_config=template_config,
    static_files_config=[
        StaticFilesConfig(directories=["static"], path="/static/"),
    ],
    on_startup=[open_database_connection_pool],
    on_shutdown=[close_database_connection_pool],
    debug=not IS_PRODUCTION,
    openapi_config=OpenAPIConfig(
        title=constants.SITE_NAME.rstrip() + " API",
        version="0.0.0",
        render_plugins=[SwaggerRenderPlugin()],
        path="/docs",
        components=Components(
            security_schemes={
                "session": SecurityScheme(
                    type="apiKey",
                    name="id",
                    security_scheme_in="cookie",
                    description="Session based authentication.",
                ),
            }
        ),
    ),
    cors_config=cors_config,
    csrf_config=csrf_config,
    logging_config=logging_config,
    middleware=[rate_limit_config.middleware, session_config.middleware],
    plugins=[flash_plugin, OpenTelemetryPlugin(open_telemetry_config)],
    response_headers=[
        ResponseHeader(
            name="x-frame-options",
            value="SAMEORIGIN",
            description="Security header",
        ),
        ResponseHeader(
            name="x-content-type-options",
            value="nosniff",
            description="Security header",
        ),
        ResponseHeader(
            name="referrer-policy",
            value="strict-origin",
            description="Security header",
        ),
        ResponseHeader(
            name="permissions-policy",
            value="microphone=(); geolocation=(); fullscreen=();",
            description="Security header",
        ),
        ResponseHeader(
            name="content-security-policy",
            value="default-src 'none'; frame-ancestors 'none'; object-src 'none';"
            " base-uri 'none'; script-src 'nonce-{}' 'strict-dynamic'; style-src "
            "'nonce-{}' 'strict-dynamic'; require-trusted-types-for 'script'",
            description="Security header",
            documentation_only=True,
        ),
    ],
    exception_handlers=exception_handlers,
    before_request=before_request_handler,
)
