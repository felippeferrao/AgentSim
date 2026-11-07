"""File-configured workspace logins for an explicit HTTPS deployment."""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path

SESSIONS = {}
LOCK = threading.Lock()
TTL = 12 * 3600


def config():
    name = os.environ.get("AGENTSIM_LOGIN_FILE")
    if not name:
        if os.environ.get("AGENTSIM_PUBLIC_URL"):
            raise ValueError("Public deployments require AGENTSIM_LOGIN_FILE.")
        return None
    data = json.loads(Path(name).read_text())
    users = data.get("users", [data])
    if not isinstance(users, list) or not users or len(users) > 100:
        raise ValueError("Invalid site login configuration.")
    names = set()
    for user in users:
        if not isinstance(user, dict) or not all(isinstance(user.get(k), str) and user[k] for k in ("username", "salt", "password_hash")):
            raise ValueError("Invalid site login configuration.")
        if user["username"] in names or len(user["username"]) > 100:
            raise ValueError("Invalid site login configuration.")
        names.add(user["username"])
        try:
            if len(bytes.fromhex(user["salt"])) < 16 or len(bytes.fromhex(user["password_hash"])) != 64:
                raise ValueError("Invalid site login configuration.")
        except ValueError:
            raise ValueError("Invalid site login configuration.") from None
    return {"users": users}


def authenticated(cookie):
    try:
        cookies = SimpleCookie(cookie or "")
        token = cookies["agentsim_session"].value
    except (KeyError, ValueError):
        return False
    with LOCK:
        return SESSIONS.get(token, 0) > time.time()


def login(username, password):
    data = config()
    if not data or not isinstance(username, str) or not isinstance(password, str) or len(password) > 1024:
        return None
    user = next((u for u in data["users"] if u["username"] == username), None)
    # Hash unknown users too so failed account lookups do not skip password work.
    candidate = user or data["users"][0]
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(candidate["salt"]), n=16384, r=8, p=1).hex()
    if not user or not hmac.compare_digest(digest, user["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    with LOCK:
        now = time.time()
        for old in list(SESSIONS):
            if SESSIONS[old] <= now:
                SESSIONS.pop(old, None)
        SESSIONS[token] = now + TTL
    return token


def logout(cookie):
    try:
        token = SimpleCookie(cookie or "")["agentsim_session"].value
    except (KeyError, ValueError):
        return
    with LOCK:
        SESSIONS.pop(token, None)


LOGIN_HTML = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in · WABIX AgentSim</title><style>body{margin:0;background:#f4f7fb;color:#142840;font:16px system-ui;display:grid;place-items:center;min-height:100vh}main{background:white;border-radius:20px;padding:40px;box-shadow:0 8px 40px #14284015;width:min(340px,80vw)}h1{font-size:26px}label{display:block;margin:20px 0}input{box-sizing:border-box;width:100%;padding:12px;border:1px solid #aebac8;border-radius:8px;margin-top:6px;font:inherit}button{background:#167a79;color:white;border:0;border-radius:8px;padding:12px;width:100%;font:inherit;cursor:pointer}#error{color:#a32525;min-height:24px}small{color:#65778b}</style><main><small>Powered by Wabix</small><h1>WABIX AgentSim</h1><p>Sign in to your workspace.</p><form id="login"><label>Username<input name="username" autocomplete="username" required maxlength="100"></label><label>Password<input name="password" type="password" autocomplete="current-password" required maxlength="1024"></label><button>Sign in</button><p id="error" role="alert"></p></form></main><script>document.querySelector('form').onsubmit=async(e)=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{const r=await fetch('/api/site/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});if(r.ok)location.replace('/');else document.querySelector('#error').textContent='Sign-in failed. Check your username and password.'}catch{document.querySelector('#error').textContent='Could not connect. Try again.'}finally{b.disabled=false}};</script></html>'''
