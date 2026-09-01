"""
Pydantic models mirroring every interface and enum in the original
TypeScript types.ts file.

Field names are snake_case for idiomatic Python, but each model accepts
and can emit the original camelCase field names via aliases, so JSON
payloads can match the shapes used by the original React frontend and by
dbService.ts when it maps database rows to these shapes.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


def to_camel(snake_str: str) -> str:
    """Converts a snake_case field name to camelCase for aliasing."""
    parts = snake_str.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class CamelModel(BaseModel):
    """Base model that accepts and serializes camelCase aliases."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class Vibe(str, Enum):
    """Mirrors the Vibe enum in types.ts."""

    COZY = "Cozy"
    LAPTOP_FRIENDLY = "Laptop Friendly"
    FAST_WIFI = "Fast Wifi"
    MATCHA = "Matcha"
    SPECIALTY = "Specialty"
    OUTDOOR_SEATING = "Outdoor"
    MINIMALIST = "Minimalist"
    AESTHETIC = "Aesthetic"
    PLANTS = "Plants"
    LATTE_ART = "Latte Art"
    QUIET = "Quiet"


class Review(CamelModel):
    """Mirrors the Review interface in types.ts."""

    id: str
    user_id: str = Field(alias="userId")
    username: str
    avatar_url: str = Field(alias="avatarUrl")
    rating: float
    comment: str
    date: str


class Location(CamelModel):
    """Mirrors the Location interface in types.ts."""

    lat: float
    lng: float
    address: str
    city: str
    state: str
    area: Optional[str] = None


class ShopImage(CamelModel):
    """Mirrors the ShopImage interface in types.ts."""

    id: Optional[str] = None
    url: str
    public_id: Optional[str] = Field(default=None, alias="publicId")
    type: str  # 'owner' or 'community'
    approved: Optional[bool] = None
    uploaded_by: Optional[str] = Field(default=None, alias="uploadedBy")
    caption: Optional[str] = None


class VibeRating(CamelModel):
    """Mirrors the VibeRating interface in types.ts."""

    up: int
    down: int
    total: int
    score: int
    current_user_vote: Optional[str] = Field(default=None, alias="currentUserVote")


class OpenHours(CamelModel):
    """Mirrors the OpenHours interface in types.ts."""

    monday: Optional[str] = None
    tuesday: Optional[str] = None
    wednesday: Optional[str] = None
    thursday: Optional[str] = None
    friday: Optional[str] = None
    saturday: Optional[str] = None
    sunday: Optional[str] = None


class ShopFacilities(CamelModel):
    """Mirrors the anonymous `facilities` object on the Shop interface."""

    has_prayer_area: Optional[bool] = Field(default=None, alias="PrayerArea")
    has_clean_washrooms: Optional[bool] = Field(default=None, alias="CleanWashrooms")
    has_baby_changing: Optional[bool] = Field(default=None, alias="BabyChanging")
    is_wheelchair_accessible: Optional[bool] = Field(
        default=None, alias="isWheelchairAccessible"
    )
    has_ac: Optional[bool] = Field(default=None, alias="Ac")
    has_power_outlets: Optional[bool] = Field(default=None, alias="PowerOutlets")
    has_wifi: Optional[bool] = Field(default=None, alias="Wifi")
    is_pet_friendly: Optional[bool] = Field(default=None, alias="PetFriendly")
    custom_facilities: Optional[List[str]] = Field(default=None, alias="customFacilities")


class Shop(CamelModel):
    """Mirrors the Shop interface in types.ts."""

    id: str
    name: str
    description: str
    location: Location
    gallery: List[ShopImage] = Field(default_factory=list)
    vibes: List[str] = Field(default_factory=list)
    vibe_ratings: Optional[dict[str, VibeRating]] = Field(
        default=None, alias="vibeRatings"
    )
    cheeky_vibes: List[str] = Field(default_factory=list, alias="cheekyVibes")
    rating: float
    review_count: int = Field(alias="reviewCount")
    reviews: List[Review] = Field(default_factory=list)
    is_claimed: bool = Field(alias="isClaimed")
    claimed_by: Optional[str] = Field(default=None, alias="claimedBy")
    stamp_count: int = Field(alias="stampCount")
    saved_count: int = Field(default=0, alias="savedCount")
    open_hours: Optional[OpenHours] = Field(default=None, alias="openHours")
    parking: Optional[str] = None
    facilities: Optional[ShopFacilities] = None


class SocialLinks(CamelModel):
    """Mirrors the SocialLinks interface in types.ts."""

    instagram: Optional[str] = None
    x: Optional[str] = None


class User(CamelModel):
    """Mirrors the User interface in types.ts."""

    id: str
    username: str
    email: str
    avatar_url: str = Field(alias="avatarUrl")
    bio: Optional[str] = None
    social_links: Optional[SocialLinks] = Field(default=None, alias="socialLinks")
    is_business_owner: bool = Field(alias="isBusinessOwner")
    is_admin: Optional[bool] = Field(default=False, alias="isAdmin")
    saved_shops: List[str] = Field(default_factory=list, alias="savedShops")
    visited_shops: List[str] = Field(default_factory=list, alias="visitedShops")
    follower_ids: Optional[List[str]] = Field(default=None, alias="followerIds")
    following_ids: Optional[List[str]] = Field(default=None, alias="followingIds")


class ClaimRequest(CamelModel):
    """Mirrors the ClaimRequest interface in types.ts."""

    id: str
    shop_id: str = Field(alias="shopId")
    user_id: str = Field(alias="userId")
    business_email: str = Field(alias="businessEmail")
    role: str
    social_link: str = Field(alias="socialLink")
    status: str  # 'pending' | 'approved' | 'rejected'
    date: str
