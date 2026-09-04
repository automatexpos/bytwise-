"""
Small JSON endpoints called via fetch from page JS for interactive actions
that should not reload the page (vibe voting, save/visit toggles, follow,
admin moderation actions, and the shop list feeding the Leaflet map).
"""

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.models import User
from app.security import get_current_user, get_request_supabase_client, require_admin, require_user
from app.services import db_service, storage_service

router = APIRouter(prefix="/api")

PEOPLE_SAY_CATEGORIES = {
    "food_quality",
    "portion_size",
    "price_value",
    "ambience",
    "service",
}


@router.get("/shops")
def list_shops(supabase=Depends(get_request_supabase_client)) -> dict[str, Any]:
    """GET /api/shops : JSON list of shops for the Leaflet map to consume."""
    try:
        shops = db_service.fetch_shops(supabase)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not load shops: {error}"
        ) from error
    return {"shops": shops}


@router.post("/check-shop-duplicate")
def check_shop_duplicate(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/check-shop-duplicate : looks for existing shops matching name/city/area."""
    name = str(payload.get("name") or "").strip()
    city = str(payload.get("city") or "").strip()
    area = str(payload.get("area") or "").strip()

    if not name or not city:
        return {"status": "ok"}

    result = db_service.find_duplicate_shops(supabase, name, city, area)
    if result["exact"]:
        return {"status": "exact", "matches": result["exact"]}
    if result["similar"]:
        return {"status": "similar", "matches": result["similar"]}
    return {"status": "ok"}


@router.post("/vibe-vote")
def vibe_vote(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/vibe-vote : casts an up/down vote on a shop's vibe tag."""
    shop_id = str(payload.get("shopId") or "")
    vibe = str(payload.get("vibe") or "")
    vote = str(payload.get("vote") or "")

    if not shop_id or not vibe or vote not in ("up", "down"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid vote payload.")

    result = db_service.vote_on_vibe(supabase, user.id, shop_id, vibe, vote)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Could not save vibe vote."),
        )
    return result


@router.post("/people-say-ratings")
def save_people_say_ratings(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/people-say-ratings : saves the current user's category ratings."""
    shop_id = str(payload.get("shopId") or "")
    ratings = payload.get("ratings")
    if (
        not shop_id
        or not isinstance(ratings, dict)
        or not ratings
        or not set(ratings).issubset(PEOPLE_SAY_CATEGORIES)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category rating payload.")

    validated_ratings: dict[str, int] = {}
    for category, rating in ratings.items():
        if isinstance(rating, bool):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ratings must be whole numbers from 0 to 5.")
        try:
            numeric_rating = float(rating)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ratings must be whole numbers from 0 to 5.")
        if not numeric_rating.is_integer() or not 0 <= numeric_rating <= 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ratings must be whole numbers from 0 to 5.")
        validated_ratings[category] = int(numeric_rating)

    result = db_service.save_people_say_ratings(supabase, shop_id, user.id, validated_ratings)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Could not save category ratings."),
        )
    return result


@router.post("/save-shop")
def save_shop(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/save-shop : toggles a shop's saved status for the current user."""
    shop_id = str(payload.get("shopId") or "")
    if not shop_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="shopId is required.")

    is_saved = shop_id in (user.saved_shops or [])
    result = db_service.toggle_saved_shop(supabase, user.id, shop_id, is_saved)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Could not update saved status."),
        )
    return {"success": True, "saved": not is_saved}


@router.post("/visit-shop")
def visit_shop(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/visit-shop : toggles a shop's visited (passport stamp) status."""
    shop_id = str(payload.get("shopId") or "")
    if not shop_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="shopId is required.")

    is_visited = shop_id in (user.visited_shops or [])
    result = db_service.toggle_visited_shop(supabase, user.id, shop_id, is_visited)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Could not update visited status."),
        )

    review_rating = payload.get("rating")
    review_comment = payload.get("comment")
    if not is_visited and review_comment:
        review_result = db_service.add_review(supabase, shop_id, user.id, int(round(float(review_rating or 5))), str(review_comment))
        if not review_result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(review_result.get("error") or "Could not save your review."),
            )

    return {"success": True, "visited": not is_visited}


@router.post("/add-review")
def add_review(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/add-review : adds/updates the current user's review for a shop and marks the passport stamped."""
    shop_id = str(payload.get("shopId") or "")
    comment = str(payload.get("comment") or "").strip()
    stamp_passport = payload.get("stampPassport", True)
    if not shop_id or not comment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="shopId and comment are required.")

    try:
        rating = int(round(float(payload.get("rating") or 5)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rating must be a number.")
    if not 1 <= rating <= 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rating must be between 1 and 5.")

    result = db_service.add_review(supabase, shop_id, user.id, rating, comment)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Could not save your review."),
        )

    if stamp_passport:
        visit_result = db_service.mark_shop_visited(supabase, user.id, shop_id)
        if not visit_result.get("success"):
            print(f"Warning: review saved but failed to mark visited: {visit_result.get('error')}")

    return {"success": True, "review": result.get("review"), "visited": True}


@router.post("/follow")
def follow_user(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/follow : toggles following another user's profile."""
    target_user_id = str(payload.get("userId") or "")
    if not target_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="userId is required.")

    if target_user_id.startswith("fake-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generated community profiles cannot be followed.",
        )

    is_currently_following = target_user_id in (user.following_ids or [])
    result = db_service.toggle_follow_user(supabase, user.id, target_user_id, is_currently_following)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Could not update follow status."),
        )
    return {"success": True, "following": not is_currently_following}


@router.post("/admin/approve-image")
def approve_image(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_admin),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/admin/approve-image : approves a pending community photo."""
    image_id = str(payload.get("imageId") or "")
    if not image_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="imageId is required.")

    result = db_service.approve_shop_image(supabase, image_id)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Could not approve image."),
        )
    return result


@router.post("/admin/delete-image")
def delete_image(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_admin),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/admin/delete-image : deletes a shop image (Cloudinary plus database row)."""
    image_id = str(payload.get("imageId") or "")
    public_id = payload.get("publicId")
    if not image_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="imageId is required.")

    if public_id:
        storage_result = storage_service.delete_image(str(public_id), is_admin=True)
        if not storage_result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(storage_result.get("error") or "Cloudinary image deletion failed."),
            )

    result = db_service.delete_shop_image(supabase, image_id)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Database image deletion failed."),
        )
    return result


@router.post("/admin/approve-claim")
def approve_claim(
    payload: dict[str, Any] = Body(...),
    user: User = Depends(require_admin),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """POST /api/admin/approve-claim : approves a business claim request."""
    request_id = str(payload.get("requestId") or "")
    if not request_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="requestId is required.")

    result = db_service.approve_claim_request(supabase, request_id)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Could not approve claim request."),
        )
    return result
