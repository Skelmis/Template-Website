from litestar import get
from litestar.response import Template

from template.util import html_template


@get(path="/", include_in_schema=False)
async def home() -> Template:
    return html_template(
        "home.jinja",
        {
            "title": "Landing page",
        },
    )
