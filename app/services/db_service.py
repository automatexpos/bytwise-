"""
Python translation of services/dbService.ts.

Every function here takes a `supabase: Client` as its first argument.
That client is the request scoped, user authenticated client returned by
`app.database.get_supabase_client(access_token)`, so every table query
below runs under the same Postgres Row Level Security policies that the
original browser client's queries ran under.

Table names, column names, joins, filters and upsert conflict targets are
copied as exactly as possible from dbService.ts so behavior does not
change during the TypeScript to Python port.
"""

import time
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, TypeVar

from supabase import Client

from app.services import rating_service

T = TypeVar("T")

PEOPLE_SAY_CATEGORIES = (
    "food_quality",
    "portion_size",
    "price_value",
    "ambience",
    "service",
)


def get_coordinates(url: str) -> Optional[tuple[float, float]]:
    """Extracts (lat, lng) from a Google Maps URL's "@lat,lng" segment."""
    match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url or "")
    return (float(match.group(1)), float(match.group(2))) if match else None


# ==================== RETRY UTILITY ====================

_RETRYABLE_SUBSTRINGS = (
    "Failed to fetch",
    "QUIC",
    "network",
    "timeout",
    "ECONNRESET",
    "ETIMEDOUT",
)


def retry_with_backoff(
    fn: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    operation_name: str = "operation",
) -> T:
    """
    Retries a function with exponential backoff.

    Python equivalent of retryWithBackoff in dbService.ts. Helps handle
    transient network errors (the original comment called out
    ERR_QUIC_PROTOCOL_ERROR specifically). `base_delay` is in seconds
    here (the TS version used milliseconds).
    """
    last_error: Optional[BaseException] = None

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                delay = base_delay * (2 ** (attempt - 1))
                time.sleep(delay)
            return fn()
        except Exception as error:  # noqa: BLE001, mirrors the TS catch (error: any)
            last_error = error
            error_msg = str(error)

            is_retryable = any(marker in error_msg for marker in _RETRYABLE_SUBSTRINGS)

            if not is_retryable or attempt == max_retries:
                raise

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{operation_name} failed for an unknown reason.")


# ==================== PROFILES ====================


def _fetch_user_connections(supabase: Client, user_id: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """
    Runs the saved shops, visited shops, followers, and following lookups
    concurrently (they're independent queries) instead of one after another,
    since each is its own network round trip to PostgREST.
    """

    def _saved() -> list[str]:
        result = supabase.table("saved_shops").select("shop_id").eq("user_id", user_id).execute()
        return [row["shop_id"] for row in (result.data or [])]

    def _visited() -> list[str]:
        result = supabase.table("visited_shops").select("shop_id").eq("user_id", user_id).execute()
        return [row["shop_id"] for row in (result.data or [])]

    def _followers() -> list[str]:
        try:
            result = (
                supabase.table("user_follows").select("follower_id").eq("following_id", user_id).execute()
            )
            return [row["follower_id"] for row in (result.data or [])]
        except Exception:
            return []

    def _following() -> list[str]:
        try:
            result = (
                supabase.table("user_follows").select("following_id").eq("follower_id", user_id).execute()
            )
            return [row["following_id"] for row in (result.data or [])]
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=4) as executor:
        saved_future = executor.submit(_saved)
        visited_future = executor.submit(_visited)
        followers_future = executor.submit(_followers)
        following_future = executor.submit(_following)
        return (
            saved_future.result(),
            visited_future.result(),
            followers_future.result(),
            following_future.result(),
        )


