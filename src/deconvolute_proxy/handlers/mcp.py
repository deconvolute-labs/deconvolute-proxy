from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from deconvolute_proxy.logger import get_logger

logger = get_logger("handlers.mcp")

# Injected by main.py lifespan before any requests are handled.
upstream_service: Any = None

mcp_server = Server("deconvolute-proxy")
session_manager = StreamableHTTPSessionManager(app=mcp_server, stateless=False)


@mcp_server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    logger.debug("Received list_tools request.")
    return await upstream_service.list_tools()


@mcp_server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    logger.debug("Received call_tool request: %s", name)
    result = await upstream_service.call_tool(name, arguments)
    return result.content
