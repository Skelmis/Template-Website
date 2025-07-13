import hmac
import typing
import warnings
from datetime import timedelta, datetime

from commons.hibp import has_password_been_pwned
from litestar import Controller, Request, get, post
from litestar.exceptions import SerializationException, HTTPException
from litestar.response import Template, Redirect
from litestar.status_codes import HTTP_303_SEE_OTHER
from piccolo.apps.user.tables import BaseUser
from piccolo_api.mfa.authenticator.tables import AuthenticatorSecret
from piccolo_api.session_auth.tables import SessionsBase

from home import constants
from home.middleware import EnsureAuth
from home.util import html_template, alert


class AuthController(Controller):
    path = "/auth"
    _auth_table = BaseUser
    _mfa_table = AuthenticatorSecret
    _session_table = SessionsBase
    _session_expiry = timedelta(hours=6)
    _max_session_expiry = timedelta(days=3)
    _redirect_to = "/"
    _cookie_name = "id"
    tags = ["Authentication"]
    include_in_schema = False

    @staticmethod
    def _render_template(request: Request, template: str) -> Template:
        csrftoken = request.scope.get("csrftoken")  # type: ignore
        csrf_cookie_name = request.scope.get("csrf_cookie_name")  # type: ignore
        return html_template(
            template,
            {
                "csrftoken": csrftoken,
                "csrf_cookie_name": csrf_cookie_name,
                "request": request,
                "has_registration": constants.ALLOW_REGISTRATION,
            },
        )

    @classmethod
    async def get_user_for_creds(
        cls, request: Request, username: str, password: str
    ) -> tuple[BaseUser | None, Redirect | Template | None]:
        """Standard auth flow related to a password

        Returns
        -------
        tuple[BaseUser | None, Redirect | Template | None]
            The user if auth is correct else a redirect/template to expected page
        """
        if (not username) or (not password):
            alert(request, "Missing username or password", level="error")
            return None, cls._render_template(request, "auth/sign_in.jinja")

        user_id = await cls._auth_table.login(
            username=username,
            password=password,
        )

        if not user_id:
            alert(
                request,
                "The username, password or mfa is incorrect.",
                level="error",
            )
            return None, cls._render_template(request, "auth/sign_in.jinja")

        user_is_active = await BaseUser.exists().where(
            (BaseUser.id == user_id) & (BaseUser.active.eq(True))
        )
        if not user_is_active:
            alert(request, "User is currently disabled.", level="error")
            return None, cls._render_template(request, "auth/sign_in.jinja")

        return (
            await cls._auth_table.objects().get(cls._auth_table.id == user_id),
            None,
        )

    @staticmethod
    async def details_from_body(request: Request):
        # Some middleware (for example CSRF) has already awaited the request
        # body, and adds it to the request.
        body: typing.Any = request.scope.get("form")  # type: ignore

        if not body:
            try:
                body = await request.json()
            except SerializationException:
                body = await request.form()

        if body is None:
            return None, None, None

        username = body.get("username", None)
        password = body.get("password", None)
        mfa = body.get("mfa", None)
        return username, password, mfa

    @classmethod
    async def create_session_for_user(cls, user: BaseUser) -> str:
        if not constants.IS_PRODUCTION:
            message = (
                "If running sessions in production, make sure 'production' "
                "is set to True, and serve under HTTPS."
            )
            warnings.warn(message)

        now = datetime.now()
        expiry_date = now + cls._session_expiry
        max_expiry_date = now + cls._max_session_expiry

        session: SessionsBase = await cls._session_table.create_session(
            user_id=user.id,  # type: ignore
            expiry_date=expiry_date,
            max_expiry_date=max_expiry_date,
        )

        return typing.cast(str, session.token)

    async def confirm_mfa_was_correct(
        self, request: Request, user: BaseUser, mfa_code: str
    ) -> Redirect | bool | None:
        """Returns None if MFA was valid, Redirect if it needs configuring and False if incorrect"""
        user_is_enrolled = await constants.MFA_TOTP_PROVIDER.is_user_enrolled(user)
        if constants.REQUIRE_MFA or user_is_enrolled:
            # Check MFA if the site requires it or the user has it setup
            if not user_is_enrolled:
                # Not setup, yet is required.
                # Kick to MFA creation screen
                alert(
                    request,
                    "MFA is required to authenticate, yet you don't have it set up. "
                    "Please set it up here.",
                    level="error",
                )
                return Redirect(request.url_for("create_totp_mfa"))

            # Attempt to authenticate against the MFA provider
            if not await constants.MFA_TOTP_PROVIDER.authenticate_user(
                user=user,
                code=mfa_code,
            ):
                return False

        return None

    @get("/sign_in", name="sign_in")
    async def sign_in_get(self, request: Request) -> Template:
        return self._render_template(request, "auth/sign_in.jinja")

    @post("/sign_in")
    async def sign_in_post(
        self,
        request: Request,
        next_route: str = "/",
    ) -> Template | Redirect:
        username, password, mfa = await self.details_from_body(request)
        user, response = await self.get_user_for_creds(request, username, password)
        if response is not None:
            return response

        response = await self.confirm_mfa_was_correct(request, user, mfa)
        if response is False:
            alert(
                request,
                "The username, password or mfa is incorrect.",
                level="error",
            )
            return self._render_template(request, "auth/sign_in.jinja")

        elif response is not None:
            return response

        if constants.CHECK_PASSWORD_AGAINST_HIBP and await has_password_been_pwned(
            password
        ):
            alert(
                request,
                "Your password appears in breach databases, consider changing it.",
                level="error",
            )

        # Basic open redirect checks
        if not next_route.startswith("/"):
            next_route = "/"

        response: Redirect = Redirect(next_route)
        cookie = await self.create_session_for_user(user)
        response.set_cookie(
            key=self._cookie_name,
            value=cookie,
            httponly=True,
            secure=constants.IS_PRODUCTION,
            max_age=int(self._max_session_expiry.total_seconds()),
            samesite="lax",
        )
        return response

    @get("/mfa/totp", name="manage_totp_mfa", middleware=[EnsureAuth])
    async def totp_mfa_get(self, request: Request) -> Template:
        if await constants.MFA_TOTP_PROVIDER.is_user_enrolled(request.user):
            # MFA must be explicitly deleted before we will allow another one to be configured
            return self._render_template(request, "auth/mfa_configure.jinja")

        return self._render_template(request, "auth/mfa_create.jinja")

    @get("/mfa/totp/create", name="create_totp_mfa", middleware=[])
    async def totp_mfa_create_get(self, request: Request) -> Template | Redirect:
        if request.user and await constants.MFA_TOTP_PROVIDER.is_user_enrolled(
            request.user
        ):
            alert(
                request,
                "MFA must be explicitly deleted before we will "
                "allow another one to be configured",
                level="error",
            )
            return Redirect(request.url_for("manage_totp_mfa"))

        return self._render_template(request, "auth/mfa_create.jinja")

    @post("/mfa/totp/create")
    async def totp_mfa_create(self, request: Request) -> Template | Redirect:
        username, password, _ = await self.details_from_body(request)
        user, response = await self.get_user_for_creds(request, username, password)
        if response is not None:
            return response

        if await constants.MFA_TOTP_PROVIDER.is_user_enrolled(user):
            alert(request, "You are already enrolled with MFA.", level="warning")
            return Redirect(request.url_for("manage_totp_mfa"))

        registration_json = await constants.MFA_TOTP_PROVIDER.get_registration_json(
            user
        )
        response = html_template("auth/mfa_confirm.jinja", registration_json)
        cookie = await self.create_session_for_user(user)
        response.set_cookie(
            key=self._cookie_name,
            value=cookie,
            httponly=True,
            secure=constants.IS_PRODUCTION,
            max_age=int(self._max_session_expiry.total_seconds()),
            samesite="lax",
        )
        return response

    @post("/mfa/totp/confirm", name="mfa_totp_confirm", middleware=[EnsureAuth])
    async def totp_mfa_confirm(self, request: Request) -> Template | Redirect:
        _, _, mfa = await self.details_from_body(request)
        response = await self.confirm_mfa_was_correct(request, request.user, mfa)
        if response is False:
            alert(
                request,
                "Looks like your MFA code was wrong. You should "
                "delete it below otherwise you could lock yourself out of your account.",
                level="error",
            )
            return Redirect(request.url_for("manage_totp_mfa"))

        elif response is not None:
            return response

        alert(
            request,
            "MFA was correct, congrats on successfully configuring it!",
            level="success",
        )
        return self._render_template(request, "auth/mfa_configure.jinja")

    @post("/mfa/totp/delete", name="mfa_totp_delete", middleware=[EnsureAuth])
    async def totp_mfa_delete(self, request: Request) -> Template | Redirect:
        # SOFT delete, but safe to stack for same user
        await constants.MFA_TOTP_PROVIDER.delete_registration(user=request.user)
        alert(
            request,
            "Successfully deleted MFA for your account, please re-authenticate",
            level="success",
        )
        await self.logout_current_user(request)
        response = Redirect(request.url_for("manage_totp_mfa"))
        response.set_cookie(self._cookie_name, "", max_age=0)
        return response

    @classmethod
    async def logout_current_user(cls, request: Request) -> Redirect:
        cookie = request.cookies.get(cls._cookie_name, None)
        if not cookie:
            # Meh this is fine, just redirect it to home
            return Redirect("/")

        await cls._session_table.remove_session(token=cookie)

        response: Redirect = Redirect(cls._redirect_to, status_code=HTTP_303_SEE_OTHER)
        response.set_cookie(cls._cookie_name, "", max_age=0)
        return response

    @get("/sign_out", name="sign_out")
    async def sign_out_get(self, request: Request) -> Template:
        return self._render_template(request, "auth/sign_out.jinja")

    @post("/sign_out")
    async def sign_out_post(self, request: Request) -> Redirect:
        return await self.logout_current_user(request)

    @get("/passwords/forgot", name="forgot_password")
    async def forgot_password_get(self, request: Request) -> Template:
        alert(
            request,
            "This functionality hasn't been implemented yet. "
            "Reach out to your administrator directly.",
            level="info",
        )
        return self._render_template(request, "auth/forgot_password.jinja")

    @post("/passwords/forgot")
    async def forgot_password_post(self, request: Request) -> Redirect:
        return Redirect(request.url_for("forgot_password"))

    @get(
        "/passwords/change",
        name="change_password",
        middleware=[EnsureAuth],
    )
    async def change_password_get(self, request: Request) -> Template:
        return self._render_template(request, "auth/change_password.jinja")

    @post("/passwords/change", middleware=[EnsureAuth])
    async def change_password_post(self, request: Request) -> Template | Redirect:
        # Some middleware (for example CSRF) has already awaited the request
        # body, and adds it to the request.
        body: typing.Any = request.scope.get("form")  # type: ignore

        if not body:
            try:
                body = await request.json()
            except SerializationException:
                body = await request.form()

        current_password = body.get("current_password")
        new_password = body.get("new_password")
        new_password_again = body.get("new_password_again")

        if (
            current_password is None
            or new_password is None
            or new_password_again is None
        ):
            alert(request, "Please fill in all form fields.", level="error")
            return Redirect(request.url_for("change_password"))

        if not hmac.compare_digest(new_password, new_password_again):
            alert(request, "New password fields did not match.", level="error")
            return Redirect(request.url_for("change_password"))

        user = typing.cast(BaseUser, request.user)
        algorithm, iterations_, salt, hashed = BaseUser.split_stored_password(
            user.password
        )
        iterations = int(iterations_)
        if BaseUser.hash_password(current_password, salt, iterations) != user.password:
            alert(request, "Your current password was wrong.", level="error")
            return Redirect(request.url_for("change_password"))

        if constants.CHECK_PASSWORD_AGAINST_HIBP and await has_password_been_pwned(
            new_password
        ):
            alert(
                request,
                "Your new password appears in breach databases, "
                "please pick a unique password.",
                level="error",
            )
            return Redirect(request.url_for("change_password"))

        await user.update_password(user.id, new_password)
        alert(
            request,
            "Successfully changed password, please reauthenticate.",
            level="success",
        )
        return await self.logout_current_user(request)

    @get("/sign_up", name="sign_up")
    async def sign_up_get(self, request: Request) -> Template:
        if not constants.ALLOW_REGISTRATION:
            alert(
                request,
                "Sign ups are disabled. This will do nothing.",
                level="warning",
            )
        return self._render_template(request, "auth/sign_up.jinja")

    @post("/sign_up")
    async def sign_up_post(
        self,
        request: Request,
    ) -> Template | Redirect:
        if not constants.ALLOW_REGISTRATION:
            return Redirect(request.url_for("sign_up"))

        # Some middleware (for example CSRF) has already awaited the request
        # body, and adds it to the request.
        body: typing.Any = request.scope.get("form")  # type: ignore

        if not body:
            try:
                body = await request.json()
            except SerializationException:
                body = await request.form()

        email = body.get("email", None)
        username = body.get("username", None)
        password = body.get("password", None)
        confirm_password = body.get("confirm_password", None)

        if (not username) or (not password) or (not confirm_password) or (not email):
            error_message = "Please ensure all fields on the form are filled out."
            alert(request, error_message, level="error")
            return self._render_template(request, "auth/sign_up.jinja")

        if not constants.SIMPLE_EMAIL_REGEX.match(email):
            alert(request, "Please enter a valid email.", level="error")
            return self._render_template(request, "auth/sign_up.jinja")

        if not hmac.compare_digest(password, confirm_password):
            alert(request, "Passwords do not match.", level="error")
            return self._render_template(request, "auth/sign_up.jinja")

        if constants.CHECK_PASSWORD_AGAINST_HIBP and await has_password_been_pwned(
            password
        ):
            alert(
                request,
                "This password appears in breach databases, "
                "please pick a unique password.",
                level="error",
            )
            return self._render_template(request, "auth/sign_up.jinja")

        # noinspection PyTypeChecker
        if await BaseUser.exists().where(
            BaseUser.username == username,
        ):
            alert(
                request,
                "This user already exists, consider signing in instead.",
                level="error",
            )
            return self._render_template(request, "auth/sign_up.jinja")

        try:
            user: BaseUser = await BaseUser.create_user(
                username, password, email=email, active=True
            )
        except ValueError as err:
            alert(request, str(err), level="error")
            return self._render_template(request, "auth/sign_up.jinja")

        alert(
            request,
            "Thanks for creating an account, you may now sign in.",
            level="success",
        )
        if constants.MAKE_FIRST_USER_ADMIN and await BaseUser.count() == 1:
            alert(
                request,
                "As you are the first user on the system, "
                "I have also made you an admin user.",
                level="info",
            )
            user.admin = True
            await user.save()

        return Redirect(request.url_for("sign_in"))
