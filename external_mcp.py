"""User-configured Streamable HTTP MCP connections; secrets stay in .local/."""

import asyncio
import hashlib
import json
import os
import re
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
import jsonschema
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

import auth

LOCK = threading.RLock()


def registry():
    return auth.load("mcp").get("connections", {})


def public(record):
    return {
        k: v for k, v in record.items() if k not in {"credential", "command", "script", "cwd"}
    } | {"hasCredential": bool(record.get("credential"))}


def connections():
    return [public(r) for r in registry().values()]


def save_connection(body):
    with LOCK:
        records = registry()
        ident = body.get("id", "")
        if (
            not isinstance(ident, str)
            or not re.fullmatch(r"[a-z0-9-]{1,60}", ident)
            or ident == "documents"
        ):
            raise ValueError(
                "Choose a connection id using lowercase letters, numbers and hyphens. “documents” is reserved."
            )
        if not isinstance(body.get("name"), str) or not 0 < len(body["name"]) <= 80:
            raise ValueError("Give the connection a name (1–80 characters).")
        endpoint = body.get("url", "")
        if not isinstance(endpoint, str) or len(endpoint) > 2048:
            raise ValueError("Enter an MCP endpoint URL.")
        u = urlsplit(endpoint)
        if not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError(
                "Use an endpoint URL without credentials, query parameters or fragments."
            )
        if u.scheme != "https" and not (
            u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1")
        ):
            raise ValueError(
                "Use HTTPS for an external server, or HTTP on loopback for a local server."
            )
        kind = body.get("authType", "none")
        header = body.get("headerName", "")
        if kind not in ("none", "bearer", "header"):
            raise ValueError("Choose no authentication, Bearer token or a custom header.")
        if kind == "header" and (
            not isinstance(header, str)
            or not re.fullmatch(r"[A-Za-z0-9-]{1,80}", header)
            or header.lower()
            in (
                "host",
                "content-type",
                "accept",
                "mcp-session-id",
                "mcp-protocol-version",
                "connection",
                "content-length",
                "transfer-encoding",
                "cookie",
            )
        ):
            raise ValueError(
                "Choose a custom credential header such as X-API-Key. Protocol headers are reserved."
            )
        if kind != "header":
            header = ""
        old = records.get(ident, {})
        credential = body.get("credential", "")
        if (
            not isinstance(credential, str)
            or len(credential) > 8192
            or "\n" in credential
            or "\r" in credential
        ):
            raise ValueError("Enter a single-line credential (up to 8192 characters).")
        same_target = (
            old.get("url") == endpoint
            and old.get("authType") == kind
            and old.get("headerName", "") == header
        )
        if not credential and same_target and not body.get("clearCredential"):
            credential = old.get("credential", "")
        if kind == "none" or body.get("clearCredential"):
            credential = ""
        if kind != "none" and not credential:
            raise ValueError("Enter the credential locally, or choose no authentication.")
        if ident not in records and len(records) >= 20:
            raise ValueError("Use at most 20 external connections.")
        # Editing a target revokes the discovered inventory. Discovery never grants tools.
        record = {
            "id": ident,
            "name": body["name"],
            "transport": "streamable-http",
            "url": endpoint,
            "authType": kind,
            "headerName": header,
            "credential": credential,
            "revision": str(uuid.uuid4()),
            "tools": [],
            "status": "Not checked",
        }
        records[ident] = record
        auth.store("mcp", {"connections": records})
        return public(record)


def remove(ident):
    with LOCK:
        records = registry()
        if ident not in records:
            raise ValueError("Connection not found.")
        del records[ident]
        auth.store("mcp", {"connections": records})


def redact(value, record):
    secret = record.get("credential")
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[credential removed]")
    if isinstance(value, dict):
        return {k: redact(v, record) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, record) for v in value]
    return value


def failure(exc):
    if isinstance(exc, BaseExceptionGroup):
        return failure(exc.exceptions[0])
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return "MCP access denied. Check the credential and server permissions."
        if 300 <= status < 400:
            return "MCP redirects are blocked. Enter the final endpoint URL."
        return f"MCP server returned HTTP {status}. Check its endpoint and availability."
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return "MCP request timed out. Check the server and try again."
    return (
        "MCP request failed. Check the endpoint, Streamable HTTP support and server availability."
    )


