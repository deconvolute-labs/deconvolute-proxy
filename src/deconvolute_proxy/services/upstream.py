from contextlib import AsyncExitStack
from typing import Any

import httpx
import mcp.types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from deconvolute import mcp_guard

from deconvolute_proxy.config import Settings
from deconvolute_proxy.logger import get_logger

logger = get_logger("upstream")

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"


class UpstreamService:
    """
    Manages the single outbound MCP session to the GitHub server.

    One instance per process. connect() is called once during Starlette lifespan
    startup; disconnect() is called once during shutdown. All downstream requests
    reuse self._session.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session: Any = None
        self._exit_stack: AsyncExitStack | None = None

    async def connect(self) -> None:
        """
        Opens the Streamable HTTP connection, initializes the MCP session, and
        wraps it with mcp_guard. Called once at startup; the session is held for
        the process lifetime.

        GitHub's MCP endpoint uses Streamable HTTP (POST-based), not legacy SSE
        (GET-based), so streamable_http_client is required.
        """
        self._exit_stack = AsyncExitStack()

        logger.debug("Opening HTTP client to %s", GITHUB_MCP_URL)
        http_client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self._settings.github_token}"},
        )
        await self._exit_stack.enter_async_context(http_client)

        read, write, _ = await self._exit_stack.enter_async_context(
            streamable_http_client(GITHUB_MCP_URL, http_client=http_client)
        )

        raw_session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )

        # Wrap first, then initialize. mcp_guard intercepts initialize() to
        # capture the server identity and enforce server-level policy. If the
        # server version violates policy, initialize() raises ServerIdentityError.
        logger.debug(
            "Wrapping session with mcp_guard (policy: %s)", self._settings.policy_path
        )
        self._session = mcp_guard(raw_session, policy_path=self._settings.policy_path)
        init_result = await self._session.initialize()
        logger.info("MCP session initialized.")
        logger.info("GitHub server name: %s", init_result.serverInfo.name)

    async def disconnect(self) -> None:
        """Tears down the session and HTTP connection. Called once at shutdown."""
        logger.debug("Closing upstream MCP session.")
        if self._exit_stack is not None:
            await self._exit_stack.aclose()

    async def list_tools(self) -> list[mcp.types.Tool]:
        """
        Returns the policy-filtered tool list. mcp_guard intercepts list_tools,
        hides blocked tools, and pins discovered tools to SQLite on first call.
        """
        logger.debug("Fetching tool list from upstream.")
        result = await self._session.list_tools()
        logger.info("Returning %d tool(s) to downstream client.", len(result.tools))
        return result.tools

    async def call_tool(self, name: str, arguments: dict) -> mcp.types.CallToolResult:
        """
        Forwards a tool call through mcp_guard. The guard performs policy and
        integrity checks; blocked calls return CallToolResult(isError=True).
        """
        logger.info("Tool call: %s", name)
        result = await self._session.call_tool(name, arguments)
        if result.isError:
            logger.warning("Tool call blocked or errored: %s", name)
        else:
            logger.debug("Tool call succeeded: %s", name)
        return result
