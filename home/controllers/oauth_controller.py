import logging
import secrets
from datetime import timedelta
from typing import Annotated, Any, cast

import commons
import httpx
from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.oauth2 import OAuth2
from litestar import Controller, get, Request, post
from litestar.enums import RequestEncodingType
from litestar.params import Parameter, Body
from litestar.response import Template, Redirect
from pydantic import BaseModel, Field, model_validator

from home import constants
from home.middleware import EnsureAuth
from home.tables import MagicLinks, Users, OAuthEntry
from home.util import html_template, alert
from home.controllers import AuthController
from home.util.table_mixins import utc_now

logger = logging.getLogger(__name__)
PROVIDERS = {}
if constants.HAS_IMPLEMENTED_OAUTH:
    # For a full list of providers supported natively please see
    # https://frankie567.github.io/httpx-oauth/reference/httpx_oauth.clients/
    PROVIDERS["github"] = GitHubOAuth2(
        client_id=constants.get_secret("GITHUB_CLIENT_ID", constants.infisical_client),
        client_secret=constants.get_secret(
            "GITHUB_CLIENT_SECRET", constants.infisical_client
        ),
        scopes=["user:email", "read:user"],
    )


class OAuth2Result(BaseModel):
    id: str
    email: str
    profile: dict


class LinkOAuthProvidersIn(BaseModel):
    providers: Annotated[
        dict[int, bool],
        Field(
            description="A mapping of OAuthEntry to if they should be allowed to auth",
            examples=[
                "provider-1=on&_csrf_token=aasfghjkl",
            ],
        ),
    ]

    @model_validator(mode="before")
    @classmethod
    def cast_to_expected(cls, data: Any) -> Any:
        # We assume here it is coming from multi-part forms
        # and therefore in the wack HTML format
        providers: dict[int, bool] = {}
        for k, v in data.items():
            k = cast(str, k)
            if k.startswith("provider-"):
                providers[int(k.removeprefix("provider-"))] = v.lower() == "allowed"

        return {"providers": providers}


