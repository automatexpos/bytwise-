"""
Supabase client factory for the FastAPI backend.

Mirrors lib/supabase.ts, but instead of a single module level browser
client, this module builds a fresh client per request. When a user's
access token is supplied, the token is attached to both the PostgREST
client (so Row Level Security policies see the same auth.uid() as the
original browser client) and the Auth client (so supabase.auth.get_user
and related calls work against that session). The anon key is always
used as the base API key, the same way the original browser client
only ever shipped the anon key. A service role key is never used here
so RLS continues to apply exactly as it did in the TypeScript app.
"""

from functools import lru_cache

import base64
import json
import time

from supabase import Client, ClientOptions, create_client

from app.config import get_settings


def _is_jwt_expired(token: str) -> bool:
    """
    Cheaply checks a JWT's `exp` claim without verifying its signature
    (Supabase itself verifies the signature; this just avoids sending a
    token we already know is stale, which PostgREST would reject outright
    with a "JWT expired" error instead of falling back to anonymous access).
    """
    try:
        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_segment + padding))
        exp = payload.get("exp")
        return bool(exp) and time.time() >= exp
    except Exception:
        return False


@lru_cache
def _get_base_client() -> Client:
    """
    Builds (and caches) the anonymous, unauthenticated Supabase client.

    This mirrors the base `supabase` export in lib/supabase.ts before any
    user session is attached.
    """
    settings = get_settings()
    if not settings.is_supabase_configured:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY "
            "(or VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY) in the environment."
        )

    options = ClientOptions(
        headers={"x-client-info": "bytwise-backend"},
        schema="public",
    )
    return create_client(settings.supabase_url, settings.supabase_anon_key, options)


def get_supabase_client(access_token: str | None = None) -> Client:
    """
    Returns a Supabase client scoped to the given user access token, if any.

    Parameters
    ----------
    access_token:
        The logged in user's Supabase JWT (as stored in the sb_access_token
        httponly cookie). When provided, the returned client's PostgREST
        and Auth requests are authenticated as that user, so RLS policies
        apply exactly as they did in the original browser client. When
        omitted, the returned client behaves like an anonymous visitor.

    Returns
    -------
    Client
        A `supabase.Client` instance. Note this always uses the anon key,
        never a service role key, so RLS is never bypassed.
    """
    settings = get_settings()
    if not settings.is_supabase_configured:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY "
            "(or VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY) in the environment."
        )

    options = ClientOptions(
        headers={"x-client-info": "bytwise-backend"},
        schema="public",
    )
    client = create_client(settings.supabase_url, settings.supabase_anon_key, options)

    if access_token and not _is_jwt_expired(access_token):
        # Attach the bearer token to PostgREST so `auth.uid()` inside RLS
        # policies resolves to this user, the same way the browser client's
        # persisted session did.
        client.postgrest.auth(access_token)

        # Also register the token with the Auth client so that
        # supabase.auth.get_user() / get_session() style calls made against
        # this client see the same logged in user.
        try:
            client.auth.set_session(access_token, access_token)
        except Exception:
            # set_session tries to validate/refresh the session remotely.
            # If that fails (e.g. no refresh token available), the
            # PostgREST auth() call above is still sufficient for RLS
            # scoped table queries, so we do not raise here.
            pass

    return client
