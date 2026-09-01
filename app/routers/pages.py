"""
Server rendered HTML page routes, mirroring the React Router routes in
App.tsx (Home, ShopDetail, AddSpot, EditShop, Auth, Profile, ClaimShop,
AdminDashboard).

Business logic that used to live in context/AppContext.tsx (fetching
shops, deriving saved/visited lists, computing vibe ratings, generating
fake community members, computing drip score and badges) is reproduced
here at the route layer since there is no client side context in a
server rendered app.
"""

import math
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.chatbot_config import get_chatbot_api_url
from app.constants import CHEEKY_VIBES_OPTIONS, PARKING_OPTIONS, STANDARD_VIBES
from app.models import User
from app.security import (
    SESSION_COOKIE_NAME,
    get_current_user,
    get_request_supabase_client,
    log_in,
    log_out,
    require_admin,
    require_user,
    sign_up,
)
from app.services import db_service, gemini_service, storage_service

router = APIRouter()

# Resolved relative to this file (app/routers/pages.py -> app/templates), not
# the process working directory, so template loading works the same way
# locally and once deployed as a serverless function (e.g. on Vercel).
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Exposed as a global instead of adding it to every route's context dict, so
# base.html can render the chat widget on every page. Registered as the
# function itself (not a value read once at import time), so base.html
# calls it on every render and always gets the latest tunnel URL out of
# the cloudflare_url table in Supabase. Empty string hides the widget.
templates.env.globals["get_chatbot_api_url"] = get_chatbot_api_url

FACILITY_FIELDS = [
    ("has_prayer_area", "Prayer Area"),
    ("has_clean_washrooms", "Clean Washrooms"),
    ("has_baby_changing", "Baby Changing"),
    ("is_wheelchair_accessible", "Wheelchair Accessible"),
    ("has_ac", "Air Conditioned"),
    ("has_power_outlets", "Power Outlets"),
    ("has_wifi", "WiFi"),
    ("is_pet_friendly", "Pet Friendly"),
]

DAYS_OF_WEEK = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _shop_by_id(shops: list[dict[str, Any]], shop_id: str) -> Optional[dict[str, Any]]:
    for shop in shops:
        if shop.get("id") == shop_id:
            return shop
    return None


def _is_uploaded_file(value: Any) -> bool:
    """
    Checks whether a form field value is an actual uploaded file with
    content, not a plain text field. `request.form()` returns Starlette's
    own `UploadFile` (a superclass of `fastapi.UploadFile`), so an
    `isinstance(value, fastapi.UploadFile)` check never matches; this
    duck-types on `filename` instead.
    """
    return not isinstance(value, str) and bool(getattr(value, "filename", None))


def _get_vibe_score_class(score: int) -> str:
    if score >= 70:
        return "score-good"
    if score >= 40:
        return "score-mid"
    return "score-bad"


def _get_shop_community(shop: dict[str, Any], user: Optional[User], supabase) -> dict[str, Any]:
    """
    Fetches the real users who saved/visited this shop (see
    db_service.fetch_shop_community), plus the current user prepended if
    they saved or visited this shop and aren't already in that list.
    """
    shop_id = shop["id"]
    community = db_service.fetch_shop_community(supabase, shop_id)
    savers = community["savers"]
    visitors = community["visitors"]

    if user:
        if shop_id in (user.saved_shops or []) and not any(s["id"] == user.id for s in savers):
            savers = [{"id": user.id, "username": user.username, "avatarUrl": user.avatar_url}] + savers
        if shop_id in (user.visited_shops or []) and not any(v["id"] == user.id for v in visitors):
            visitors = [{"id": user.id, "username": user.username, "avatarUrl": user.avatar_url}] + visitors

    return {"savers": savers, "visitors": visitors}


def _calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometers between two lat/lng points."""
    earth_radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_km * c


def _parse_optional_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    if not val_str:
        return None
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return None


def _load_claim_requests_for(user: Optional[User], supabase) -> list[dict[str, Any]]:
    """Loads claim requests only when the user is an admin or business owner,
    mirroring loadUserProfile's conditional fetch in AppContext.tsx."""
    if user and (user.is_admin or user.is_business_owner):
        return db_service.fetch_claim_requests(supabase)
    return []


