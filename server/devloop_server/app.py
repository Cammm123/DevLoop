from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Annotated, AsyncIterator
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .analytics import dashboard
from .config import Settings
from .database import Database
from .models import BatchResult, EventBatch, EventIn, Kind, MilestoneIn, Source

_MAX_BODY_BYTES = 1_000_000
_bearer = HTTPBearer(auto_error=False)


class _BodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=413, detail="request body too large")


class RequestSecurityMiddleware:
    """Enforce body size on the ASGI stream and add private-response headers."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def secure_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        async def error_response(status_code: int, detail: str) -> None:
            response = JSONResponse(status_code=status_code, content={"detail": detail})
            await response(scope, receive, secure_send)

        content_lengths = [
            value for name, value in scope.get("headers", []) if name.lower() == b"content-length"
        ]
        if content_lengths:
            try:
                content_length = int(content_lengths[-1])
                if content_length < 0:
                    raise ValueError
            except ValueError:
                await error_response(400, "invalid content-length")
                return
            if content_length > self.max_body_bytes:
                await error_response(413, "request body too large")
                return

        total_size = 0

        async def limited_receive() -> Message:
            nonlocal total_size
            message = await receive()
            if message["type"] == "http.request":
                total_size += len(message.get("body", b""))
                if total_size > self.max_body_bytes:
                    # Never forward the limit-crossing chunk to request parsing
                    # or Pydantic schema validation.
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, secure_send)
        except _BodyTooLarge:
            if response_started:
                raise
            await error_response(413, "request body too large")


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    database = Database(config.database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.initialize()
        yield

    app = FastAPI(
        title="DevLoop Private API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.database = database
    app.add_middleware(RequestSecurityMiddleware, max_body_bytes=_MAX_BODY_BYTES)

    async def require_token(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> None:
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or not secrets.compare_digest(credentials.credentials, config.api_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )


    @app.get("/health")
    def health(response: Response) -> dict[str, str]:
        if not database.check():
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "unhealthy"}
        return {"status": "ok"}

    @app.post(
        "/v1/events/batch",
        response_model=BatchResult,
        dependencies=[Depends(require_token)],
    )
    def ingest(payload: EventBatch) -> BatchResult:
        inserted = database.insert_events(payload.events)
        return BatchResult(
            received=len(payload.events),
            inserted=inserted,
            duplicates=len(payload.events) - inserted,
        )

    @app.post(
        "/v1/milestones",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_token)],
    )
    def milestone(payload: MilestoneIn) -> dict[str, str]:
        event = EventIn(
            id=uuid4(),
            occurred_at=payload.occurred_at or datetime.now(timezone.utc),
            device_id=payload.device_id,
            source=Source.MANUAL,
            kind=Kind.MILESTONE,
            project=payload.project,
            magnitude=payload.magnitude,
            label=payload.title,
        )
        database.insert_events([event])
        return {"id": str(event.id), "status": "created"}

    @app.get("/v1/dashboard", dependencies=[Depends(require_token)])
    def get_dashboard(
        day: Annotated[date | None, Query(alias="date")] = None,
        timezone_name: Annotated[str, Query(alias="timezone", min_length=1, max_length=64)] = "UTC",
    ) -> dict[str, object]:
        try:
            zone = ZoneInfo(timezone_name)
            selected = day or datetime.now(zone).date()
            return dashboard(database, selected, timezone_name)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app
