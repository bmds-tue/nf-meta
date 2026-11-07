"""Access control for the editor's HTTP server: a host check on every request
and a session token on every API request."""

import secrets
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

TOKEN_HEADER = "X-NF-Meta-Token"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
WILDCARD_HOSTS = frozenset({"0.0.0.0", "::", ""})


def new_token() -> str:
    """A random token for one editor session."""
    return secrets.token_urlsafe(32)


def configure_access(app: FastAPI, token: str | None, bind_host: str | None = None) -> None:
    """Require `token` on API requests and accept requests addressed to a
    loopback name or to `bind_host`. A wildcard `bind_host` (`0.0.0.0`, `::`)
    accepts any host name; the token is still required."""
    app.state.token = token
    if bind_host is not None and bind_host.strip("[]") in WILDCARD_HOSTS:
        app.state.allowed_hosts = None
    else:
        app.state.allowed_hosts = LOOPBACK_HOSTS | ({bind_host.strip("[]").lower()} if bind_host else set())


def host_name(host_header: str) -> str:
    """The name in a `Host` header, without its port or IPv6 brackets."""
    if host_header.startswith("["):
        return host_header[1 : host_header.find("]")] if "]" in host_header else host_header
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


async def guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Middleware: 400 for a host not allowed, 401 for an API request without
    the session's token. Refuses API requests when no token is configured."""
    state = request.app.state
    allowed = getattr(state, "allowed_hosts", LOOPBACK_HOSTS)
    if allowed is not None and host_name(request.headers.get("host", "")).lower() not in allowed:
        return JSONResponse(status_code=400, content={"detail": "Invalid host"})
    if request.url.path.startswith("/api/"):
        expected = getattr(state, "token", None)
        given = request.headers.get(TOKEN_HEADER, "")
        if not expected or not secrets.compare_digest(given.encode(), expected.encode()):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid editor token"})
    return await call_next(request)