def fetch_user_profile(supabase: Client, user_id: str) -> Optional[dict[str, Any]]:
    """
    Fetches a user's profile row plus saved shops, visited shops, and
    follower/following id lists, shaped like the User interface.

    Python equivalent of fetchUserProfile in dbService.ts. Returns a plain
    dict using the same camelCase style keys the TS function returned
    (id, username, email, avatarUrl, bio, socialLinks, isBusinessOwner,
    isAdmin, savedShops, visitedShops, followerIds, followingIds), so it
    can be handed directly to app.models.User(**data).
    """
    try:
        profile_response = (
            supabase.table("profiles").select("*").eq("id", user_id).single().execute()
        )
        profile = profile_response.data
        if not profile:
            return None

        saved_shops, visited_shops, followers_data, following_data = _fetch_user_connections(
            supabase, user_id
        )

        return {
            "id": profile["id"],
            "username": profile["username"],
            "email": profile["email"],
            "avatarUrl": profile.get("avatar_url") or "",
            "bio": profile.get("bio") or "",
            "socialLinks": {
                "instagram": profile.get("instagram"),
                "x": profile.get("x"),
            },
            "isBusinessOwner": profile.get("is_business_owner") or False,
            "isAdmin": profile.get("is_admin") or False,
            "savedShops": saved_shops,
            "visitedShops": visited_shops,
            "followerIds": followers_data,
            "followingIds": following_data,
        }
    except Exception as error:  # noqa: BLE001, mirrors the TS catch and console.error
        print(f"Error fetching user profile: {error}")
        return None


def fetch_user_profiles_basic(supabase: Client, user_ids: list[str]) -> list[dict[str, Any]]:
    """
    Fetches just id/username/avatarUrl for a batch of user ids in a single
    query. Used for connection lists (following/followers) where the full
    fetch_user_profile per id (five sequential queries each) would be a
    severe N+1 query problem for anyone with more than a couple of connections.
    """
    if not user_ids:
        return []
    try:
        response = (
            supabase.table("profiles")
            .select("id, username, avatar_url")
            .in_("id", user_ids)
            .execute()
        )
        rows = response.data or []
    except Exception as error:  # noqa: BLE001
        print(f"Error fetching basic user profiles: {error}")
        return []

    by_id = {
        row["id"]: {"id": row["id"], "username": row["username"], "avatarUrl": row.get("avatar_url")}
        for row in rows
    }
    # Preserve the caller's requested order (e.g. most recently followed first).
    return [by_id[user_id] for user_id in user_ids if user_id in by_id]


def fetch_user_profile_by_username(
    supabase: Client, username: str
) -> Optional[dict[str, Any]]:
    """
    Fetches a user's profile row by username (case insensitive match).

    Python equivalent of fetchUserProfileByUsername in dbService.ts.
    """
    try:
        profile_response = (
            supabase.table("profiles")
            .select("*")
            .ilike("username", username)
            .single()
            .execute()
        )
        profile = profile_response.data
        if not profile:
            return None

        user_id = profile["id"]
        saved_shops, visited_shops, followers_data, following_data = _fetch_user_connections(
            supabase, user_id
        )

        return {
            "id": profile["id"],
            "username": profile["username"],
            "email": profile["email"],
            "avatarUrl": profile.get("avatar_url") or "",
            "bio": profile.get("bio") or "",
            "socialLinks": {
                "instagram": profile.get("instagram"),
                "x": profile.get("x"),
            },
            "isBusinessOwner": profile.get("is_business_owner") or False,
            "isAdmin": profile.get("is_admin") or False,
            "savedShops": saved_shops,
            "visitedShops": visited_shops,
            "followerIds": followers_data,
            "followingIds": following_data,
        }
    except Exception as error:  # noqa: BLE001
        print(f"Error fetching user profile by username: {error}")
        return None


def toggle_follow_user(
    supabase: Client, follower_id: str, following_id: str, is_currently_following: bool
) -> dict[str, Any]:
    """
    Follows or unfollows a user depending on `is_currently_following`.

    Python equivalent of toggleFollowUser in dbService.ts.
    """
    try:
        if is_currently_following:
            response = (
                supabase.table("user_follows")
                .delete()
                .eq("follower_id", follower_id)
                .eq("following_id", following_id)
                .execute()
            )
        else:
            response = (
                supabase.table("user_follows")
                .insert({"follower_id": follower_id, "following_id": following_id})
                .execute()
            )
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error toggling follow: {error}")
        return {"success": False, "error": str(error) or "Failed to follow/unfollow"}


