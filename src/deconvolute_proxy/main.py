import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

# load_dotenv() must run before Settings() is instantiated so that os.environ
# is populated for both pydantic-settings and the Deconvolute SDK.
load_dotenv()

from deconvolute_proxy.handlers import mcp as mcp_handler  # noqa: E402
from deconvolute_proxy.config import get_settings  # noqa: E402
from deconvolute_proxy.logger import get_logger  # noqa: E402
from deconvolute_proxy.services.upstream import UpstreamService  # noqa: E402
from deconvolute_proxy.logger import configure_logging, get_logger

configure_logging()
logger = get_logger()


@asynccontextmanager
async def lifespan(app: Starlette):
    settings = get_settings()

    # Ensure the SDK reads the configured cache dir and API key from os.environ.
    # pydantic-settings populates its own model but does not write back to the
    # environment, so we set these explicitly for the SDK's internal os.getenv() calls.
    os.environ["DECONVOLUTE_CACHE_DIR"] = settings.deconvolute_cache_dir
    if settings.deconvolute_api_key:
        os.environ["DECONVOLUTE_API_KEY"] = settings.deconvolute_api_key

    logger.info("Connecting to upstream GitHub MCP server...")
    service = UpstreamService(settings)
    await service.connect()
    logger.info("Upstream session ready. Policy: %s", settings.policy_path)

    app.state.upstream = service
    mcp_handler.upstream_service = service

    async with mcp_handler.session_manager.run():
        logger.info(
            "Proxy listening on http://%s:%d — MCP endpoint: /mcp  Health: /health",
            settings.host,
            settings.port,
        )
        yield

    logger.info("Shutting down upstream session.")
    await service.disconnect()


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def mcp_asgi(scope: Any, receive: Any, send: Any) -> None:
    await mcp_handler.session_manager.handle_request(scope, receive, send)


app = Starlette(
    lifespan=lifespan,
    routes=[
        Mount("/mcp", app=mcp_asgi),
        Route("/health", endpoint=health, methods=["GET"]),
    ],
)


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "deconvolute_proxy.main:app",
        host=settings.host,
        port=settings.port,
    )
