from litestar import MediaType
from litestar.response import Template

from home import constants
from home.util import get_csp


def html_template(
    template_name: str,
    context: dict = None,
    *,
    status_code: int = 200,
) -> Template:
    if context is None:
        context = {}

    csp, nonce = get_csp()
    context["csp_nonce"] = nonce
    context["site_name"] = constants.SITE_NAME
    return Template(
        template_name=template_name,
        context=context,
        headers={"content-security-policy": csp},
        media_type=MediaType.HTML,
        status_code=status_code,
    )