@asynccontextmanager
async def transport(record, headers):
    if record.get("transport") == "stdio":
        params = StdioServerParameters(
            command=record["command"],
            args=[record["script"]],
            cwd=record["cwd"],
            env={
                "PATH": os.environ.get("PATH", ""),
                **{name: record.get("credential", "") for name in record.get("envKeys", [])},
                "PLUGIN_ACCESS_KEY": record.get("credential", ""),
                "API_KEY": record.get("credential", ""),
                "ACCESS_KEY": record.get("credential", ""),
            },
        )
        async with stdio_client(params) as (reader, writer):
            yield reader, writer, None
    else:
        async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=False) as http:
            async with streamable_http_client(record["url"], http_client=http) as streams:
                yield streams


async def exchange(record, tool_name=None, arguments=None):
    headers = {}
    if record["authType"] == "bearer":
        headers["Authorization"] = "Bearer " + record["credential"]
    elif record["authType"] == "header":
        headers[record["headerName"]] = record["credential"]

    async def request():
        # No redirects: never forward an MCP credential to another destination.
        async with transport(record, headers) as (reader, writer, _):
            async with ClientSession(
                reader, writer, read_timeout_seconds=timedelta(seconds=15)
            ) as session:
                await session.initialize()
                if tool_name is None:
                    tools = []
                    cursor = None
                    seen = set()
                    for _ in range(20):
                        page = await session.list_tools(cursor=cursor)
                        for t in page.tools:
                            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", t.name) or t.name in seen:
                                raise ValueError(
                                    "The MCP server returned an invalid or duplicate tool name."
                                )
                            seen.add(t.name)
                            schema = t.inputSchema
                            if not isinstance(schema, dict) or schema.get("type") != "object":
                                raise ValueError("MCP tools must use an object input schema.")

                            def check_refs(value):
                                if isinstance(value, dict):
                                    if "$ref" in value and (
                                        not isinstance(value["$ref"], str)
                                        or not value["$ref"].startswith("#")
                                    ):
                                        raise ValueError(
                                            "Remote JSON Schema references are not supported. Use a self-contained schema."
                                        )
                                    for child in value.values():
                                        check_refs(child)
                                elif isinstance(value, list):
                                    for child in value:
                                        check_refs(child)

                            check_refs(schema)
                            jsonschema.Draft202012Validator.check_schema(schema)
                            tools.append(
                                {
                                    "id": t.name,
                                    "name": t.title or t.name,
                                    "description": t.description or "External MCP tool.",
                                    "inputSchema": schema,
                                }
                            )
                        if len(tools) > 100 or len(json.dumps(tools)) > 100000:
                            raise ValueError(
                                "This server has too many tools or its schemas are too large (limit 100 tools / 100 KB)."
                            )
                        cursor = page.nextCursor
                        if not cursor:
                            return redact(tools, record)
                    raise ValueError("MCP tool discovery exceeded the pagination limit.")
                result = await session.call_tool(tool_name, arguments or {})
                if result.isError:
                    raise ValueError(
                        "The MCP tool reported an error. Check its arguments and server permissions."
                    )
                content = "\n".join(
                    getattr(c, "text", "[Non-text MCP content]") for c in result.content
                )
                return redact(content[:32000], record)

    try:
        return await asyncio.wait_for(request(), timeout=20)
    except ValueError as exc:
        raise ValueError(redact(str(exc), record)) from None
    except Exception as exc:
        raise ValueError(failure(exc)) from None


async def discover(ident):
    record = registry().get(ident)
    if not record:
        raise ValueError("Connection not found.")
    try:
        tools = await exchange(record)
        for tool in tools:
            tool["connectionRevision"] = record["revision"]
    except ValueError as exc:
        with LOCK:
            records = registry()
            if records.get(ident) == record:
                records[ident]["status"] = str(exc)
                auth.store("mcp", {"connections": records})
        raise
    with LOCK:
        records = registry()
        if records.get(ident) != record:
            raise ValueError("The connection changed during discovery. Check it again.")
        records[ident]["tools"] = tools
        records[ident]["status"] = "Connected"
        auth.store("mcp", {"connections": records})
        return public(records[ident])


def fingerprint(tool):
    return hashlib.sha256(json.dumps(tool, sort_keys=True).encode()).hexdigest()


async def call(ident, name, arguments, grants, expected_tool):
    if ident + ":" + name not in grants:
        raise ValueError("This agent is not allowed to use that MCP tool.")
    record = registry().get(ident)
    if not record:
        raise ValueError("This MCP connection was removed. Choose a connection again.")
    current = next((t for t in record["tools"] if t["id"] == name), None)
    if not current or fingerprint(current) != fingerprint(expected_tool):
        raise ValueError("This MCP tool changed. Discover tools and explicitly assign it again.")
    try:
        jsonschema.Draft202012Validator(current["inputSchema"]).validate(arguments)
    except jsonschema.ValidationError:
        raise ValueError("MCP arguments do not match the discovered input schema.") from None
    return await exchange(record, name, arguments)