# ==================== HOME ====================


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    q: str = "",
    vibe: Optional[list[str]] = Query(default=None),
    city: str = "",
    min_rating: Optional[str] = None,
    radius: Optional[str] = None,
    user_lat: Optional[str] = None,
    user_lng: Optional[str] = None,
    user: Optional[User] = Depends(get_current_user),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """GET / : shop list plus map with rating, city, and radius filters."""
    selected_vibes = vibe or []
    min_rating_val = _parse_optional_float(min_rating)
    radius_val = _parse_optional_float(radius)
    user_lat_val = _parse_optional_float(user_lat)
    user_lng_val = _parse_optional_float(user_lng)

    try:
        shops = db_service.fetch_shops(supabase)
    except Exception:
        shops = []

    cities = sorted(
        {
            shop.get("location", {}).get("city", "").strip()
            for shop in shops
            if shop.get("location", {}).get("city", "").strip()
        }
    )

    query = q.lower().strip()
    selected_city = city.strip()

    def matches(shop: dict[str, Any]) -> bool:
        if query:
            haystacks = [
                shop.get("name", ""),
                shop.get("location", {}).get("city", ""),
                shop.get("location", {}).get("state", ""),
                shop.get("description", ""),
            ]
            text_match = any(query in (h or "").lower() for h in haystacks)
            vibe_match = any(query in (v or "").lower() for v in shop.get("vibes", []))
            if not (text_match or vibe_match):
                return False
        if selected_vibes:
            shop_vibes = shop.get("vibes", [])
            if not all(v in shop_vibes for v in selected_vibes):
                return False
        if selected_city:
            shop_city = (shop.get("location", {}).get("city") or "").strip()
            if shop_city.lower() != selected_city.lower():
                return False
        if min_rating_val is not None and min_rating_val > 0:
            shop_rating = float(shop.get("peopleSayRating") or shop.get("rating") or 0)
            if shop_rating < min_rating_val:
                return False
        if radius_val is not None and radius_val > 0 and user_lat_val is not None and user_lng_val is not None:
            shop_lat = float(shop.get("location", {}).get("lat") or 0)
            shop_lng = float(shop.get("location", {}).get("lng") or 0)
            if shop_lat == 0 and shop_lng == 0:
                return False
            dist = _calculate_distance_km(user_lat_val, user_lng_val, shop_lat, shop_lng)
            shop["distance"] = round(dist, 1)
            if dist > radius_val:
                return False
        elif user_lat_val is not None and user_lng_val is not None:
            shop_lat = float(shop.get("location", {}).get("lat") or 0)
            shop_lng = float(shop.get("location", {}).get("lng") or 0)
            if shop_lat != 0 or shop_lng != 0:
                dist = _calculate_distance_km(user_lat_val, user_lng_val, shop_lat, shop_lng)
                shop["distance"] = round(dist, 1)
        return True

    filtered_shops = [shop for shop in shops if matches(shop)]
    if radius_val is not None and radius_val > 0 and user_lat_val is not None and user_lng_val is not None:
        filtered_shops.sort(key=lambda s: s.get("distance", float("inf")))

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "user": user,
            "shops": filtered_shops,
            "cities": cities,
            "selected_city": selected_city,
            "selected_min_rating": min_rating_val,
            "selected_radius": radius_val,
            "user_lat": user_lat_val,
            "user_lng": user_lng_val,
            "search_query": q,
            "selected_vibes": selected_vibes,
            "standard_vibe_options": [v for group in STANDARD_VIBES.values() for v in group],
        },
    )


# ==================== SHOP DETAIL ====================


