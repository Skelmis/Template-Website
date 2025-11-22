from collections.abc import AsyncGenerator
from http import HTTPMethod
from typing import TypeVar, Generic, Any

import httpx
from httpx_retries import RetryTransport, Retry
from pydantic import BaseModel, Field

from template.crud.controller import SearchRequestModel, SearchModel

MODEL_IN = TypeVar("MODEL_IN")
MODEL_OUT = TypeVar("MODEL_OUT")
MODEL_PATCH_IN = TypeVar("MODEL_PATCH_IN")


class GetAllResponseModel(BaseModel):
    data: list[MODEL_OUT | dict]  # type: ignore
    next_cursor: str | None = None


class GetCountResponseModel(BaseModel):
    total_records: int = Field(
        description="The total number of records available to the current requester"
    )


class CRUDClient(Generic[MODEL_IN, MODEL_OUT]):
    def __init__(
        self,
        base_url: str,
        dto_out: type[MODEL_OUT],
        *,
        headers: dict | None = None,
        cookies: dict | None = None,
        maximum_retries_before_giving_up: int = 5,
        maximum_retry_wait_between_requests: float = 60,
    ):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            cookies=cookies,
            # Automatically retry 429's as per response headers
            transport=RetryTransport(
                retry=Retry(
                    backoff_factor=0.5,
                    respect_retry_after_header=True,
                    total=maximum_retries_before_giving_up,
                    max_backoff_wait=maximum_retry_wait_between_requests,
                    allowed_methods=[
                        HTTPMethod.HEAD,
                        HTTPMethod.OPTIONS,
                        HTTPMethod.TRACE,
                        HTTPMethod.GET,
                        HTTPMethod.POST,
                        HTTPMethod.PUT,
                        HTTPMethod.PATCH,
                        HTTPMethod.DELETE,
                    ],
                )
            ),
        )
        self.dto_out: type[MODEL_OUT] = dto_out

    async def get_all_records_as_list(self, page_size: int = 500) -> list[MODEL_OUT]:
        data = []
        async for entry in self.get_all_records(page_size=page_size):
            data.extend(entry)
        return data

    async def get_all_records(
        self, page_size: int = 500
    ) -> AsyncGenerator[list[MODEL_OUT], None]:
        initial_response: httpx.Response = await self.client.get(
            f"/?_page_size={page_size}"
        )
        initial_response.raise_for_status()
        raw_data = initial_response.json()
        resp_data: GetAllResponseModel = GetAllResponseModel(
            next_cursor=raw_data["next_cursor"],
            data=[self.dto_out(**row) for row in raw_data["data"]],
        )
        yield resp_data.data

        next_cursor = resp_data.next_cursor
        while next_cursor is not None:
            initial_response: httpx.Response = await self.client.get(
                f"/?_next_cursor={next_cursor}&_page_size={page_size}"
            )
            initial_response.raise_for_status()
            raw_data = initial_response.json()
            resp_data: GetAllResponseModel = GetAllResponseModel(
                next_cursor=raw_data["next_cursor"],
                data=[self.dto_out(**row) for row in raw_data["data"]],
            )
            yield resp_data.data
            next_cursor = resp_data.next_cursor

    async def get_total_record_count(self) -> GetCountResponseModel:
        resp = await self.client.get("/meta/count")
        resp.raise_for_status()
        return GetCountResponseModel(**resp.json())

    async def get_record(self, object_id: Any) -> MODEL_OUT:
        resp = await self.client.get(f"/{object_id}")
        resp.raise_for_status()
        return self.dto_out(**resp.json())

    async def delete_record(self, object_id: Any) -> None:
        delete_resp = await self.client.delete(f"/{object_id}")
        delete_resp.raise_for_status()
        return None

    async def create_record(self, data: MODEL_IN) -> MODEL_OUT:
        create_resp = await self.client.post(
            "/",
            data=data.model_dump_json(),
        )
        create_resp.raise_for_status()
        return self.dto_out(**create_resp.json())

    async def patch_record(self, object_id: Any, data: MODEL_PATCH_IN) -> MODEL_OUT:
        create_resp = await self.client.patch(
            f"/{object_id}",
            data=data.model_dump_json(exclude_unset=True),
        )
        create_resp.raise_for_status()
        return self.dto_out(**create_resp.json())

    async def get_search_filters(self) -> SearchRequestModel:
        resp = await self.client.get(f"/search/filters")
        resp.raise_for_status()
        return SearchRequestModel(**resp.json())

    async def search_records_as_list(
        self, search: SearchModel, page_size: int = 500
    ) -> list[MODEL_OUT]:
        data = []
        async for entry in self.search_records(search=search, page_size=page_size):
            data.extend(entry)
        return data

    async def search_records(self, search: SearchModel, page_size: int = 500):
        initial_response: httpx.Response = await self.client.post(
            f"/search?_page_size={page_size}",
            data=search.model_dump_json(),
        )
        initial_response.raise_for_status()
        raw_data = initial_response.json()
        resp_data: GetAllResponseModel = GetAllResponseModel(
            next_cursor=raw_data["next_cursor"],
            data=[self.dto_out(**row) for row in raw_data["data"]],
        )
        yield resp_data.data

        next_cursor = resp_data.next_cursor
        while next_cursor is not None:
            initial_response: httpx.Response = await self.client.post(
                f"/search?_next_cursor={next_cursor}&_page_size={page_size}",
                data=search.model_dump_json(),
            )
            initial_response.raise_for_status()
            raw_data = initial_response.json()
            resp_data: GetAllResponseModel = GetAllResponseModel(
                next_cursor=raw_data["next_cursor"],
                data=[self.dto_out(**row) for row in raw_data["data"]],
            )
            yield resp_data.data
            next_cursor = resp_data.next_cursor
