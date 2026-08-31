"""
Resolves the restaurant chatbot backend's base URL from Supabase instead
of a fixed environment variable.

The chatbot backend (Flask + Ollama) runs on the developer's own machine
behind a Cloudflare Tunnel. Free quick tunnels hand out a new random URL
every time `cloudflared` restarts, which used to mean updating a
`CHATBOT_API_URL` environment variable on Vercel and redeploying just to
pick up the new value. Instead, the tunnel URL is now written into a
single Supabase table (`cloudflare_url`) whenever the tunnel starts, and
this module reads the most recent row on each request, so a tunnel
restart only requires a new row in that table, not a redeploy.

Table shape (already created by the user):
    create table public.cloudflare_url (
      id integer not null,
      url text not null,
      created_at timestamp with time zone not null default now(),
      constraint cloudflare_url_pkey primary key (id)
    );

Note: this is read with the anonymous Supabase client (the same one
Auth sign up/log in uses), since page renders happen for logged out
visitors too. The `cloudflare_url` table needs a Row Level Security
policy that allows SELECT for the anon role, otherwise every read fails
and the widget stays hidden.
"""

import time

from app.database import get_supabase_client

# Short enough that a new tunnel URL shows up on the site quickly after
# being written, long enough that normal page views do not each cost a
# round trip to Supabase.
_CACHE_TTL_SECONDS = 30

_cached_url: str = ""
_cache_expires_at: float = 0.0


def get_chatbot_api_url() -> str:
    """
    Returns the current chatbot backend base URL from the most recent row
    in the `cloudflare_url` table, with a short in memory cache.

    On any error (Supabase unreachable, table missing, RLS denying
    anonymous access, no rows yet), this falls back to the last
    successfully fetched URL instead of hiding the widget over a brief
    hiccup. If nothing has ever been fetched successfully, it returns an
    empty string, which keeps the widget hidden, the same as before when
    the URL was unconfigured.
    """
    global _cached_url, _cache_expires_at

    now = time.monotonic()
    if now < _cache_expires_at:
        return _cached_url

    try:
        client = get_supabase_client()
        response = (
            client.table("cloudflare_url")
            .select("url")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if rows and rows[0].get("url"):
            _cached_url = str(rows[0]["url"]).rstrip("/")
    except Exception:
        # Keep serving whatever we last had rather than flashing the
        # widget on and off because of a transient network error.
        pass

    _cache_expires_at = now + _CACHE_TTL_SECONDS
    return _cached_url
