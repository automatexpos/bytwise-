"""
Fast, runtime recalculation of a shop's average ratings.

shops only allows UPDATE via RLS for the claimed owner or an admin, so a
plain `.table("shops").update(...)` from a regular user's request-scoped
client is silently filtered out (0 rows affected, no error). Instead these
call the `recalculate_shop_rating`/`recalculate_shop_people_say_rating`
SECURITY DEFINER Postgres functions (see database/rpc_recalculate_ratings.sql),
which recompute the averages server-side in a single round trip and are
narrowly scoped to just those rating columns.
"""

from typing import Any

from supabase import Client


def recalculate_review_rating(supabase: Client, shop_id: str) -> None:
    """Recomputes shops.rating/review_count from the reviews table for one shop."""
    response = supabase.rpc("recalculate_shop_rating", {"p_shop_id": shop_id}).execute()
    _raise_if_error(response)


def recalculate_people_say_rating(supabase: Client, shop_id: str) -> None:
    """Recomputes shops.people_say_rating/_count from shop_category_ratings for one shop."""
    response = supabase.rpc("recalculate_shop_people_say_rating", {"p_shop_id": shop_id}).execute()
    _raise_if_error(response)


def _raise_if_error(response: Any) -> None:
    error = getattr(response, "error", None)
    if error:
        raise RuntimeError(str(error))
