"""Independent public-client OAuth. Never reads Codex or Cortex credentials."""

import base64
import hashlib
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

import httpx
import jwt

LOCAL = Path(__file__).parent / ".local"
PENDING = {}
AUTH = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"


def load(name):
    p = LOCAL / (name + ".json")
    return json.loads(p.read_text()) if p.exists() else {}


def store(name, data):
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    path = LOCAL / (name + ".json")
    tmp = path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def start(port):
    host = load("host")
    if not host:
        host = {"id": "urn:uuid:" + str(uuid.uuid4())}
        store("host", host)
    old = load("oauth")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    redirect = f"http://127.0.0.1:{port}/auth/callback"
    client = old.get("client_id", "dynamic_agent_client")
    PENDING.clear()
    PENDING[state] = {
        "verifier": verifier,
        "nonce": nonce,
        "redirect": redirect,
        "client": client,
        "time": time.time(),
        "subject": old.get("subject"),
    }
    q = {
        "client_id": client,
        "ext_agent_host_id": host["id"],
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct",
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("="),
    }
    if client == "dynamic_agent_client":
        q["agent_name_hint"] = "WABIX AgentSim"
    elif old.get("id_token"):
        q["id_token_hint"] = old["id_token"]
    return AUTH + "/api/accounts/authorize?" + urlencode(q)


def callback(q):
    attempt = PENDING.pop(q.get("state", ""), None)
    if not attempt or time.time() - attempt["time"] > 600:
        raise ValueError("Sign-in expired or state did not match. Start again.")
    if q.get("error"):
        raise ValueError("Sign-in was not approved. You can try again.")
    client = q.get("client_id", attempt["client"])
    if client == "dynamic_agent_client" or (
        attempt["client"] != "dynamic_agent_client" and client != attempt["client"]
    ):
        raise ValueError("Registration did not return the expected client id.")
    r = httpx.post(
        AUTH + "/api/accounts/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client,
            "code": q.get("code", ""),
            "code_verifier": attempt["verifier"],
            "redirect_uri": attempt["redirect"],
            "resource": RESOURCE,
        },
        timeout=30,
    )
    if r.status_code != 200:
        raise ValueError("Code exchange failed. Start sign-in again.")
    token = r.json()
    jwks = jwt.PyJWKClient(AUTH + "/.well-known/jwks.json")
    key = jwks.get_signing_key_from_jwt(token["id_token"])
    claims = jwt.decode(
        token["id_token"],
        key.key,
        algorithms=["RS256"],
        audience=client,
        issuer=AUTH,
        options={"require": ["exp", "sub", "iss", "aud", "nonce"]},
    )
    if claims["nonce"] != attempt["nonce"] or (
        attempt["subject"] and claims["sub"] != attempt["subject"]
    ):
        raise ValueError("The account identity did not match. Previous credentials were kept.")
    token.update(
        {
            "client_id": client,
            "subject": claims["sub"],
            "email": claims.get("email"),
            "expires_at": time.time() + token.get("expires_in", 3600),
            "scopes": token.get("scope", "").split(),
        }
    )
    store("oauth", token)
    if "chatgpt.tokens.use.direct" not in token["scopes"]:
        raise ValueError(
            "Signed in, but ChatGPT plan permission was not granted. Sign in again to allow plan use."
        )


def access():
    t = load("oauth")
    if "chatgpt.tokens.use.direct" not in t.get("scopes", []):
        raise ValueError("Continue with ChatGPT first and allow plan usage.")
    if t.get("expires_at", 0) < time.time() + 60:
        r = httpx.post(
            AUTH + "/api/accounts/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": t["client_id"],
                "refresh_token": t.get("refresh_token", ""),
                "resource": RESOURCE,
            },
            timeout=30,
        )
        if r.status_code != 200:
            raise ValueError("Please sign in again. Token refresh failed.")
        fresh = r.json()
        t.update(fresh)
        t["expires_at"] = time.time() + fresh.get("expires_in", 3600)
        if "scope" in fresh:
            t["scopes"] = fresh["scope"].split()
        store("oauth", t)
    if "chatgpt.tokens.use.direct" not in t.get("scopes", []):
        raise ValueError("ChatGPT plan permission is missing. Sign in again.")
    return t["access_token"]


def settings():
    return load("provider") or {
        "provider": "demo",
        "model": "",
        "base_url": "https://api.openai.com/v1",
    }


def public_settings():
    s = settings()
    s.pop("api_key", None)
    s["has_key"] = bool(load("provider").get("api_key"))
    t = load("oauth")
    s["oauth_connected"] = bool(
        t.get("access_token") and "chatgpt.tokens.use.direct" in t.get("scopes", [])
    )
    return s