@router.get("/shop/{shop_id}", response_class=HTMLResponse)
def shop_detail(
    shop_id: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """GET /shop/{shop_id} : gallery, vibes, reviews, vibe voting, save/visit, claim link."""
    try:
        shops = db_service.fetch_shops(supabase)
    except Exception:
        shops = []

    shop = _shop_by_id(shops, shop_id)
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    claim_requests = _load_claim_requests_for(user, supabase)
    pending_request = None
    if user:
        for r in claim_requests:
            if r.get("shop_id") == shop_id and r.get("user_id") == user.id and r.get("status") == "pending":
                pending_request = r
                break

    is_saved = bool(user and shop_id in (user.saved_shops or []))
    is_visited = bool(user and shop_id in (user.visited_shops or []))
    is_owner = bool(user and (shop.get("claimedBy") == user.id or user.is_admin))
    is_claimed_owner = bool(user and shop.get("claimedBy") == user.id and not user.is_admin)

    community = _get_shop_community(shop, user, supabase)

    vibe_ratings = shop.get("vibeRatings") or {}
    vibe_score_classes = {
        vibe: _get_vibe_score_class(rating.get("score", 0)) for vibe, rating in vibe_ratings.items()
    }

    facility_labels = {key: label for key, label in FACILITY_FIELDS}
    facilities = shop.get("facilities") or {}
    enabled_facilities = [
        facility_labels.get(key, key)
        for key, value in facilities.items()
        if key != "customFacilities" and value is True
    ]
    custom_facilities = facilities.get("customFacilities") or []

    all_cheeky_vibes = [v for group in CHEEKY_VIBES_OPTIONS.values() for v in group]

    return templates.TemplateResponse(
        request,
        "shop_detail.html",
        {
            "user": user,
            "shop": shop,
            "is_saved": is_saved,
            "is_visited": is_visited,
            "is_owner": is_owner,
            "is_claimed_owner": is_claimed_owner,
            "pending_request": pending_request,
            "savers": community["savers"],
            "visitors": community["visitors"],
            "vibe_score_classes": vibe_score_classes,
            "enabled_facilities": enabled_facilities,
            "custom_facilities": custom_facilities,
            "all_cheeky_vibes": all_cheeky_vibes,
            "days_of_week": DAYS_OF_WEEK,
        },
    )


@router.post("/shop/{shop_id}/upload-photo")
async def shop_upload_photo(
    shop_id: str,
    request: Request,
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> dict[str, Any]:
    """
    Uploads community photos to a shop's gallery pending admin approval.

    Mirrors ShopDetail.tsx's handlePhotoUpload: new images are inserted as
    type 'community' with approved=False until an admin approves them.
    """
    form = await request.form()
    images = [f for f in form.getlist("images") if _is_uploaded_file(f) and f.filename]
    if not images:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No photos were provided.")

    uploaded_files = []
    for image in images:
        content = await image.read()
        uploaded_files.append((content, image.content_type or "image/jpeg"))

    try:
        upload_result = storage_service.upload_images(uploaded_files, "shops")
    except Exception as upload_error:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(upload_error) or "Failed to upload photos.",
        ) from upload_error

    new_images = [
        {
            "url": url,
            "publicId": upload_result["publicIds"][index],
            "type": "community",
            "approved": False,
            "uploadedBy": user.id,
        }
        for index, url in enumerate(upload_result["urls"])
    ]

    result = db_service.add_shop_images(supabase, shop_id, new_images)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(result.get("error") or "Images uploaded but failed to save to database."),
        )

    return {"success": True, "count": len(new_images)}


# ==================== ADD SPOT ====================


@router.get("/add", response_class=HTMLResponse)
def add_spot_form(
    request: Request,
    user: User = Depends(require_user),
) -> HTMLResponse:
    """GET /add : create shop form, matches AddSpot.tsx."""
    return templates.TemplateResponse(
        request,
        "add_spot.html",
        {
            "user": user,
            "standard_vibes": STANDARD_VIBES,
            "cheeky_vibes_options": CHEEKY_VIBES_OPTIONS,
            "parking_options": PARKING_OPTIONS,
            "facility_fields": FACILITY_FIELDS,
            "days_of_week": DAYS_OF_WEEK,
            "form_data": {},
            "selected_vibes": [],
            "selected_cheeky_vibes": [],
            "error": None,
        },
    )


