FROM ghcr.io/astral-sh/uv:alpine

RUN apk update
RUN apk add bash postgresql-client

WORKDIR /code

## Program install steps
COPY ./pyproject.toml /code/pyproject.toml
COPY ./uv.lock /code/uv.lock

RUN uv sync --compile-bytecode

COPY . /code

RUN chmod +x /code/docker/saq/entrypoint.sh
ENTRYPOINT ["/code/docker/saq/entrypoint.sh"]
