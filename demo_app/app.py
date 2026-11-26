"""SDD Demo Portal - the local application under test for the POC (NOT a production system).

UI : /login, /dashboard (server-rendered HTML, server-side validation)
API: /api/auth/login, /api/users[/{user_id}] - see specifications/api/openapi.yaml

Credentials come from environment variables (.env). State is in memory and resets on restart.
Set SDD_DEMO_LOGIN_ERROR to change the invalid-credentials message (used to demonstrate spec drift).
"""

from __future__ import annotations

import html
import itertools
import os
import secrets
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

ROLES = ("admin", "viewer")


def _login_error() -> str:
    return os.environ.get("SDD_DEMO_LOGIN_ERROR", "Invalid email or password")


def _accounts() -> dict[str, dict[str, str]]:
    return {
        os.environ.get("SDD_DEMO_USER_EMAIL", "qa.user@demo.local").lower():
            {"password": os.environ.get("SDD_DEMO_USER_PASSWORD", "Demo@12345"), "role": "viewer", "name": "QA User"},
        os.environ.get("SDD_DEMO_ADMIN_EMAIL", "admin@demo.local").lower():
            {"password": os.environ.get("SDD_DEMO_ADMIN_PASSWORD", "Admin@12345"), "role": "admin", "name": "Admin"},
    }


def create_app() -> FastAPI:
    app = FastAPI(title="SDD Demo Portal", version="1.0.0", docs_url=None, redoc_url=None)
    tokens: dict[str, str] = {}
    sessions: dict[str, str] = {}
    users: dict[int, dict[str, Any]] = {}
    ids = itertools.count(1)

    for email, acc in _accounts().items():
        uid = next(ids)
        users[uid] = {"id": uid, "name": acc["name"], "email": email, "role": acc["role"],
                      "created_at": datetime.now(UTC).isoformat(timespec="seconds")}

    # ------------------------------------------------------------------ helpers
    def validate_login(email: str, password: str) -> tuple[dict[str, str], str]:
        errors: dict[str, str] = {}
        if not email.strip():
            errors["email"] = "Email is required"
        if not password:
            errors["password"] = "Password is required"
        elif len(password) < 8:
            errors["password"] = "Password must be at least 8 characters"
        if errors:
            return errors, ""
        acc = _accounts().get(email.strip().lower())
        if not acc or not secrets.compare_digest(acc["password"], password):
            return {}, _login_error()
        return {}, ""

    def current_token(request: Request) -> str | None:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            if token in tokens:
                return token
        return None

    def unauthorized() -> JSONResponse:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    def validate_user(body: Any, partial: bool) -> str | None:
        if not isinstance(body, dict):
            return "Request body must be a JSON object"
        for field in ("name", "email", "role"):
            if field not in body:
                if partial:
                    continue
                return f"{field} is required"
            value = body[field]
            if not isinstance(value, str) or not value.strip():
                return f"{field} is required"
        if "name" in body and len(body["name"]) > 100:
            return "name must be at most 100 characters"
        if "email" in body and "@" not in body["email"]:
            return "email must be a valid email address"
        if "role" in body and body["role"] not in ROLES:
            return f"role must be one of: {', '.join(ROLES)}"
        return None

    def email_taken(email: str, exclude: int | None = None) -> bool:
        return any(u["email"].lower() == email.lower() and u["id"] != exclude for u in users.values())

    # ------------------------------------------------------------------ UI
    def login_page(email: str = "", errors: dict[str, str] | None = None, alert: str = "") -> HTMLResponse:
        errors = errors or {}
        def err(field: str) -> str:
            return f'<div class="field-error" id="{field}-error">{html.escape(errors[field])}</div>' \
                if field in errors else ""
        alert_html = f'<div role="alert" class="error">{html.escape(alert)}</div>' if alert else ""
        return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Sign in - SDD Demo Portal</title>