def create_user_profile(
    supabase: Client, user_id: str, username: str, email: str
) -> dict[str, Any]:
    """
    Creates (or upserts) a profile row for a newly signed up user.

    Python equivalent of createUserProfile in dbService.ts. Reproduces the
    same safe username derivation (fallback to the email prefix, then to
    user_<first 8 chars of id>, trimmed, whitespace replaced with
    underscores, truncated to 40 chars) and the same default avatar URL
    scheme via ui-avatars.com.
    """
    try:
        import urllib.parse
        import re

        fallback = username or (email.split("@")[0] if email else "") or f"user_{user_id[:8]}"
        safe_username = re.sub(r"\s+", "_", fallback.strip())[:40]

        avatar_url = (
            "https://ui-avatars.com/api/?name="
            f"{urllib.parse.quote(safe_username)}&background=231b15&color=F08000"
        )

        response = (
            supabase.table("profiles")
            .upsert(
                {
                    "id": user_id,
                    "username": safe_username,
                    "email": email,
                    "avatar_url": avatar_url,
                },
                on_conflict="id",
            )
            .execute()
        )
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error creating profile: {error}")
        return {"success": False, "error": error}


def update_user_profile(
    supabase: Client,
    user_id: str,
    username: Optional[str] = None,
    bio: Optional[str] = None,
    avatar_url: Optional[str] = None,
    instagram: Optional[str] = None,
    x: Optional[str] = None,
) -> dict[str, Any]:
    """
    Updates one or more fields on a profile row.

    Python equivalent of updateUserProfile in dbService.ts. Only fields
    that are not None are included in the update, mirroring the
    `updates.field !== undefined` checks in the TS version.
    """
    try:
        update_data: dict[str, Any] = {}
        if username is not None:
            update_data["username"] = username
        if bio is not None:
            update_data["bio"] = bio
        if avatar_url is not None:
            update_data["avatar_url"] = avatar_url
        if instagram is not None:
            update_data["instagram"] = instagram
        if x is not None:
            update_data["x"] = x

        response = (
            supabase.table("profiles").update(update_data).eq("id", user_id).execute()
        )
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error updating profile: {error}")
        return {"success": False, "error": error}


# ==================== SHOPS ====================


