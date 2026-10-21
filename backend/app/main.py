import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import Response

from app.api import preview, runs, ws
from app.browser.factory import create_browser_driver
from app.config import Settings
from app.core.state import InvalidTransition
from app.core.store import RunNotFound
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import BrowserDriver
from app.interfaces.llm import LLMClient
from app.llm.openrouter_client import OpenRouterPool
from app.logging import configure_logging
from app.runtime import RunCapacityExceeded, RunService

logger = logging.getLogger("clevis")


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


class JsonCORSMiddleware(CORSMiddleware):
    def preflight_response(self, request_headers: Headers) -> Response:
        response = super().preflight_response(request_headers)
        if response.status_code == 400:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "cors_denied", "message": "CORS request denied."}},
                headers={
                    k: v
                    for k, v in response.headers.items()
                    if k not in {"content-length", "content-type"}
                },
            )
        return response


def create_app(
    settings: Settings | None = None,
    *,
    driver_factory: Callable[[], BrowserDriver] | None = None,
    llm_factory: Callable[[], LLMClient] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    service = RunService(
        settings,
        driver_factory or (lambda: create_browser_driver(settings)),
        llm_factory or FakeLLMClient,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        service.settings.validate_llm()
        if settings.agent_driver == "pinchtab":
            from app.browser.pinchtab_api import PinchtabAPI

            checker = PinchtabAPI(settings)
            try:
                await checker.health()
            finally:
                await checker.close()
        pool: OpenRouterPool | None = None
        if llm_factory is None and settings.llm_provider == "openrouter":
            pool = OpenRouterPool(settings)
            service.llm_factory = pool.session
        configure_logging(service.settings.log_level)
        try:
            yield
        finally:
            await service.shutdown()
            if pool is not None:
                await pool.close()

    application = FastAPI(title="Clevis runs API", lifespan=lifespan)
    application.state.service = service
    application.add_middleware(
        JsonCORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    application.include_router(runs.router)
    application.include_router(ws.router)
    application.include_router(preview.router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.exception_handler(RunCapacityExceeded)
    async def capacity(request: Request, exc: RunCapacityExceeded) -> JSONResponse:
        return error_response(
            429, "run_capacity_exceeded", "Maximum concurrent runs reached; try again later."
        )

    @application.exception_handler(RunNotFound)
    async def not_found(request: Request, exc: RunNotFound) -> JSONResponse:
        return error_response(404, "run_not_found", "Run not found.")

    @application.exception_handler(InvalidTransition)
    async def conflict(request: Request, exc: InvalidTransition) -> JSONResponse:
        return error_response(409, "invalid_transition", str(exc))

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo submitted inputs, which may contain private goals or later credentials.
        return error_response(422, "validation_error", "Request validation failed.")

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed."
        return error_response(exc.status_code, f"http_{exc.status_code}", message)

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        run_id = request.path_params.get("run_id", "unassigned")
        logger.error("request.failed", extra={"runId": run_id, "errorType": type(exc).__name__})
        return error_response(500, "internal_error", "Unexpected server error.")

    return application


app = create_app()
