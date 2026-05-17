import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routers import meals, scan, users


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event("startup"))
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🥗 NutriOS API v{app.version} started")
    yield
    print("NutriOS API shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NutriOS API",
    version="1.0.0",
    description="AI-powered calorie & nutrition tracker for Telegram Mini App",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — Telegram Mini Apps open from various t.me / telegram.org domains
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API routers  (registered BEFORE static mount so they always win)
# ---------------------------------------------------------------------------

app.include_router(users.router)   # prefix="/users" — auth + profile endpoints
app.include_router(meals.router)   # no prefix — /meals /daily/today /water /steps /foods /streak
app.include_router(scan.router)    # prefix="/scan"

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"], summary="Health check")
async def health_check() -> dict:
    """Lightweight liveness probe used by Railway / Docker / uptime monitors."""
    return {"status": "ok", "version": app.version}

# ---------------------------------------------------------------------------
# Static files — Mini App
#
# Project layout (local dev and Docker):
#   nutrios/
#   ├── backend/     ← uvicorn runs here  (WORKDIR /app in Dockerfile)
#   └── miniapp/     ← index.html, style.css, app.js
#
# Mounted at /static (NOT at "/") so API routes are never shadowed.
# Set your Telegram Mini App URL to:  https://<your-railway-domain>/static/index.html
#
# Override at deploy time:  MINIAPP_DIR=/path/to/miniapp
# ---------------------------------------------------------------------------

_default_miniapp_dir = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "miniapp")
)
MINIAPP_DIR: str = os.environ.get("MINIAPP_DIR", _default_miniapp_dir)

if os.path.isdir(MINIAPP_DIR):
    app.mount("/static", StaticFiles(directory=MINIAPP_DIR, html=True), name="miniapp")
    print(f"📁 Mini App served from '{MINIAPP_DIR}' at /static")
else:
    print(
        f"⚠️  miniapp directory not found at '{MINIAPP_DIR}' — "
        "static files will not be served. Set MINIAPP_DIR env var to override."
    )

# ---------------------------------------------------------------------------
# Root — redirect to Mini App or API docs (fallback)
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    """Redirect browser to the Mini App, or /docs if miniapp/ isn't mounted."""
    if os.path.isdir(MINIAPP_DIR):
        return RedirectResponse(url="/static/index.html")
    return RedirectResponse(url="/docs")