def fetch_shops(supabase: Client) -> list[dict[str, Any]]:
    """
    Fetches every shop with its images, reviews, and aggregated vibe votes.

    Python equivalent of fetchShops in dbService.ts. Retries with backoff
    (3 retries, 1 second base delay) the same way the original did.
    """

    def _do_fetch() -> list[dict[str, Any]]:
        shops_response = (
            supabase.table("shops")
            .select("*, shop_images(*), reviews(*, profiles(username, avatar_url))")
            .order("created_at", desc=True)
            .execute()
        )
        shops = shops_response.data
        if not shops:
            return []

        shop_ids = [shop["id"] for shop in shops]
        votes: list[dict[str, Any]] = []
        if shop_ids:
            try:
                votes_response = (
                    supabase.table("vibe_votes")
                    .select("shop_id, vibe, vote")
                    .in_("shop_id", shop_ids)
                    .execute()
                )
                votes = votes_response.data or []
            except Exception as votes_error:  # noqa: BLE001
                # Mirrors: if (votesError && votesError.code !== '42P01') throw votesError;
                # Postgres error code 42P01 is "undefined table", tolerated
                # the same way the original silently ignored a missing
                # vibe_votes table.
                code = getattr(votes_error, "code", None)
                if code != "42P01":
                    raise

        vibe_ratings_by_shop: dict[str, dict[str, dict[str, Any]]] = {}
        for vote in votes:
            shop_id = vote["shop_id"]
            rating = vibe_ratings_by_shop.setdefault(shop_id, {})
            current = rating.setdefault(
                vote["vibe"], {"up": 0, "down": 0, "total": 0, "score": 0}
            )
            if vote["vote"] == "up":
                current["up"] += 1
            else:
                current["down"] += 1
            current["total"] += 1
            current["score"] = round((current["up"] / current["total"]) * 100)

        people_say_ratings: list[dict[str, Any]] = []
        if shop_ids:
            try:
                people_say_response = (
                    supabase.table("shop_category_ratings")
                    .select("shop_id, category, rating")
                    .in_("shop_id", shop_ids)
                    .execute()
                )
                people_say_ratings = people_say_response.data or []
            except Exception as ratings_error:  # noqa: BLE001
                if getattr(ratings_error, "code", None) != "42P01":
                    raise

        people_say_by_shop: dict[str, dict[str, list[float]]] = {}
        for rating in people_say_ratings:
            category = rating.get("category")
            if category not in PEOPLE_SAY_CATEGORIES:
                continue
            shop_ratings = people_say_by_shop.setdefault(rating["shop_id"], {})
            shop_ratings.setdefault(category, []).append(float(rating["rating"]))

        results: list[dict[str, Any]] = []
        for shop in shops:
            shop_images = shop.get("shop_images") or []
            gallery = [
                {
                    "id": img.get("id"),
                    "url": img.get("url") or "",
                    "publicId": img.get("cloudinary_public_id"),
                    "type": img.get("type"),
                    "approved": img.get("approved") is not False,
                    "uploadedBy": img.get("uploaded_by"),
                    "caption": img.get("caption"),
                }
                for img in shop_images
                if img.get("approved") is not False
            ]

            reviews = []
            for review in shop.get("reviews") or []:
                review_profile = review.get("profiles") or {}
                username = review_profile.get("username") or "Anonymous"
                avatar_url = review_profile.get("avatar_url") or (
                    "https://ui-avatars.com/api/?name="
                    f"{review_profile.get('username') or 'User'}&background=random"
                )
                reviews.append(
                    {
                        "id": review["id"],
                        "userId": review.get("user_id"),
                        "username": username,
                        "avatarUrl": avatar_url,
                        "rating": review.get("rating"),
                        "comment": review.get("comment") or "",
                        "date": review.get("created_at"),
                    }
                )

            lat = float(shop["lat"] or 0)
            lng = float(shop["lng"] or 0)
            if lat == 0 and lng == 0:
                coordinates = get_coordinates(shop.get("address") or "")
                if coordinates:
                    lat, lng = coordinates

            category_averages = {
                category: {
                    "average": round(sum(scores) / len(scores), 1),
                    "count": len(scores),
                }
                for category, scores in people_say_by_shop.get(shop["id"], {}).items()
            }
            people_say_rating = float(shop.get("people_say_rating") or 0)
            people_say_rating_count = int(shop.get("people_say_rating_count") or 0)

            results.append(
                {
                    "id": shop["id"],
                    "name": shop["name"],
                    "description": shop.get("description") or "",
                    "location": {
                        "lat": lat,
                        "lng": lng,
                        "address": shop.get("address"),
                        "city": shop.get("city"),
                        "state": shop.get("state"),
                        "area": shop.get("area"),
                    },
                    "gallery": gallery,
                    "vibes": shop.get("vibes") or [],
                    "vibeRatings": vibe_ratings_by_shop.get(shop["id"], {}),
                    "peopleSayRatings": category_averages,
                    "peopleSayRating": people_say_rating,
                    "peopleSayRatingCount": people_say_rating_count,
                    "cheekyVibes": shop.get("cheeky_vibes") or [],
                    "rating": float(shop.get("rating") or 0),
                    "reviewCount": shop.get("review_count") or 0,
                    "reviews": reviews,
                    "isClaimed": shop.get("is_claimed"),
                    "claimedBy": shop.get("claimed_by"),
                    "stampCount": shop.get("stamp_count") or 0,
                    "openHours": shop.get("open_hours"),
                    "parking": shop.get("parking"),
                    "facilities": shop.get("facilities"),
                }
            )
        return results

    try:
        return retry_with_backoff(_do_fetch, 3, 1.0, "fetchShops")
    except Exception as error:  # noqa: BLE001
        print(f"[dbService] Error fetching shops (all retries exhausted): {error}")
        raise


