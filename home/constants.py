import base64
import logging
import os
import re
from copy import deepcopy
from datetime import timedelta

from commons import value_to_bool
from dotenv import load_dotenv
from infisical_sdk import InfisicalSDKClient
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from piccolo_api.encryption.providers import XChaCha20Provider
from piccolo_api.mfa.authenticator.provider import AuthenticatorProvider

load_dotenv()
infisical_client = InfisicalSDKClient(host="https://secrets.skelmis.co.nz")
infisical_client.auth.universal_auth.login(
    client_id=os.environ["INFISICAL_ID"],
    client_secret=os.environ["INFISICAL_SECRET"],
)


def configure_otel():
    # Service name is required for most backends
    stream = get_secret("LOGOO_STREAM", infisical_client)
    resource = Resource(attributes={SERVICE_NAME: stream})
    trace_provider = TracerProvider(resource=resource)
    log_url = "https://logs.skelmis.co.nz/api/default/v1/logs"
    trace_url = "https://logs.skelmis.co.nz/api/default/v1/traces"
    headers = {
        "Authorization": f"Basic {
        base64.b64encode(
            bytes(
                get_secret("LOGOO_USER", infisical_client) 
                + ":" + get_secret("LOGOO_PASSWORD", infisical_client)
                , "utf-8")
        ).decode("utf-8")}"
    }
    trace_exporter = OTLPSpanExporter(endpoint=trace_url, headers=headers)
    span_processor = BatchSpanProcessor(trace_exporter)
    trace_provider.add_span_processor(span_processor)
    # Sets the global default tracer provider
    trace.set_tracer_provider(trace_provider)

    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    log_headers = deepcopy(headers)
    log_headers["stream-name"] = stream
    log_exporter = OTLPLogExporter(endpoint=log_url, headers=log_headers)
    log_batch = BatchLogRecordProcessor(log_exporter)
    logger_provider.add_log_record_processor(log_batch)
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    logging.basicConfig(
        handlers=[handler],
        level=logging.DEBUG,
        format="%(message)s",
        datefmt="%I:%M:%S %p %d/%m/%Y",
    )


def get_secret(secret_name: str, infisical_client: InfisicalSDKClient) -> str:
    return infisical_client.secrets.get_secret_by_name(
        secret_name=secret_name,
        project_id=os.environ["INFISICAL_PROJECT_ID"],
        environment_slug=os.environ["INFISICAL_SLUG"],
        secret_path="/",
        view_secret_value=True,
    ).secretValue


SITE_NAME: str = os.environ.get("SITE_NAME", "Template Website")
"""The site name for usage in templates etc"""

IS_PRODUCTION: bool = not value_to_bool(os.environ.get("DEBUG"))
"""Are we in production?"""

ALLOW_REGISTRATION: bool = value_to_bool(os.environ.get("ALLOW_REGISTRATION", True))
"""Whether users should be allowed to create new accounts."""

SERVING_DOMAIN: list[str] = os.environ.get("SERVING_DOMAIN", "localhost").split(",")
"""The domain this site will run on. Used for cookies etc."""

CHECK_PASSWORD_AGAINST_HIBP: bool = not value_to_bool(
    os.environ.get("DISABLE_HIBP", False)
)
"""If True, checks passwords against Have I Been Pwned"""

SIMPLE_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
"""A simple email regex. Not perfect, but good enough."""

MAKE_FIRST_USER_ADMIN: bool = value_to_bool(
    os.environ.get("MAKE_FIRST_USER_ADMIN", True)
)
"""Makes the first user to sign in admin. Just makes life easier."""

REQUIRE_MFA: bool = value_to_bool(os.environ.get("REQUIRE_MFA", False))
"""Enforces the usage of MFA for authentication.

Due to platform limitations, it won't be enforced if users
only sign in via the admin portal.
"""

DONT_SEND_EMAILS: bool = value_to_bool(os.environ.get("DONT_SEND_EMAILS", False))
"""If True, prints emails to console instead of sending them"""

MAGIC_LINK_VALIDITY_WINDOW = timedelta(minutes=5)
"""How long since it is sent can a link be used to authenticate"""


SESSION_KEY = bytes.fromhex(get_secret("SESSION_KEY", infisical_client))
CSRF_TOKEN = get_secret("CSRF_TOKEN", infisical_client)
ENCRYPTION_KEY = bytes.fromhex(get_secret("ENCRYPTION_KEY", infisical_client))
ENCRYPTION_PROVIDER = XChaCha20Provider(ENCRYPTION_KEY)
MFA_TOTP_PROVIDER = AuthenticatorProvider(
    ENCRYPTION_PROVIDER, issuer_name=SITE_NAME, valid_window=1
)
MAILGUN_API_KEY = get_secret("MAILGUN_API_KEY", infisical_client)