@router.post("/add", response_class=HTMLResponse)
async def add_spot_submit(
    request: Request,
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """POST /add : creates the shop, mirrors AddSpot.tsx's handleSubmit."""
    form = await request.form()

    name = str(form.get("name") or "").strip()
    city = str(form.get("city") or "").strip()
    state = str(form.get("state") or "").strip()
    area = str(form.get("area") or "").strip()
    address = str(form.get("address") or "").strip()
    description = str(form.get("description") or "").strip()
    parking = str(form.get("parking") or "Unknown")
    coordinates = db_service.get_coordinates(address)
    if coordinates:
        lat, lng = coordinates
    else:
        lat = float(form.get("lat") or 0)
        lng = float(form.get("lng") or 0)

    selected_vibes = form.getlist("vibes")
    selected_cheeky_vibes = form.getlist("cheeky_vibes")

    facilities = {key: (form.get(key) == "on") for key, _ in FACILITY_FIELDS}
    open_hours = {day: str(form.get(f"hours_{day}") or "") for day in DAYS_OF_WEEK}

    images = [f for f in form.getlist("images") if _is_uploaded_file(f) and f.filename]

    error: Optional[str] = None
    if not address:
        error = "Please paste the Google Maps URL for this spot."
    elif not images:
        error = "Please upload at least one photo."
    elif not selected_vibes:
        error = "Please select at least one standard vibe."

    if error:
        return templates.TemplateResponse(
            request,
            "add_spot.html",
            {
                "user": user,
                "standard_vibes": STANDARD_VIBES,
                "cheeky_vibes_options": CHEEKY_VIBES_OPTIONS,
                "parking_options": PARKING_OPTIONS,
                "facility_fields": FACILITY_FIELDS,
                "days_of_week": DAYS_OF_WEEK,
                "form_data": {
                    "name": name, "city": city, "state": state, "area": area,
                    "address": address, "description": description,
                },
                "selected_vibes": selected_vibes,
                "selected_cheeky_vibes": selected_cheeky_vibes,
                "error": error,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    uploaded_files: list[tuple[bytes, str]] = []
    for image in images:
        content = await image.read()
        uploaded_files.append((content, image.content_type or "image/jpeg"))

    try:
        upload_result = storage_service.upload_images(uploaded_files, "shops")
    except Exception as upload_error:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "add_spot.html",
            {
                "user": user,
                "standard_vibes": STANDARD_VIBES,
                "cheeky_vibes_options": CHEEKY_VIBES_OPTIONS,
                "parking_options": PARKING_OPTIONS,
                "facility_fields": FACILITY_FIELDS,
                "days_of_week": DAYS_OF_WEEK,
                "form_data": {
                    "name": name, "city": city, "state": state, "area": area,
                    "address": address, "description": description,
                },
                "selected_vibes": selected_vibes,
                "selected_cheeky_vibes": selected_cheeky_vibes,
                "error": str(upload_error) or "Failed to upload photos.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    gallery_images = [
        {"url": url, "publicId": upload_result["publicIds"][index], "type": "owner", "uploadedBy": user.id}
        for index, url in enumerate(upload_result["urls"])
    ]

    shop_data = {
        "name": name,
        "description": description,
        "lat": lat,
        "lng": lng,
        "address": address,
        "city": city,
        "state": state,
        "area": area or None,
        "vibes": selected_vibes,
        "cheekyVibes": selected_cheeky_vibes,
        "parking": parking,
        "facilities": facilities,
        "openHours": open_hours,
        "images": gallery_images,
    }

    result = db_service.create_shop(supabase, shop_data)
    if not result.get("success"):
        return templates.TemplateResponse(
            request,
            "add_spot.html",
            {
                "user": user,
                "standard_vibes": STANDARD_VIBES,
                "cheeky_vibes_options": CHEEKY_VIBES_OPTIONS,
                "parking_options": PARKING_OPTIONS,
                "facility_fields": FACILITY_FIELDS,
                "days_of_week": DAYS_OF_WEEK,
                "form_data": {
                    "name": name, "city": city, "state": state, "area": area,
                    "address": address, "description": description,
                },
                "selected_vibes": selected_vibes,
                "selected_cheeky_vibes": selected_cheeky_vibes,
                "error": str(result.get("error") or "Failed to create shop."),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/add/generate-description")
async def add_spot_generate_description(
    request: Request,
    user: User = Depends(require_user),
) -> dict[str, str]:
    """AJAX endpoint backing AddSpot.tsx's 'Generate with AI' button."""
    form = await request.form()
    name = str(form.get("name") or "")
    city = str(form.get("city") or "")
    area = str(form.get("area") or "") or None
    vibes = form.getlist("vibes")
    cheeky_vibes = form.getlist("cheeky_vibes")
    parking = str(form.get("parking") or "Unknown")
    facilities = {key: (form.get(key) == "on") for key, _ in FACILITY_FIELDS}
    open_hours = {day: str(form.get(f"hours_{day}") or "") for day in DAYS_OF_WEEK}

    description = gemini_service.generate_shop_description(
        name=name,
        vibes=list(vibes),
        city=city,
        area=area,
        cheeky_vibes=list(cheeky_vibes),
        parking=parking,
        facilities=facilities,
        open_hours=open_hours,
    )
    return {"description": description}


# ==================== EDIT SHOP ====================


@router.post("/edit-shop/{shop_id}/generate-description")
async def edit_shop_generate_description(
    shop_id: str,
    request: Request,
    user: User = Depends(require_user),
) -> dict[str, str]:
    """AJAX endpoint backing EditShop.tsx's 'Regenerate with AI' button."""
    form = await request.form()
    name = str(form.get("name") or "")
    city = str(form.get("city") or "")
    area = str(form.get("area") or "") or None
    vibes = form.getlist("vibes")
    cheeky_vibes = form.getlist("cheeky_vibes")
    parking = str(form.get("parking") or "Unknown")
    facilities = {key: (form.get(key) == "on") for key, _ in FACILITY_FIELDS}
    open_hours = {day: str(form.get(f"hours_{day}") or "") for day in DAYS_OF_WEEK}

    description = gemini_service.generate_shop_description(
        name=name,
        vibes=list(vibes),
        city=city,
        area=area,
        cheeky_vibes=list(cheeky_vibes),
        parking=parking,
        facilities=facilities,
        open_hours=open_hours,
    )
    return {"description": description}


@router.get("/edit-shop/{shop_id}", response_class=HTMLResponse)
def edit_shop_form(
    shop_id: str,
    request: Request,
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """GET /edit-shop/{shop_id} : owner/admin only, matches EditShop.tsx."""
    try:
        shops = db_service.fetch_shops(supabase)
    except Exception:
        shops = []

    shop = _shop_by_id(shops, shop_id)
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    if shop.get("claimedBy") != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to edit this shop.",
        )

    is_claimed_owner = shop.get("claimedBy") == user.id and not user.is_admin

    return templates.TemplateResponse(
        request,
        "edit_shop.html",
        {
            "user": user,
            "shop": shop,
            "is_claimed_owner": is_claimed_owner,
            "standard_vibes": STANDARD_VIBES,
            "cheeky_vibes_options": CHEEKY_VIBES_OPTIONS,
            "parking_options": PARKING_OPTIONS,
            "facility_fields": FACILITY_FIELDS,
            "days_of_week": DAYS_OF_WEEK,
            "error": None,
        },
    )


@router.post("/edit-shop/{shop_id}", response_class=HTMLResponse)
async def edit_shop_submit(
    shop_id: str,
    request: Request,
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """POST /edit-shop/{shop_id} : updates shop details, mirrors EditShop.tsx."""
    try:
        shops = db_service.fetch_shops(supabase)
    except Exception:
        shops = []

    shop = _shop_by_id(shops, shop_id)
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    if shop.get("claimedBy") != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to edit this shop.",
        )

    is_claimed_owner = shop.get("claimedBy") == user.id and not user.is_admin

    form = await request.form()
    name = str(form.get("name") or "").strip()
    city = str(form.get("city") or "").strip()
    state = str(form.get("state") or "").strip()
    area = str(form.get("area") or "").strip()
    address = str(form.get("address") or "").strip()
    coordinates = db_service.get_coordinates(address)
    if coordinates:
        lat, lng = coordinates
    else:
        lat = float(form.get("lat") or shop["location"]["lat"])
        lng = float(form.get("lng") or shop["location"]["lng"])
    parking = str(form.get("parking") or "Unknown")
    facilities = {key: (form.get(key) == "on") for key, _ in FACILITY_FIELDS}
    custom_facility_list = [f for f in form.getlist("custom_facilities") if f]

    if is_claimed_owner:
        # Owners can only update the basic business details and facilities,
        # mirroring the isClaimedOwner branch of EditShop.tsx's handleSubmit.
        owner_facilities: dict[str, Any] = dict(facilities)
        owner_facilities["customFacilities"] = custom_facility_list
        updates = {
            "name": name,
            "city": city,
            "state": state,
            "area": area,
            "address": address,
            "lat": lat,
            "lng": lng,
            "parking": parking,
            "facilities": owner_facilities,
        }
        result = db_service.update_shop_in_db(supabase, shop_id, updates)
        if not result.get("success"):
            return templates.TemplateResponse(
                request,
                "edit_shop.html",
                {
                    "user": user,
                    "shop": shop,
                    "is_claimed_owner": is_claimed_owner,
                    "standard_vibes": STANDARD_VIBES,
                    "cheeky_vibes_options": CHEEKY_VIBES_OPTIONS,
                    "parking_options": PARKING_OPTIONS,
                    "facility_fields": FACILITY_FIELDS,
                    "days_of_week": DAYS_OF_WEEK,
                    "error": str(result.get("error") or "Could not update shop details."),
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return RedirectResponse(url=f"/shop/{shop_id}", status_code=status.HTTP_303_SEE_OTHER)

    # Full editor path (admin, or non claimed-owner editor).
    description = str(form.get("description") or "").strip()
    selected_vibes = form.getlist("vibes")
    selected_cheeky_vibes = form.getlist("cheeky_vibes")
    open_hours = {day: str(form.get(f"hours_{day}") or "") for day in DAYS_OF_WEEK}

    new_images = [f for f in form.getlist("images") if _is_uploaded_file(f) and f.filename]
    kept_urls = set(form.getlist("kept_images"))

    existing_gallery = shop.get("gallery") or []
    kept_gallery = [img for img in existing_gallery if img.get("url") in kept_urls]
    removed_images = [img for img in existing_gallery if img.get("url") not in kept_urls]

    if new_images:
        uploaded_files = []
        for image in new_images:
            content = await image.read()
            uploaded_files.append((content, image.content_type or "image/jpeg"))
        try:
            upload_result = storage_service.upload_images(uploaded_files, "shops")
        except Exception as upload_error:  # noqa: BLE001
            return templates.TemplateResponse(
                request,
                "edit_shop.html",
                {
                    "user": user,
                    "shop": shop,
                    "is_claimed_owner": is_claimed_owner,
                    "standard_vibes": STANDARD_VIBES,
                    "cheeky_vibes_options": CHEEKY_VIBES_OPTIONS,
                    "parking_options": PARKING_OPTIONS,
                    "facility_fields": FACILITY_FIELDS,
                    "days_of_week": DAYS_OF_WEEK,
                    "error": str(upload_error) or "Failed to upload photos.",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        new_gallery_images = [
            {"url": url, "publicId": upload_result["publicIds"][index], "type": "owner"}
            for index, url in enumerate(upload_result["urls"])
        ]
    else:
        new_gallery_images = []

    if removed_images:
        removed_public_ids = [img["publicId"] for img in removed_images if img.get("publicId")]
        for public_id in removed_public_ids:
            storage_service.delete_image(public_id, is_admin=user.is_admin)
        db_service.delete_shop_images(supabase, removed_public_ids)

    if new_gallery_images:
        db_service.add_shop_images(supabase, shop_id, new_gallery_images)

    full_facilities: dict[str, Any] = dict(facilities)
    full_facilities["customFacilities"] = custom_facility_list
    updates = {
        "name": name,
        "description": description,
        "city": city,
        "state": state,
        "area": area,
        "address": address,
        "lat": lat,
        "lng": lng,
        "vibes": selected_vibes,
        "cheeky_vibes": selected_cheeky_vibes,
        "open_hours": open_hours,
        "parking": parking,
        "facilities": full_facilities,
    }
    result = db_service.update_shop_in_db(supabase, shop_id, updates)
    if not result.get("success"):
        return templates.TemplateResponse(
            request,
            "edit_shop.html",
            {
                "user": user,
                "shop": shop,
                "is_claimed_owner": is_claimed_owner,
                "standard_vibes": STANDARD_VIBES,
                "cheeky_vibes_options": CHEEKY_VIBES_OPTIONS,
                "parking_options": PARKING_OPTIONS,
                "facility_fields": FACILITY_FIELDS,
                "days_of_week": DAYS_OF_WEEK,
                "error": str(result.get("error") or "Failed to update shop."),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url=f"/shop/{shop_id}", status_code=status.HTTP_303_SEE_OTHER)


# ==================== AUTH ====================


def _safe_next_path(next_path: Optional[str]) -> str:
    """Only allow same-site relative redirects, never an absolute/external URL."""
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return "/"


@router.get("/auth", response_class=HTMLResponse)
def auth_form(
    request: Request,
    mode: str = "login",
    next: str = "/",
    notice: Optional[str] = None,
    user: Optional[User] = Depends(get_current_user),
) -> HTMLResponse:
    """GET /auth : login and signup tabs, matches Auth.tsx."""
    safe_next = _safe_next_path(next)
    if user:
        return RedirectResponse(url=safe_next, status_code=status.HTTP_303_SEE_OTHER)

    mode = mode if mode in ("login", "signup") else "login"
    return templates.TemplateResponse(
        request,
        "auth.html",
        {
            "user": None,
            "mode": mode,
            "error": None,
            "next": safe_next,
            "notice": "To write a review please signup" if notice == "review" else None,
        },
    )


@router.post("/auth", response_class=HTMLResponse)
async def auth_submit(request: Request) -> HTMLResponse:
    """POST /auth : handles both login and signup submissions."""
    form = await request.form()
    mode = str(form.get("mode") or "login")
    email = str(form.get("email") or "").strip()
    password = str(form.get("password") or "")
    username = str(form.get("username") or "").strip()
    safe_next = _safe_next_path(str(form.get("next") or "/"))

    def render_error(message: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "auth.html",
            {"user": None, "mode": mode, "error": message, "next": safe_next},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not email or not password:
        return render_error("Please fill in all required fields")
    if mode == "signup" and not username:
        return render_error("Please enter a username")
    if len(password) < 6:
        return render_error("Password must be at least 6 characters")

    if mode == "signup":
        result = sign_up(email, password)
        if not result.success:
            return render_error(result.error or "Failed to create account")
        if result.user_id:
            profile_client = get_request_supabase_client(request)
            db_service.create_user_profile(profile_client, result.user_id, username, email)
        return RedirectResponse(
            url=f"/auth?mode=login&next={safe_next}", status_code=status.HTTP_303_SEE_OTHER
        )

    result = log_in(email, password)
    if not result.success or not result.access_token:
        return render_error(result.error or "Invalid email or password")

    response = RedirectResponse(url=safe_next, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=result.access_token,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    """Logs the user out and clears the session cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    log_out(token)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# ==================== PROFILE ====================


def _compute_profile_context(
    viewed_user: dict[str, Any],
    current_user: Optional[User],
    shops: list[dict[str, Any]],
    supabase,
) -> dict[str, Any]:
    """Reproduces the gamification and passport book logic from Profile.tsx."""
    saved_shop_ids = set(viewed_user.get("savedShops") or [])
    visited_shop_ids = set(viewed_user.get("visitedShops") or [])
    viewed_user_id = viewed_user.get("id")

    saved_spots = [s for s in shops if s["id"] in saved_shop_ids]
    visited_spots = [s for s in shops if s["id"] in visited_shop_ids]
    claimed_spots = [s for s in shops if s.get("claimedBy") == viewed_user_id]

    passport_book: dict[str, list[dict[str, Any]]] = {}
    for shop in visited_spots:
        key = f"{shop['location']['city']}, {shop['location']['state']}"
        passport_book.setdefault(key, []).append(shop)

    user_review_count = sum(
        1
        for shop in shops
        for review in shop.get("reviews", [])
        if review.get("userId") == viewed_user_id
    )
    drip_score = (
        len(visited_spots) * 10
        + len(saved_spots) * 5
        + user_review_count * 20
        + len(claimed_spots) * 50
    )

    unique_cities_visited = len({s["location"]["city"] for s in visited_spots})
    matcha_spots_visited = sum(1 for s in visited_spots if "Matcha" in s.get("vibes", []))

    badges = [
        {
            "id": "first-sip", "name": "First Sip", "desc": "Visit your first spot",
            "icon": "mug-hot", "unlocked": len(visited_spots) >= 1,
        },
        {
            "id": "tastemaker", "name": "Tastemaker", "desc": "Leave 3 Reviews",
            "icon": "feather", "unlocked": user_review_count >= 3,
        },
        {
            "id": "nomad", "name": "The Nomad", "desc": "Visit 3 Cities",
            "icon": "globe", "unlocked": unique_cities_visited >= 3,
        },
        {
            "id": "matcha-fix", "name": "Green Goddess", "desc": "Visit 3 Matcha Spots",
            "icon": "leaf", "unlocked": matcha_spots_visited >= 3,
        },
        {
            "id": "curator", "name": "The Curator", "desc": "Save 5 Spots",
            "icon": "bookmark", "unlocked": len(saved_spots) >= 5,
        },
        {
            "id": "boss", "name": "The Boss", "desc": "Claim a Shop",
            "icon": "briefcase", "unlocked": len(claimed_spots) >= 1,
        },
    ]

    following_ids = viewed_user.get("followingIds") or []
    follower_ids = viewed_user.get("followerIds") or []

    following_profiles = db_service.fetch_user_profiles_basic(supabase, following_ids)
    follower_profiles = db_service.fetch_user_profiles_basic(supabase, follower_ids)

    is_following = bool(
        current_user and viewed_user_id in (current_user.following_ids or [])
    )

    return {
        "saved_spots": saved_spots,
        "visited_spots": visited_spots,
        "claimed_spots": claimed_spots,
        "passport_book": passport_book,
        "drip_score": drip_score,
        "badges": badges,
        "following_profiles": following_profiles,
        "follower_profiles": follower_profiles,
        "is_following": is_following,
    }


@router.get("/profile", response_class=HTMLResponse)
def own_profile(
    request: Request,
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """GET /profile : own profile view, matches Profile.tsx (isOwnProfile branch)."""
    try:
        shops = db_service.fetch_shops(supabase)
    except Exception:
        shops = []

    viewed_user = user.model_dump(by_alias=True)
    context = _compute_profile_context(viewed_user, user, shops, supabase)

    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "viewed_user": viewed_user,
            "is_own_profile": True,
            **context,
        },
    )


@router.get("/profile/{user_id}", response_class=HTMLResponse)
def public_profile(
    user_id: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """GET /profile/{user_id} : public profile view, matches Profile.tsx."""
    if user and (user.id == user_id or user.username.lower() == user_id.lower()):
        return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)

    profile = db_service.fetch_user_profile_by_username(supabase, user_id)
    if not profile:
        profile = db_service.fetch_user_profile(supabase, user_id)

    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
        shops = db_service.fetch_shops(supabase)
    except Exception:
        shops = []

    context = _compute_profile_context(profile, user, shops, supabase)

    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "viewed_user": profile,
            "is_own_profile": False,
            **context,
        },
    )


@router.post("/profile/edit")
async def edit_profile_submit(
    request: Request,
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> RedirectResponse:
    """Handles the profile edit form submission from profile.html (Profile.tsx's handleSave)."""
    form = await request.form()
    username = str(form.get("username") or user.username).strip()
    bio = str(form.get("bio") or "")
    instagram = str(form.get("instagram") or "")
    x = str(form.get("x") or "")
    avatar_file = form.get("avatar")

    final_avatar_url = user.avatar_url
    if _is_uploaded_file(avatar_file) and avatar_file.filename:
        content = await avatar_file.read()
        try:
            upload_result = storage_service.upload_image(
                content, avatar_file.content_type or "image/jpeg", "avatars"
            )
            final_avatar_url = upload_result["url"]
        except Exception:  # noqa: BLE001
            pass

    db_service.update_user_profile(
        supabase,
        user.id,
        username=username,
        bio=bio,
        avatar_url=final_avatar_url,
        instagram=instagram,
        x=x,
    )

    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)


# ==================== CLAIM SHOP ====================


@router.get("/claim/{shop_id}", response_class=HTMLResponse)
def claim_shop_form(
    shop_id: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """GET /claim/{shop_id} : matches ClaimShop.tsx, including its logged out state."""
    try:
        shops = db_service.fetch_shops(supabase)
    except Exception:
        shops = []

    shop = _shop_by_id(shops, shop_id)
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    return templates.TemplateResponse(
        request,
        "claim_shop.html",
        {"user": user, "shop": shop, "error": None},
    )


@router.post("/claim/{shop_id}", response_class=HTMLResponse)
async def claim_shop_submit(
    shop_id: str,
    request: Request,
    user: User = Depends(require_user),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """POST /claim/{shop_id} : submits a claim request, mirrors ClaimShop.tsx's handleSubmit."""
    try:
        shops = db_service.fetch_shops(supabase)
    except Exception:
        shops = []

    shop = _shop_by_id(shops, shop_id)
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    form = await request.form()
    business_email = str(form.get("business_email") or "").strip()
    role = str(form.get("role") or "Owner")
    social_link = str(form.get("social_link") or "").strip()

    if not business_email or not social_link:
        return templates.TemplateResponse(
            request,
            "claim_shop.html",
            {
                "user": user,
                "shop": shop,
                "error": "Please fill in the business email and social media link.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    result = db_service.submit_claim_request(
        supabase,
        {
            "shopId": shop_id,
            "userId": user.id,
            "businessEmail": business_email,
            "role": role,
            "socialLink": social_link,
        },
    )

    if not result.get("success"):
        return templates.TemplateResponse(
            request,
            "claim_shop.html",
            {
                "user": user,
                "shop": shop,
                "error": str(result.get("error") or "Failed to submit claim request. Please try again."),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url=f"/shop/{shop_id}", status_code=status.HTTP_303_SEE_OTHER)


# ==================== ADMIN DASHBOARD ====================


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    user: User = Depends(require_admin),
    supabase=Depends(get_request_supabase_client),
) -> HTMLResponse:
    """GET /admin : pending images, claim requests, admin-only, matches AdminDashboard.tsx."""
    try:
        shops = db_service.fetch_shops(supabase)
    except Exception:
        shops = []

    pending_images_result = db_service.fetch_pending_shop_images(supabase)
    pending_images = pending_images_result.get("images", [])

    for image in pending_images:
        shop = _shop_by_id(shops, image.get("shop_id"))
        image["shop_name"] = shop["name"] if shop else "Unknown spot"

    claim_requests = db_service.fetch_claim_requests(supabase)
    pending_requests = [r for r in claim_requests if r.get("status") == "pending"]
    approved_requests = [r for r in claim_requests if r.get("status") == "approved"]

    for request_row in pending_requests + approved_requests:
        shop = _shop_by_id(shops, request_row.get("shop_id"))
        request_row["shop_name"] = shop["name"] if shop else "Unknown Shop"

    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "user": user,
            "pending_images": pending_images,
            "pending_requests": pending_requests,
            "approved_requests": approved_requests,
        },
    )