<style>body{{font-family:system-ui;background:#f4f6fb;display:grid;place-items:center;min-height:100vh;margin:0}}
form{{background:#fff;padding:32px;border-radius:12px;box-shadow:0 4px 18px #0002;width:320px;display:grid;gap:8px}}
input{{padding:8px;border:1px solid #bbb;border-radius:6px}}button{{padding:10px;background:#4f46e5;color:#fff;border:0;
border-radius:6px;cursor:pointer}}.field-error,.error{{color:#b91c1c;font-size:13px}}</style></head>
<body><main><form method="post" action="/login" novalidate>
<h1>Sign in</h1>{alert_html}
<label for="email">Email</label><input id="email" name="email" type="email" value="{html.escape(email)}">{err("email")}
<label for="password">Password</label><input id="password" name="password" type="password">{err("password")}
<button type="submit">Sign in</button></form></main></body></html>""")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/login", status_code=303)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/login", response_class=HTMLResponse)
    def get_login() -> HTMLResponse:
        return login_page()

    @app.post("/login", response_model=None)
    async def post_login(request: Request) -> Response:
        form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        email = form.get("email", [""])[0]
        password = form.get("password", [""])[0]
        errors, alert = validate_login(email, password)
        if errors or alert:
            return login_page(email, errors, alert)
        sid = secrets.token_urlsafe(16)
        sessions[sid] = email.lower()
        resp = RedirectResponse("/dashboard", status_code=303)
        resp.set_cookie("sdd_session", sid, httponly=True, samesite="lax")
        return resp

    @app.get("/dashboard", response_model=None)
    def dashboard(request: Request) -> Response:
        email = sessions.get(request.cookies.get("sdd_session", ""))
        if not email:
            return RedirectResponse("/login", status_code=303)
        return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Dashboard</title>
</head><body style="font-family:system-ui;padding:32px"><h1>Dashboard</h1><p>Signed in as {html.escape(email)}</p>
<form method="post" action="/logout"><button type="submit">Sign out</button></form></body></html>""")

    @app.post("/logout", include_in_schema=False)
    def logout(request: Request) -> RedirectResponse:
        sessions.pop(request.cookies.get("sdd_session", ""), None)
        return RedirectResponse("/login", status_code=303)

    # ------------------------------------------------------------------ API
    @app.post("/api/auth/login")
    async def api_login(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"detail": "Request body must be JSON"}, status_code=422)
        errors, alert = validate_login(str(body.get("email", "")), str(body.get("password", "")))
        if errors:
            return JSONResponse({"detail": next(iter(errors.values()))}, status_code=422)
        if alert:
            return JSONResponse({"detail": alert}, status_code=401)
        token = secrets.token_urlsafe(24)
        tokens[token] = str(body["email"]).lower()
        return JSONResponse({"access_token": token, "token_type": "bearer"})

    @app.get("/api/users")
    def list_users(request: Request) -> JSONResponse:
        if not current_token(request):
            return unauthorized()
        return JSONResponse(list(users.values()))

    @app.post("/api/users")
    async def create_user(request: Request) -> JSONResponse:
        if not current_token(request):
            return unauthorized()
        try:
            body = await request.json()
        except ValueError:
            body = None
        if err := validate_user(body, partial=False):
            return JSONResponse({"detail": err}, status_code=422)
        if email_taken(body["email"]):
            return JSONResponse({"detail": "Email already exists"}, status_code=409)
        uid = next(ids)
        users[uid] = {"id": uid, "name": body["name"], "email": body["email"], "role": body["role"],
                      "created_at": datetime.now(UTC).isoformat(timespec="seconds")}
        return JSONResponse(users[uid], status_code=201)

    @app.get("/api/users/{user_id}")
    def get_user(user_id: int, request: Request) -> JSONResponse:
        if not current_token(request):
            return unauthorized()
        if user_id not in users:
            return JSONResponse({"detail": "User not found"}, status_code=404)
        return JSONResponse(users[user_id])

    async def _update(user_id: int, request: Request, partial: bool) -> JSONResponse:
        if not current_token(request):
            return unauthorized()
        if user_id not in users:
            return JSONResponse({"detail": "User not found"}, status_code=404)
        try:
            body = await request.json()
        except ValueError:
            body = None
        if err := validate_user(body, partial=partial):
            return JSONResponse({"detail": err}, status_code=422)
        if "email" in body and email_taken(body["email"], exclude=user_id):
            return JSONResponse({"detail": "Email already exists"}, status_code=409)
        users[user_id].update({k: body[k] for k in ("name", "email", "role") if k in body})
        return JSONResponse(users[user_id])

    @app.put("/api/users/{user_id}")
    async def replace_user(user_id: int, request: Request) -> JSONResponse:
        return await _update(user_id, request, partial=False)

    @app.patch("/api/users/{user_id}")
    async def patch_user(user_id: int, request: Request) -> JSONResponse:
        return await _update(user_id, request, partial=True)

    @app.delete("/api/users/{user_id}", response_model=None)
    def delete_user(user_id: int, request: Request) -> Response:
        if not current_token(request):
            return unauthorized()
        if users.pop(user_id, None) is None:
            return JSONResponse({"detail": "User not found"}, status_code=404)
        return Response(status_code=204)

    return app


app = create_app()

if __name__ == "__main__":  # python -m demo_app.app
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("SDD_DEMO_PORT", "8765")))
