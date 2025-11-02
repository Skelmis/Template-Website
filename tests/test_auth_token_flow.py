import httpx
import pytest
from httpx import AsyncClient
from litestar import Litestar
from litestar.testing import AsyncTestClient


@pytest.mark.parametrize("session_cookie", ["user_1"], indirect=True)
async def test_getting_token_from_session(
    test_client: AsyncTestClient[Litestar],
    session_cookie,
    csrf_token,
    patch_saq,
):
    resp: httpx.Response = await test_client.post(
        "/auth/token/initial",
        data={"_csrf_token": csrf_token},
        cookies={"csrf_token": csrf_token, "id": session_cookie},
        follow_redirects=False,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data
    assert "expiry_date" in data
    assert "max_expiry_date" in data
    # assert resp.json() == {
    #     "expiry_date": "2025-11-02T09:34:19.118230Z",
    #     "max_expiry_date": "2025-11-05T07:34:19.118332Z",
    #     "token": "5a18649831c61bbc570126dc32eb78711ed88bc98d00a331a3bfcc5ad9ca964e",
    # }
