"""
FastAPI application entrypoint.

Creates the FastAPI() app, mounts the static directory, configures
Jinja2Templates, includes the pages and api routers, and runs a startup
check that warns (but never crashes) if Supabase, Cloudinary, or Gemini
environment variables are missing.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.routers import api, pages

# Resolved relative to this file, not the process working directory, so
# static file serving keeps working the same way locally and once deployed
# as a serverless function (e.g. on Vercel), where the working directory at
# request time is not guaranteed to be the project root.
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Bytwise", description="Cozy cafe and hidden gem discovery app.")

# Signed cookie session, used to hold in-progress signup data (username,
# email, password, OTP) between the "Get OTP" and "Verify" steps.
app.add_middleware(SessionMiddleware, secret_key=get_settings().session_secret_key)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(pages.router)
app.include_router(api.router)


@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException) -> Response:
    """
    On a page route (not /api/*), a 401 from require_user/require_admin
    redirects to the login page instead of showing a bare JSON error,
    matching how the original SPA sent unauthenticated visitors to Auth.tsx.
    API routes keep the plain JSON error response.
    """
    if exc.status_code == status.HTTP_401_UNAUTHORIZED and not request.url.path.startswith("/api/"):
        return RedirectResponse(url=f"/auth?next={request.url.path}", status_code=status.HTTP_303_SEE_OTHER)

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RuntimeError)
async def configuration_error_handler(request: Request, exc: RuntimeError) -> Response:
    """
    Renders a friendly page (or JSON for API routes) instead of a bare 500
    when Supabase, Cloudinary, or Gemini credentials are missing. This
    mirrors the original app's mock client, which kept the app usable in
    an unconfigured demo environment instead of crashing.
    """
    message = str(exc)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=503, content={"error": message})

    body = (
        "<html><head><title>Bytwise, setup needed</title></head>"
        "<body style='font-family: sans-serif; max-width: 640px; margin: 80px auto; padding: 0 20px;'>"
        "<h1>Almost there</h1>"
        f"<p>{message}</p>"
        "<p>Copy <code>.env.example</code> to <code>.env</code>, fill in your "
        "Supabase, Cloudinary, and Gemini keys, then restart the server.</p>"
        "</body></html>"
    )
    return HTMLResponse(status_code=503, content=body)


@app.on_event("startup")
def warn_on_missing_configuration() -> None:
    """
    Warns (does not crash) if Supabase, Cloudinary, or Gemini credentials
    are missing, reusing the is_*_configured properties from app.config.
    """
    settings = get_settings()

    if not settings.is_supabase_configured:
        print(
            "[startup warning] Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_ANON_KEY (or VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY) in "
            "your .env file. Pages that read or write shop and profile data will fail."
        )

    if not settings.is_cloudinary_configured:
        print(
            "[startup warning] Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in your .env file. Image "
            "uploads (shop photos, avatars) will fail until this is set."
        )

    if not settings.is_gemini_configured:
        print(
            "[startup warning] Gemini is not configured. Set GEMINI_API_KEY in your "
            ".env file. The 'Generate with AI' description button will fall back to "
            "a simple templated description instead of calling the Gemini API."
        )

    if not settings.is_email_configured:
        print(
            "[startup warning] Email is not configured. Set GMAIL_SMTP_USER and "
            "GMAIL_SMTP_PASSWORD (a Gmail app password) in your .env file. Signup "
            "OTP emails will fail to send until this is set."
        )


@app.get("/healthz")
def health_check() -> dict[str, str]:
    """Simple liveness check, not part of the original React app."""
    return {"status": "ok"}