def create_shop(supabase: Client, shop_data: dict[str, Any]) -> dict[str, Any]:
    """
    Creates a new shop row plus any accompanying shop_images rows.

    Python equivalent of createShop in dbService.ts. `shop_data` should
    contain: name, description, lat, lng, address, city, state, area
    (optional), vibes, cheekyVibes, parking (optional), facilities
    (optional dict), openHours (optional dict), and images (a list of
    dicts with url, publicId (optional), type, uploadedBy (optional)).
    """
    import uuid

    try:
        shop_id = str(uuid.uuid4())
        shop_response = (
            supabase.table("shops")
            .insert(
                {
                    "id": shop_id,
                    "name": shop_data["name"],
                    "description": shop_data["description"],
                    "lat": shop_data["lat"],
                    "lng": shop_data["lng"],
                    "address": shop_data["address"],
                    "city": shop_data["city"],
                    "state": shop_data["state"],
                    "area": shop_data.get("area") or None,
                    "vibes": shop_data["vibes"],
                    "cheeky_vibes": shop_data["cheekyVibes"],
                    "parking": shop_data.get("parking") or None,
                    "facilities": shop_data.get("facilities") or {},
                    "open_hours": shop_data.get("openHours") or {},
                }
            )
            .execute()
        )
        if getattr(shop_response, "error", None):
            raise RuntimeError(
                f"Could not save shop record: {shop_response.error.message}"
            )

        images = shop_data.get("images") or []
        if images:
            image_inserts = [
                {
                    "shop_id": shop_id,
                    "url": img["url"],
                    "cloudinary_public_id": img.get("publicId") or None,
                    "type": img["type"],
                    "approved": True,
                    "uploaded_by": img.get("uploadedBy") or None,
                }
                for img in images
            ]
            image_response = supabase.table("shop_images").insert(image_inserts).execute()
            if getattr(image_response, "error", None):
                raise RuntimeError(
                    f"Shop image records could not be saved: {image_response.error.message}"
                )

        return {"success": True, "shop": {"id": shop_id}}
    except Exception as error:  # noqa: BLE001
        print(f"Error creating shop: {error}")
        return {"success": False, "error": error}


