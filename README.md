
# Deconvolute Proxy

A security proxy for MCP servers, powered by the [Deconvolute SDK](https://github.com/deconvolute-labs/deconvolute).

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Status: MVP](https://img.shields.io/badge/status-MVP-orange.svg)]()
[![Deconvolute](https://img.shields.io/badge/powered%20by-deconvolute-blue.svg)](https://github.com/deconvolute-labs/deconvolute)

> [!Note]
> **Status:** MVP / proof of concept. Not production-ready.

## What this is

`deconvolute-proxy` sits between a closed AI agent runtime (such as Claude Cowork or Microsoft Copilot) and an MCP server (such as GitHub). It enforces a policy-as-code security layer on every tool call before the call reaches the upstream server.

```bash
Claude Cowork
    |
    | HTTPS (custom connector)
    v
deconvolute-proxy          <- policy enforced here
    |
    | Streamable HTTP over HTTPS
    v
GitHub MCP Server
```

The proxy exposes a [Streamable HTTP](https://modelcontextprotocol.io) MCP endpoint that any MCP-compatible client can connect to via URL. It requires no changes to the agent runtime and no access to the agent's source code.

## Why

Agent runtimes like Cowork connect directly to MCP servers. There is no layer between them where a security team can inspect or restrict tool calls at the protocol level.

`deconvolute-proxy` provides that layer. It enforces a least-privilege policy on the MCP tool call surface, independent of the agent runtime, the MCP server, and the underlying model.

For a detailed breakdown of what this addresses and where it fits relative to tools like NVIDIA OpenShell, see the [blog post](https://deconvolutelabs.com/blog/nvidia-openshell-mcp-protocol-layer?utm_source=github.com&utm_medium=readme_body&utm_campaign=proxy).
A hands-on demo using Claude Cowork and GitHub MCP is documented in [the demo repo](https://github.com/deconvolute-labs/mcp-deconvolute-demo/tree/main/scenarios/policy_enforcement_cowork) and explained with more background in the [blog post about the proxy](https://deconvolutelabs.com/blog/mcp-policy-enforcement-claude-cowork-live-demo?utm_source=github.com&utm_medium=readme_body&utm_campaign=proxy).

## How it works

On startup, the proxy connects to the upstream MCP server and wraps the session with [`mcp_guard`](https://docs.deconvolutelabs.com?utm_source=github.com&utm_medium=readme_body&utm_campaign=proxy) from the Deconvolute SDK. This does two things:

**Tool discovery:** The proxy fetches the upstream server's full tool list and filters it against `policy.yaml`. Tools not in the allowlist are hidden from the agent entirely.

**Tool execution:** Before forwarding any tool call to the upstream server, the proxy verifies it against the policy and the session snapshot. Blocked calls return an error to the agent. The event is written to a local SQLite audit log.

The SQLite state is managed automatically by the Deconvolute SDK. On first run, tool schemas are pinned. On subsequent runs, schemas are verified against the pinned baseline to detect tampering.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- A fine-grained PAT for the upstream MCP server
- [ngrok](https://ngrok.com) or similar tunnel to expose the proxy over HTTPS locally

## Setup

```bash
git clone https://github.com/deconvolute-labs/deconvolute-proxy
cd deconvolute-proxy

uv sync

cp .env.example .env
# Edit .env and set GITHUB_TOKEN and other required variables
```

## Configuration

### GitHub PAT

Create a fine-grained PAT at <https://github.com/settings/tokens>:

- Repository access: select only the repositories the agent should access
- Permissions: set the minimum required for your workflow

Scoping the token to the minimum required permissions provides a second layer of defense alongside the policy.

### Policy

Edit `policy-example.yaml` to define which tools the agent is allowed to call. Adjust it to match your use case and rename to `policy.yaml` to use it.

The policy supports:

- Allowlists and blocklists using tool name patterns including wildcards
- CEL conditions for argument-level enforcement (e.g. restrict a search tool to a specific repository)
- Default deny to block any tool not explicitly listed

Example policy with a CEL condition:

```yaml
version: "2.0"
default_action: block

servers:
  your-server-name:
    tools:
      - name: "list_issues"
        action: allow
      - name: "get_issue"
        action: allow
      - name: "search_code"
        action: allow
        condition: 'args.query.contains("repo:your-org/your-repo")'
      - name: "*"
        action: block
```

The server name must match what the upstream MCP server reports during the initialization handshake. Check the proxy startup logs on first run to confirm the name and adjust if needed.

See the [Deconvolute SDK docs](https://docs.deconvolutelabs.com?utm_source=github.com&utm_medium=readme_body&utm_campaign=proxy) for the full policy syntax reference.

## Running

Terminal 1:

```bash
uv run proxy
# MCP endpoint: http://127.0.0.1:8000/mcp/
# Health check:  http://127.0.0.1:8000/health
```

Terminal 2:

```bash
ngrok http 8000
# Copy the HTTPS forwarding URL
```

## Connecting from Cowork

1. Open Claude Desktop
2. Go to Settings > Connectors > Add custom connector
3. Enter your ngrok URL with trailing slash: `https://abc123.ngrok-free.app/mcp/`
4. Save

Only the tools permitted by `policy.yaml` are visible to the agent.

## Testing with the MCP inspector

```bash
npx @modelcontextprotocol/inspector http://127.0.0.1:8000/mcp/
```

Select Streamable HTTP transport, connect, then run List Tools to verify the policy is applied correctly.

## Audit log

The Deconvolute SDK writes all security events to a local SQLite database:

```bash
data/deconvolute_state.db
```

This includes tool discovery events, allowed calls, and blocked calls. The path is controlled by `DECONVOLUTE_CACHE_DIR` in `.env`.

Query recent events:

```bash
sqlite3 data/deconvolute_state.db \
  "SELECT event_type, json_extract(payload, '$.tool_name'),
   json_extract(payload, '$.status'), json_extract(payload, '$.reason')
   FROM audit_queue ORDER BY id DESC LIMIT 10;"
```

## Deployment to Cloud Run

For a persistent deployment accessible without ngrok:

1. Set `HOST=0.0.0.0` and `PORT=8080` in your environment
2. Set `GITHUB_TOKEN` and other secrets via Cloud Run Secret Manager
3. Mount a persistent volume at `DECONVOLUTE_CACHE_DIR` for SQLite state
4. Cloud Run provides the HTTPS URL directly

## Current limitations

This is an MVP under active development. Known limitations:

- **No auth on the proxy itself.** Any client with the proxy URL can connect. For production, add an API key check or OAuth layer in front of the proxy.
- **Single shared upstream session.** All downstream connections share one upstream session and one tool registry. Production deployments should isolate sessions per downstream client.
- **`secure_sse_session` not used.** The Deconvolute SDK's `secure_sse_session` context manager does not currently accept request headers, so the proxy uses the lower-level `streamablehttp_client` + `mcp_guard` pattern. DNS pinning and transport origin validation are not active in this version.
- **Single upstream server.** This proxy connects to one upstream MCP server. The enterprise platform architecture supports multiple proxies sharing a central policy store.

## Roadmap

Planned improvements:

- **Docker image** for one-command deployment without Python or uv
- **Per-session upstream isolation** so each downstream client gets its own tool registry
- **Auth layer** with API key and OAuth support for the proxy endpoint
- **Multi-server support** with a central policy store shared across proxy instances
- **Cloud Run Terraform module** for one-command production deployment

Contributions and feedback welcome via [GitHub Issues](https://github.com/deconvolute-labs/deconvolute-proxy/issues).

## Related

- [Deconvolute SDK](https://github.com/deconvolute-labs/deconvolute)
- [Deconvolute docs](https://docs.deconvolutelabs.com?utm_source=github.com&utm_medium=readme_related&utm_campaign=proxy)
- [Demo scenarios](https://github.com/deconvolute-labs/mcp-deconvolute-demo)
- Blog post: [How to Control What Your AI Agents Can Do](https://deconvolutelabs.com/blog/mcp-policy-enforcement-claude-cowork-live-demo?utm_source=github.com&utm_medium=readme_related&utm_campaign=proxy)
