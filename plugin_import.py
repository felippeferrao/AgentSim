"""Interpret plugin ZIP manifests; run only an explicitly trusted local entry point."""

import base64
import hashlib
import io
import json
import re
import shutil
import stat
import sys
import zipfile
from pathlib import PurePosixPath

import auth
import external_mcp
from skill_files import parse_markdown


def unpack(encoded):
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 10_000_000:
            raise ValueError("ZIP limit is 10 MB.")
        archive = zipfile.ZipFile(io.BytesIO(raw))
        entries = archive.infolist()
        if len(entries) > 500 or sum(x.file_size for x in entries) > 20_000_000:
            raise ValueError("ZIP expands beyond 20 MB or 500 files.")
        files = {}
        for item in entries:
            path = PurePosixPath(item.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in item.filename
                or stat.S_ISLNK(item.external_attr >> 16)
            ):
                raise ValueError("Unsafe archive path or symlink.")
            if item.flag_bits & 1:
                raise ValueError("Encrypted ZIPs are not supported.")
            if not item.is_dir():
                if item.filename in files:
                    raise ValueError("Duplicate archive path.")
                files[item.filename] = archive.read(item)
        return raw, files
    except (zipfile.BadZipFile, ValueError, TypeError) as exc:
        raise ValueError(
            str(exc) if isinstance(exc, ValueError) else "Invalid ZIP archive."
        ) from None


def inspect(encoded):
    raw, files = unpack(encoded)
    candidates = [
        name
        for name in files
        if name.endswith(("/.mcp.json", "/mcp.json")) or name in (".mcp.json", "mcp.json")
    ]
    if len(candidates) != 1:
        raise ValueError("ZIP must contain one .mcp.json (or mcp.json) with an mcpServers mapping.")
    manifest_path = candidates[0]
    root = str(PurePosixPath(manifest_path).parent)
    root = "" if root == "." else root + "/"
    try:
        config = json.loads(files[manifest_path])
        servers = config.get("mcpServers", config)
        if not isinstance(servers, dict) or not 0 < len(servers) <= 10:
            raise ValueError("Plugin must define 1-10 MCP servers.")
        connections = []
        for name, entry in servers.items():
            if not isinstance(entry, dict) or not re.fullmatch(r"[a-z0-9-]{1,40}", name):
                raise ValueError(
                    "Plugin server ids must use lowercase letters, numbers and hyphens."
                )
            if entry.get("url"):
                headers = entry.get("headers", {})
                if len(headers) > 1:
                    raise ValueError("Use one access-key header per MCP server.")
                header = next(iter(headers), "")
                template = headers.get(header, "")
                if template and not re.fullmatch(
                    r"(?:Bearer )?\$\{(?:API_KEY|ACCESS_KEY|PLUGIN_ACCESS_KEY)\}", template
                ):
                    raise ValueError(
                        "Use an access-key placeholder, not an embedded secret, in plugin headers."
                    )
                connections.append(
                    {
                        "id": name,
                        "name": entry.get("name", name),
                        "transport": "streamable-http",
                        "url": entry["url"],
                        "authType": "bearer"
                        if header.lower() == "authorization" and template.startswith("Bearer ")
                        else "header"
                        if header
                        else "none",
                        "headerName": header,
                        "keyRequired": bool(header),
                    }
                )
            else:
                command = entry.get("command", "")
                args = entry.get("args", [])
                if (
                    command not in ("python", "python3", "node")
                    or not isinstance(args, list)
                    or len(args) != 1
                    or not isinstance(args[0], str)
                ):
                    raise ValueError(
                        "Local plugins must use python/python3/node with one packaged script argument; package installers and shell commands are not run."
                    )
                script = (
                    args[0].replace("${CLAUDE_PLUGIN_ROOT}/", "").replace("${PLUGIN_ROOT}/", "")
                )
                path = PurePosixPath(script)
                if path.is_absolute() or ".." in path.parts or root + script not in files:
                    raise ValueError("Local MCP entry point must exist inside the ZIP.")
                environment = entry.get("env", {})
                if not isinstance(environment, dict) or any(
                    not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k)
                    or v not in ("${API_KEY}", "${ACCESS_KEY}", "${PLUGIN_ACCESS_KEY}")
                    for k, v in environment.items()
                ):
                    raise ValueError(
                        "Plugin env entries must map variable names to an access-key placeholder."
                    )
                connections.append(
                    {
                        "id": name,
                        "name": entry.get("name", name),
                        "transport": "stdio",
                        "envKeys": list(environment),
                        "command": command,
                        "script": script,
                        "sourcePreview": files[root + script].decode("utf-8", errors="replace")[
                            :20000
                        ],
                        "root": root,
                        "keyRequired": bool(entry.get("env")),
                        "url": "Local plugin · " + script,
                    }
                )
        skills = [
            parse_markdown(value.decode("utf-8"))
            for name, value in files.items()
            if name.endswith("/SKILL.md") or name == "SKILL.md"
        ]
        return {
            "digest": hashlib.sha256(raw).hexdigest(),
            "connections": connections,
            "skills": skills,
            "files": list(files),
            "runsLocalCode": any(c["transport"] == "stdio" for c in connections),
        }
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, TypeError):
        raise ValueError("Invalid MCP plugin manifest.") from None


def install(encoded, access_key, trust_local=False):
    description = inspect(encoded)
    if description["runsLocalCode"] and not trust_local:
        raise ValueError("Review and explicitly trust the local plugin code before importing it.")
    if (
        not isinstance(access_key, str)
        or "\n" in access_key
        or "\r" in access_key
        or len(access_key) > 8192
    ):
        raise ValueError("Invalid access key.")
    if any(c["keyRequired"] for c in description["connections"]) and not access_key:
        raise ValueError("This plugin requires an access key.")
    _, files = unpack(encoded)
    package = auth.LOCAL / "plugins" / description["digest"]
    # Validate all remote configurations before mutating the registry.
    old = external_mcp.registry()
    if any(c["id"] in old for c in description["connections"]):
        raise ValueError(
            "A connection id already exists; remove or rename it before importing this plugin."
        )
    imported = []
    try:
        for c in description["connections"]:
            if c["transport"] == "streamable-http":
                imported.append(external_mcp.save_connection({**c, "credential": access_key}))
            else:
                executable = (
                    sys.executable if c["command"].startswith("python") else shutil.which("node")
                )
                if not executable:
                    raise ValueError("Node.js is required by this plugin.")
                package.mkdir(parents=True, exist_ok=True, mode=0o700)
                for name, data in files.items():
                    target = package / name
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    target.write_bytes(data)
                    target.chmod(0o600)
                import uuid

                record = {
                    "id": c["id"],
                    "name": c["name"],
                    "transport": "stdio",
                    "url": c["url"],
                    "authType": "plugin-key" if access_key else "none",
                    "headerName": "",
                    "credential": access_key,
                    "envKeys": c.get("envKeys", []),
                    "command": executable,
                    "script": str(package / (c["root"] + c["script"])),
                    "cwd": str(package / c["root"]),
                    "revision": str(uuid.uuid4()),
                    "tools": [],
                    "status": "Not checked",
                    "pluginDigest": description["digest"],
                }
                records = external_mcp.registry()
                records[c["id"]] = record
                auth.store("mcp", {"connections": records})
                imported.append(external_mcp.public(record))
    except Exception:
        auth.store("mcp", {"connections": old})
        raise
    return description, imported