def add_shop_images(
    supabase: Client, shop_id: str, images: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Adds images to an existing shop.

    Python equivalent of addShopImages in dbService.ts. Each item in
    `images` may contain url, publicId (optional), type, approved
    (optional, defaults to True unless explicitly False), uploadedBy
    (optional).
    """
    try:
        if not images:
            return {"success": True}

        image_inserts = [
            {
                "shop_id": shop_id,
                "url": img["url"],
                "cloudinary_public_id": img.get("publicId") or None,
                "type": img["type"],
                "approved": img.get("approved") is not False,
                "uploaded_by": img.get("uploadedBy") or None,
            }
            for img in images
        ]

        response = supabase.table("shop_images").insert(image_inserts).execute()
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error adding shop images: {error}")
        return {"success": False, "error": error}


def fetch_pending_shop_images(supabase: Client) -> dict[str, Any]:
    """
    Fetches all shop_images rows that are pending admin approval.

    Python equivalent of fetchPendingShopImages in dbService.ts.
    """
    try:
        response = (
            supabase.table("shop_images")
            .select("id, shop_id, url, cloudinary_public_id, type, uploaded_by, created_at")
            .eq("approved", False)
            .order("created_at", desc=True)
            .execute()
        )
        _raise_if_error(response)
        return {"success": True, "images": response.data or []}
    except Exception as error:  # noqa: BLE001
        print(f"Error fetching pending shop images: {error}")
        return {"success": False, "error": error, "images": []}


def approve_shop_image(supabase: Client, image_id: str) -> dict[str, Any]:
    """
    Marks a pending shop image as approved.

    Python equivalent of approveShopImage in dbService.ts.
    """
    try:
        response = (
            supabase.table("shop_images")
            .update({"approved": True})
            .eq("id", image_id)
            .execute()
        )
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error approving shop image: {error}")
        return {"success": False, "error": error}


def delete_shop_images(supabase: Client, public_ids: list[str]) -> dict[str, Any]:
    """
    Deletes shop_images rows by a list of Cloudinary public ids.

    Python equivalent of deleteShopImages in dbService.ts.
    """
    try:
        if not public_ids:
            return {"success": True}
        response = (
            supabase.table("shop_images")
            .delete()
            .in_("cloudinary_public_id", public_ids)
            .execute()
        )
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error deleting shop images: {error}")
        return {"success": False, "error": error}


def delete_shop_image(supabase: Client, image_id: str) -> dict[str, Any]:
    """
    Deletes a single shop_images row by its id.

    Python equivalent of deleteShopImage in dbService.ts.
    """
    try:
        response = supabase.table("shop_images").delete().eq("id", image_id).execute()
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error deleting shop image record: {error}")
        return {"success": False, "error": error}


def vote_on_vibe(
    supabase: Client, user_id: str, shop_id: str, vibe: str, vote: str
) -> dict[str, Any]:
    """
    Casts (or replaces) a user's up/down vote on a shop's vibe tag.

    Python equivalent of voteOnVibe in dbService.ts. `vote` should be
    either 'up' or 'down'. Upserts on the (user_id, shop_id, vibe)
    composite conflict target, same as the original.
    """
    try:
        response = (
            supabase.table("vibe_votes")
            .upsert(
                {"user_id": user_id, "shop_id": shop_id, "vibe": vibe, "vote": vote},
                on_conflict="user_id,shop_id,vibe",
            )
            .execute()
        )
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error voting on vibe: {error}")
        return {"success": False, "error": str(error) or "Could not save vibe vote."}


def update_shop_in_db(supabase: Client, shop_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """
    Updates arbitrary fields on a shop row.

    Python equivalent of updateShopInDB in dbService.ts. `updates` is
    passed straight through to the update call, the same way the TS
    version passed its `updates` object straight through (fields:
    name, description, lat, lng, address, city, state, area, parking,
    facilities, vibes, cheeky_vibes, open_hours).
    """
    try:
        response = supabase.table("shops").update(updates).eq("id", shop_id).execute()
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error updating shop: {error}")
        return {"success": False, "error": error}


# ==================== REVIEWS ====================


def save_people_say_ratings(
    supabase: Client, shop_id: str, user_id: str, ratings: dict[str, int]
) -> dict[str, Any]:
    """Upserts one 0-5 category rating per user for a shop."""
    rows = [
        {
            "shop_id": shop_id,
            "user_id": user_id,
            "category": category,
            "rating": rating,
        }
        for category, rating in ratings.items()
    ]
    try:
        response = (
            supabase.table("shop_category_ratings")
            .upsert(rows, on_conflict="shop_id,user_id,category")
            .execute()
        )
        _raise_if_error(response)
        ratings_response = (
            supabase.table("shop_category_ratings")
            .select("category, rating")
            .eq("shop_id", shop_id)
            .execute()
        )
        _raise_if_error(ratings_response)
        scores_by_category: dict[str, list[float]] = {}
        for row in ratings_response.data or []:
            scores_by_category.setdefault(row["category"], []).append(float(row["rating"]))
        aggregates = {
            category: {"average": round(sum(scores) / len(scores), 1), "count": len(scores)}
            for category, scores in scores_by_category.items()
        }

        # Keep shops.people_say_rating/_count in sync at runtime, in case the
        # DB trigger from add_shop_category_ratings.sql hasn't been applied.
        rating_service.recalculate_people_say_rating(supabase, shop_id)

        return {"success": True, "ratings": aggregates}
    except Exception as error:  # noqa: BLE001
        print(f"Error saving category ratings: {error}")
        return {"success": False, "error": error}


def add_review(
    supabase: Client, shop_id: str, user_id: str, rating: float, comment: str
) -> dict[str, Any]:
    """
    Adds a review for a shop, then recalculates and stores the shop's
    average rating and review count.

    Python equivalent of addReview in dbService.ts.
    """
    try:
        insert_response = (
            supabase.table("reviews")
            .upsert(
                {"shop_id": shop_id, "user_id": user_id, "rating": rating, "comment": comment},
                on_conflict="shop_id,user_id",
            )
            .execute()
        )
        _raise_if_error(insert_response)
        inserted_review = (insert_response.data or [None])[0]

        rating_service.recalculate_review_rating(supabase, shop_id)

        return {"success": True, "review": inserted_review}
    except Exception as error:  # noqa: BLE001
        print(f"Error adding review: {error}")
        return {"success": False, "error": error}


# ==================== SAVED SHOPS ====================


def toggle_saved_shop(supabase: Client, user_id: str, shop_id: str, is_saved: bool) -> dict[str, Any]:
    """
    Saves or unsaves a shop for a user, depending on `is_saved`.

    Python equivalent of toggleSavedShop in dbService.ts.
    """
    try:
        if is_saved:
            response = (
                supabase.table("saved_shops")
                .delete()
                .eq("user_id", user_id)
                .eq("shop_id", shop_id)
                .execute()
            )
        else:
            response = (
                supabase.table("saved_shops")
                .insert({"user_id": user_id, "shop_id": shop_id})
                .execute()
            )
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error toggling saved shop: {error}")
        return {"success": False, "error": error}


# ==================== VISITED SHOPS ====================


def toggle_visited_shop(
    supabase: Client, user_id: str, shop_id: str, is_visited: bool
) -> dict[str, Any]:
    """
    Marks or unmarks a shop as visited for a user, depending on
    `is_visited`.

    Python equivalent of toggleVisitedShop in dbService.ts.
    """
    try:
        if is_visited:
            response = (
                supabase.table("visited_shops")
                .delete()
                .eq("user_id", user_id)
                .eq("shop_id", shop_id)
                .execute()
            )
        else:
            response = (
                supabase.table("visited_shops")
                .insert({"user_id": user_id, "shop_id": shop_id})
                .execute()
            )
        _raise_if_error(response)
        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error toggling visited shop: {error}")
        return {"success": False, "error": error}


# ==================== CLAIM REQUESTS ====================


def submit_claim_request(supabase: Client, request: dict[str, Any]) -> dict[str, Any]:
    """
    Submits a business claim request for a shop.

    Python equivalent of submitClaimRequest in dbService.ts. `request`
    should contain shopId, userId, businessEmail, role, socialLink.
    """
    try:
        response = (
            supabase.table("claim_requests")
            .insert(
                {
                    "shop_id": request["shopId"],
                    "user_id": request["userId"],
                    "business_email": request["businessEmail"],
                    "role": request["role"],
                    "social_link": request["socialLink"],
                }
            )
            .execute()
        )
        _raise_if_error(response)
        return {"success": True, "request": (response.data or [None])[0]}
    except Exception as error:  # noqa: BLE001
        print(f"Error submitting claim request: {error}")
        return {"success": False, "error": error}


def fetch_claim_requests(supabase: Client) -> list[dict[str, Any]]:
    """
    Fetches all claim requests, newest first.

    Python equivalent of fetchClaimRequests in dbService.ts.
    """
    try:
        response = (
            supabase.table("claim_requests")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        _raise_if_error(response)
        return response.data or []
    except Exception as error:  # noqa: BLE001
        print(f"Error fetching claim requests: {error}")
        return []


def approve_claim_request(supabase: Client, request_id: str) -> dict[str, Any]:
    """
    Approves a claim request: marks the request approved, marks the shop
    as claimed by the requesting user, and promotes that user to a
    business owner.

    Python equivalent of approveClaimRequest in dbService.ts.
    """
    try:
        fetch_response = (
            supabase.table("claim_requests")
            .select("*")
            .eq("id", request_id)
            .single()
            .execute()
        )
        _raise_if_error(fetch_response)
        request = fetch_response.data

        update_response = (
            supabase.table("claim_requests")
            .update({"status": "approved"})
            .eq("id", request_id)
            .execute()
        )
        _raise_if_error(update_response)

        shop_response = (
            supabase.table("shops")
            .update({"is_claimed": True, "claimed_by": request["user_id"]})
            .eq("id", request["shop_id"])
            .execute()
        )
        _raise_if_error(shop_response)

        profile_response = (
            supabase.table("profiles")
            .update({"is_business_owner": True})
            .eq("id", request["user_id"])
            .execute()
        )
        _raise_if_error(profile_response)

        return {"success": True}
    except Exception as error:  # noqa: BLE001
        print(f"Error approving claim request: {error}")
        return {"success": False, "error": error}


# ==================== INTERNAL HELPERS ====================


def _raise_if_error(response: Any) -> None:
    """
    Raises if a supabase-py response carries an error.

    supabase-py raises `postgrest.APIError` automatically on non-2xx
    responses for most calls, but some code paths return an `error`
    attribute instead. This helper normalizes both cases so callers can
    use a single `if error: raise error` style check like the original
    TypeScript `if (error) throw error;` lines.
    """
    error = getattr(response, "error", None)
    if error:
        raise RuntimeError(str(error))
