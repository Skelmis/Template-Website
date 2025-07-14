import os
import re

import commons
import logoo
from commons import value_to_bool
from dotenv import load_dotenv
from infisical_sdk import InfisicalSDKClient
from piccolo_api.encryption.providers import XChaCha20Provider
from piccolo_api.mfa.authenticator.provider import AuthenticatorProvider

load_dotenv()
infisical_client = InfisicalSDKClient(host="https://secrets.skelmis.co.nz")
infisical_client.auth.universal_auth.login(
    client_id=os.environ["INFISICAL_ID"],
    client_secret=os.environ["INFISICAL_SECRET"],
)


def get_secret(secret_name: str, infisical_client: InfisicalSDKClient) -> str:
    return infisical_client.secrets.get_secret_by_name(
        secret_name=secret_name,
        project_id=os.environ["INFISICAL_PROJECT_ID"],
        environment_slug=(
            "dev" if commons.value_to_bool(os.environ.get("DEBUG")) else "prod",
        ),
        secret_path="/",
        view_secret_value=True,
    ).secretValue


primary_logger = logoo.PrimaryLogger(
    __name__,
    base_url="https://logs.skelmis.co.nz",
    org="default",
    stream=get_secret("LOGOO_STREAM", infisical_client),
    username=get_secret("LOGOO_USER", infisical_client),
    password=get_secret("LOGOO_PASSWORD", infisical_client),
    poll_time=15,
    global_metadata={
        "service": "data_site",
    },
)
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

SESSION_KEY = bytes.fromhex(get_secret("SESSION_KEY", infisical_client))
CSRF_TOKEN = get_secret("CSRF_TOKEN", infisical_client)
ENCRYPTION_KEY = bytes.fromhex(get_secret("ENCRYPTION_KEY", infisical_client))
ENCRYPTION_PROVIDER = XChaCha20Provider(ENCRYPTION_KEY)
MFA_TOTP_PROVIDER = AuthenticatorProvider(
    ENCRYPTION_PROVIDER, issuer_name=SITE_NAME, valid_window=1
)
