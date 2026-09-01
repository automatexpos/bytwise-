"""
Fast, runtime recalculation of a shop's average ratings.

Each function issues exactly two indexed queries (a narrow single-column
select filtered by shop_id, then an update), so recalculating happens
synchronously right after a rating is written without noticeable latency.
"""

from typing import Any

from supabase import Client


def recalculate_review_rating(supabase: Client, shop_id: str) -> dict[str, Any]:
    """Recomputes shops.rating/review_count from the reviews table for one shop."""
    response = supabase.table("reviews").select("rating").eq("shop_id", shop_id).execute()
    ratings = [float(row["rating"]) for row in (response.data or [])]
    average = round(sum(ratings) / len(ratings), 1) if ratings else 0.0

    supabase.table("shops").update(
        {"rating": average, "review_count": len(ratings)}
    ).eq("id", shop_id).execute()

    return {"average": average, "count": len(ratings)}


def recalculate_people_say_rating(supabase: Client, shop_id: str) -> dict[str, Any]:
    """Recomputes shops.people_say_rating/_count from shop_category_ratings for one shop."""
    response = (
        supabase.table("shop_category_ratings").select("rating").eq("shop_id", shop_id).execute()
    )
    ratings = [float(row["rating"]) for row in (response.data or [])]
    average = round(sum(ratings) / len(ratings), 1) if ratings else 0.0

    supabase.table("shops").update(
        {"people_say_rating": average, "people_say_rating_count": len(ratings)}
    ).eq("id", shop_id).execute()

    return {"average": average, "count": len(ratings)}
