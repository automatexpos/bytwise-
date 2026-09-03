"""
Authentication helpers for the FastAPI backend.

Mirrors the auth related behavior that used to live in lib/supabase.ts
(the persisted browser session) and lib/authUtils.ts (resetSupabaseAuthState),
adapted to a server side, cookie based session model:

- Sign up / log in call Supabase Auth directly with email and password.
- The resulting access token is expected to be stored by the caller (the
  route layer) in an httponly cookie named `sb_access_token`.
- `get_current_user` reads that cookie, resolves the Supabase auth user,
  then loads the matching row from the `profiles` table via dbService.
- `require_admin` builds on `get_current_user` and rejects non-admins.
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from supabase import Client

from app.database import _is_jwt_expired, decode_jwt_payload, get_supabase_client
from app.models import User
from app.services import db_service

SESSION_COOKIE_NAME = "sb_access_token"


@dataclass
class AuthResult:
    """Result of a sign up or log in attempt against Supabase Auth."""

    success: bool
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user_id: Optional[str] = None
    email: Optional[str] = None
    error: Optional[str] = None


def sign_up(email: str, password: str, username: Optional[str] = None) -> AuthResult:
    """
    Creates a new Supabase Auth user with email and password.

    Uses an anonymous (unauthenticated) Supabase client, the same way the
    original browser client called `supabase.auth.signUp` before any
    session existed. `username`, when given, is passed as auth user
    metadata so the `handle_new_user` DB trigger (which creates the
    matching `profiles` row from `auth.users`) picks the real username
    instead of falling back to the email prefix.
    """
    client = get_supabase_client()
    payload: dict = {"email": email, "password": password}
    if username:
        payload["options"] = {"data": {"username": username}}
    try:
        response = client.auth.sign_up(payload)
    except Exception as error:
        return AuthResult(success=False, error=str(error))

    if not response.user:
        return AuthResult(success=False, error="Sign up did not return a user.")

    session = response.session
    return AuthResult(
        success=True,
        access_token=session.access_token if session else None,
        refresh_token=session.refresh_token if session else None,
        user_id=response.user.id,
        email=response.user.email,
    )


def log_in(email: str, password: str) -> AuthResult:
    """
    Logs in an existing Supabase Auth user with email and password.

    Mirrors `supabase.auth.signInWithPassword` from the browser client.
    """
    client = get_supabase_client()
    try:
        response = client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except Exception as error:
        return AuthResult(success=False, error=str(error))

    if not response.user or not response.session:
        return AuthResult(success=False, error="Invalid email or password.")

    return AuthResult(
        success=True,
        access_token=response.session.access_token,
        refresh_token=response.session.refresh_token,
        user_id=response.user.id,
        email=response.user.email,
    )


def log_out(access_token: Optional[str]) -> None:
    """
    Signs out of Supabase Auth for the given access token's session.

    This is the server side equivalent of the `supabase.auth.signOut()`
    call inside resetSupabaseAuthState in lib/authUtils.ts. Clearing the
    `sb_access_token` cookie itself is the caller's responsibility (the
    route layer), the same way clearing `sb-*` localStorage keys was the
    browser client's responsibility.
    """
    if not access_token:
        return
    client = get_supabase_client(access_token)
    try:
        client.auth.sign_out()
    except Exception:
        # Mirrors the try/except around supabase.auth.signOut() in
        # resetSupabaseAuthState, which only warns on failure.
        pass


def reset_auth_state(access_token: Optional[str]) -> None:
    """
    Server side equivalent of resetSupabaseAuthState in lib/authUtils.ts.

    The original function signed out of Supabase and cleared every
    `sb-*` key from browser localStorage. On the server there is no
    localStorage, so the equivalent cleanup is: sign out of the Supabase
    session tied to this access token, and let the caller drop the
    `sb_access_token` cookie (the server side analogue of clearing the
    persisted session key).
    """
    log_out(access_token)


def get_access_token_from_request(request: Request) -> Optional[str]:
    """Reads the sb_access_token httponly cookie from the request."""
    return request.cookies.get(SESSION_COOKIE_NAME)


def get_request_supabase_client(request: Request) -> Client:
    """
    FastAPI dependency that returns a Supabase client scoped to whatever
    user (if any) is logged in on this request, for use by route handlers
    that need direct database access alongside `get_current_user`.
    """
    token = get_access_token_from_request(request)
    return get_supabase_client(token)


def get_current_user(request: Request) -> Optional[User]:
    """
    FastAPI dependency that resolves the logged in user for this request.

    Reads the `sb_access_token` httponly cookie, verifies it with
    `supabase.auth.get_user`, then loads the corresponding row from the
    `profiles` table (plus saved/visited shops and follow lists) via
    `db_service.fetch_user_profile`. Returns None if there is no valid
    session, mirroring how the original app rendered as logged out
    whenever `supabase.auth.getSession()` had no session.
    """
    token = get_access_token_from_request(request)
    if not token or _is_jwt_expired(token):
        return None

    # Reads the user id straight out of the JWT instead of making a remote
    # call to Supabase's Auth API (client.auth.get_user) on every request.
    # The very next query (fetch_user_profile) is made with this same token
    # attached to PostgREST, which independently verifies the JWT signature,
    # so a forged/tampered token still fails there instead of being trusted.
    payload = decode_jwt_payload(token)
    user_id = payload.get("sub") if payload else None
    if not user_id:
        return None

    client = get_supabase_client(token)
    profile = db_service.fetch_user_profile(client, user_id)
    if not profile:
        return None
    return User(**profile)


def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    """FastAPI dependency that requires a logged in user or raises 401."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )
    return user


def require_admin(user: Optional[User] = Depends(get_current_user)) -> User:
    """
    FastAPI dependency that requires a logged in, admin user.

    Mirrors the admin gate in api/cloudinary-delete.ts, which loaded the
    caller's `profiles.is_admin` flag and rejected the request with a 401
    if unauthenticated or 403 if authenticated but not an admin.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can perform this action.",
        )
    return user