class OAuthController(Controller):
    # The default implementation explicitly does not
    # store access tokens or refresh tokens outside of auth
    #
    # Also email is used as username for new users
    path = "/auth/oauth"
    include_in_schema = False
    tags = ["Authentication", "OAuth"]

    @classmethod
    async def get_user_from_oauth(
        cls,
        request: Request,
        provider: str,
        oauth_id: str,
        email: str,
        *,
        name: str = None,
    ) -> tuple[Users | None, Redirect | None]:
        oauth_entry: OAuthEntry | None = (
            await OAuthEntry.objects()
            .where(OAuthEntry.provider == provider)  # type: ignore
            .where(OAuthEntry.oauth_id == oauth_id)
            .first()
        )
        user_already_exists: bool = await Users.exists().where(Users.email == email)  # type: ignore
        if user_already_exists and oauth_entry.user is None:
            alert(
                request,
                "Looks like that user already exists and authenticates via "
                "other means. Please sign in and allow usage of this provider.",
                level="error",
            )
            return None, Redirect(request.url_for("link_oauth_accounts"))

        if oauth_entry is None:
            oauth_entry = OAuthEntry(
                provider=provider, oauth_id=oauth_id, oauth_email=email
            )
            await oauth_entry.save()
            if user_already_exists:
                # Existing account,
                #   This helps mitigate account takeover from platforms
                #   that don't verify email ownership
                alert(
                    request,
                    "Looks like that user already exists and authenticates via "
                    "other means. Please sign in and allow usage of this provider.",
                    level="error",
                )
                return None, Redirect(request.url_for("link_oauth_accounts"))

            user = Users(
                username=email,
                name=name,
                email=email,
                password=secrets.token_hex(64),
                active=True,
                auths_without_password=True,
            )
            await user.save()
            oauth_entry.user = user

        # It may have updated
        #   If so, update the link email but not our sites one
        oauth_entry.oauth_email = email
        oauth_entry.last_login = utc_now()
        await oauth_entry.save()
        return await Users.objects().get(Users.id == oauth_entry.user), None

    @get("/select_provider", name="select_oauth_provider")
    async def get_select_provider(
        self, request: Request, next_route: str = "/"
    ) -> Template:
        return html_template(
            "oauth/select_provider.jinja",
            {
                "next_route": next_route,
                "providers": [
                    (
                        k,
                        request.url_for(
                            "provider_sign_in", provider=k, next_route=next_route
                        ),
                    )
                    for k in PROVIDERS.keys()
                ],
            },
        )

    @get("/link_providers", name="link_oauth_accounts", middleware=[EnsureAuth])
    async def get_link_oauth_accounts(self, request: Request) -> Template:
        providers = await OAuthEntry.objects().where(  # type: ignore
            OAuthEntry.oauth_email == request.user.email  # type: ignore
        )
        return html_template(
            "oauth/link_providers.jinja",
            {
                "providers": providers,
            },
        )

    @post("/link_providers", middleware=[EnsureAuth])
    async def post_link_oauth_accounts(
        self,
        request: Request,
        data: LinkOAuthProvidersIn = Body(media_type=RequestEncodingType.MULTI_PART),
    ) -> Template:
        for provider_id, value in data.providers.items():
            oauth_entry: OAuthEntry | None = (
                await OAuthEntry.objects()
                .where(OAuthEntry.id == provider_id)
                .where(OAuthEntry.oauth_email == request.user.email)  # type: ignore
                .first()
            )
            if oauth_entry is None:
                alert(
                    request,
                    "Something went wrong linking {provider_id} to you. Please retry.",
                    level="error",
                )
                continue

            if value:
                oauth_entry.user = request.user
            else:
                oauth_entry.user = None
            await oauth_entry.save()

        alert(
            request,
            "Thank you, changes have been saved and should be reflected below.",
            level="success",
        )
        return html_template(
            "oauth/link_providers.jinja",
            {
                "providers": await OAuthEntry.objects().where(  # type: ignore
                    OAuthEntry.oauth_email == request.user.email  # type: ignore
                ),
            },
        )

    @get(path="/{provider:str}/sign_in", name="provider_sign_in")
    async def login_via_provider(
        self, request: Request, provider: str, next_route: str = "/"
    ) -> Redirect | Template:
        if provider not in PROVIDERS:
            alert(request, f"{provider} not implemented", level="error")
            return html_template(
                "oauth/select_provider.jinja",
                {
                    "next_route": next_route,
                },
            )

        provider_client = PROVIDERS[provider]
        redirect_uri = request.url_for(
            f"authorize_{provider}", provider=provider, next_route=next_route
        )
        state = MagicLinks.generate_token()
        auth_url = await provider_client.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            extras_params={"allow_signup": constants.ALLOW_REGISTRATION},
        )
        response = Redirect(path=auth_url, status_code=302)
        response.set_cookie(
            key=f"{provider}_state",
            value=state,
            httponly=True,
            secure=constants.IS_PRODUCTION,
            max_age=int(timedelta(minutes=10).total_seconds()),
            samesite="lax",
        )
        response.set_cookie(
            key="next_route",
            value=next_route,
            httponly=True,
            secure=constants.IS_PRODUCTION,
            max_age=int(timedelta(minutes=10).total_seconds()),
            samesite="lax",
        )
        return response

    @get(path="/github/authorize", name="authorize_github")
    async def authorize_github(
        self,
        code: str,
        request: Request,
        callback_state: str | None = Parameter(query="state", required=False),
    ) -> Template | Redirect:
        if request.cookies.get("github_state") != callback_state:
            alert(
                request,
                "Something went wrong validating GitHub made this request. Try again.",
                level="error",
            )
            return html_template("oauth/select_provider.jinja")

        try:
            provider_client: GitHubOAuth2 = PROVIDERS["github"]
            redirect_uri = request.url_for("authorize_github")

            # returns an OAuth2Token
            oauth2_token = await provider_client.get_access_token(
                code=code, redirect_uri=redirect_uri
            )

            access_token = oauth2_token["access_token"]
            profile = await provider_client.get_profile(access_token)
            oauth_id, email = await provider_client.get_id_email(access_token)
            oauth_id = str(oauth_id)
            user, redirect = await self.get_user_from_oauth(
                request,
                "github",
                oauth_id,
                email,
                name=profile["name"],
            )
            if redirect is not None:
                return redirect

        except Exception as e:
            if not constants.IS_PRODUCTION:
                raise

            alert(request, "Something went wrong, please try again.", level="error")
            logger.error(
                "OAuth route ran into issues",
                extra={"traceback": commons.exception_as_string(e)},
            )
            return html_template("oauth/select_provider.jinja")

        next_route = AuthController.validate_next_route(
            request.cookies.get("next_route", "/")
        )
        response: Redirect = Redirect(next_route)
        user.last_login = utc_now()
        await user.save()
        cookie = await AuthController.create_session_for_user(user)
        response.set_cookie(
            key=AuthController.cookie_name,
            value=cookie,
            httponly=True,
            secure=constants.IS_PRODUCTION,
            max_age=int(AuthController.max_session_expiry.total_seconds()),
            samesite="lax",
        )
        response.delete_cookie("github_state")
        response.delete_cookie("next_route")
        return response
