# Backend Core Notes

This is document lists every function created while porting the TypeScript
data layer of the source project (`/home/user/workspace/dripmap_src`) into
the Python FastAPI backend at `/home/user/workspace/bytwise/app/`. No HTTP
routes or templates were built, this is the core layer only. The next
engineer should wire FastAPI routers in `app/routers/` against these
functions.

Nothing in this layer uses a Cloudinary unsigned upload preset or a
Supabase service role key. Uploads are now signed server side, and every
database call runs through a request scoped, user authenticated Supabase
client so Row Level Security policies apply exactly as they did in the
original browser app.

## app/config.py

- `class Settings(BaseModel)`: holds `supabase_url`, `supabase_anon_key`,
  `cloudinary_cloud_name`, `cloudinary_api_key`, `cloudinary_api_secret`,
  `gemini_api_key`, plus `is_supabase_configured`, `is_cloudinary_configured`,
  and `is_gemini_configured` properties.
- `get_settings() -> Settings`: cached settings loader (reads env vars,
  accepts both `SUPABASE_URL`/`SUPABASE_ANON_KEY` and the `VITE_` prefixed
  equivalents used by the original .env files).
- Module level `settings = get_settings()` for convenient importing.

## app/models.py

Pydantic models, all inherit from `CamelModel` (which sets
`model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)`),
so they accept and can emit camelCase JSON matching the original
types.ts shapes while using snake_case attribute names in Python.

- `to_camel(snake_str: str) -> str`
- `class Vibe(str, Enum)`: COZY, LAPTOP_FRIENDLY, FAST_WIFI, MATCHA,
  SPECIALTY, OUTDOOR_SEATING, MINIMALIST, AESTHETIC, PLANTS, LATTE_ART, QUIET
- `class Review(CamelModel)`: id, user_id, username, avatar_url, rating,
  comment, date
- `class Location(CamelModel)`: lat, lng, address, city, state, area (optional)
- `class ShopImage(CamelModel)`: id (optional), url, public_id (optional),
  type, approved (optional), uploaded_by (optional), caption (optional)
- `class VibeRating(CamelModel)`: up, down, total, score, current_user_vote (optional)
- `class OpenHours(CamelModel)`: monday..sunday, all optional
- `class ShopFacilities(CamelModel)`: has_prayer_area, has_clean_washrooms,
  has_baby_changing, is_wheelchair_accessible, has_ac, has_power_outlets,
  has_wifi, is_pet_friendly, custom_facilities (all optional), mirrors the
  anonymous `facilities` object on the Shop interface in types.ts
- `class Shop(CamelModel)`: id, name, description, location, gallery,
  vibes, vibe_ratings (optional), cheeky_vibes, rating, review_count,
  reviews, is_claimed, claimed_by (optional), stamp_count, open_hours
  (optional), parking (optional), facilities (optional)
- `class SocialLinks(CamelModel)`: instagram (optional), x (optional)
- `class User(CamelModel)`: id, username, email, avatar_url, bio
  (optional), social_links (optional), is_business_owner, is_admin
  (optional, default False), saved_shops, visited_shops, follower_ids
  (optional), following_ids (optional)
- `class ClaimRequest(CamelModel)`: id, shop_id, user_id, business_email,
  role, social_link, status, date

## app/constants.py

- `STANDARD_VIBES: dict[str, list[str]]`
- `CHEEKY_VIBES_OPTIONS: dict[str, list[str]]`
- `STANDARD_VIBE_OPTIONS: list[str]` (flattened STANDARD_VIBES values)
- `PARKING_OPTIONS: list[str]`

Note: the source constants.ts spelled the "workStudy" entry with an em
dash and an accented character ("WFC" plus a dash plus "Work From Cafe"
with an accented e). It was rewritten here as "WFC, Work From Cafe"
(comma, no accent) per the no em dash rule. If the exact original
characters are required by a database migration or seed script, adjust
that one string in `CHEEKY_VIBES_OPTIONS["workStudy"]`.

## app/database.py

- `get_supabase_client(access_token: str | None = None) -> Client`:
  returns a `supabase.Client` built from `SUPABASE_URL` + `SUPABASE_ANON_KEY`.
  When `access_token` is supplied, calls `client.postgrest.auth(access_token)`
  and attempts `client.auth.set_session(access_token, access_token)` so RLS
  policies see the same `auth.uid()` the browser client's session did.
  Never uses a service role key.

## app/security.py

- `SESSION_COOKIE_NAME = "sb_access_token"`
- `class AuthResult`: dataclass with success, access_token, refresh_token,
  user_id, email, error
- `sign_up(email: str, password: str) -> AuthResult`
- `log_in(email: str, password: str) -> AuthResult`
- `log_out(access_token: str | None) -> None`
- `reset_auth_state(access_token: str | None) -> None`: server side
  equivalent of `resetSupabaseAuthState` in authUtils.ts (signs out;
  clearing the cookie itself is the route layer's job, mirroring how
  clearing `sb-*` localStorage keys was the browser client's job)
- `get_access_token_from_request(request: Request) -> str | None`
- `get_request_supabase_client(request: Request) -> Client`: FastAPI
  dependency, request scoped authenticated Supabase client
- `get_current_user(request: Request) -> User | None`: FastAPI dependency,
  reads the `sb_access_token` cookie, calls `supabase.auth.get_user`, then
  `db_service.fetch_user_profile`
- `require_user(user: User | None = Depends(get_current_user)) -> User`:
  raises 401 if not logged in
- `require_admin(user: User | None = Depends(get_current_user)) -> User`:
  raises 401 if not logged in, 403 if not an admin

## app/services/db_service.py

Every function takes `supabase: Client` as its first argument (the
request scoped authenticated client from `get_supabase_client`).

- `retry_with_backoff(fn, max_retries=3, base_delay=1.0, operation_name="operation") -> T`
- `fetch_user_profile(supabase, user_id: str) -> dict | None`
- `fetch_user_profile_by_username(supabase, username: str) -> dict | None`
- `toggle_follow_user(supabase, follower_id: str, following_id: str, is_currently_following: bool) -> dict`
- `create_user_profile(supabase, user_id: str, username: str, email: str) -> dict`
- `update_user_profile(supabase, user_id: str, username=None, bio=None, avatar_url=None, instagram=None, x=None) -> dict`
- `fetch_shops(supabase) -> list[dict]`
- `create_shop(supabase, shop_data: dict) -> dict`
- `add_shop_images(supabase, shop_id: str, images: list[dict]) -> dict`
- `fetch_pending_shop_images(supabase) -> dict`
- `approve_shop_image(supabase, image_id: str) -> dict`
- `delete_shop_images(supabase, public_ids: list[str]) -> dict`
- `delete_shop_image(supabase, image_id: str) -> dict`
- `vote_on_vibe(supabase, user_id: str, shop_id: str, vibe: str, vote: str) -> dict`
- `update_shop_in_db(supabase, shop_id: str, updates: dict) -> dict`
- `add_review(supabase, shop_id: str, user_id: str, rating: float, comment: str) -> dict`
- `toggle_saved_shop(supabase, user_id: str, shop_id: str, is_saved: bool) -> dict`
- `toggle_visited_shop(supabase, user_id: str, shop_id: str, is_visited: bool) -> dict`
- `submit_claim_request(supabase, request: dict) -> dict`
- `fetch_claim_requests(supabase) -> list[dict]`
- `approve_claim_request(supabase, request_id: str) -> dict`

All 19 exported dbService.ts functions are represented (fetchUserProfile,
fetchUserProfileByUsername, toggleFollowUser, createUserProfile,
updateUserProfile, fetchShops, createShop, addShopImages,
fetchPendingShopImages, approveShopImage, deleteShopImages,
deleteShopImage, voteOnVibe, updateShopInDB, addReview, toggleSavedShop,
toggleVisitedShop, submitClaimRequest, fetchClaimRequests,
approveClaimRequest), plus the retryWithBackoff utility.

Table names, column names, and upsert conflict targets are unchanged:
`profiles`, `saved_shops`, `visited_shops`, `user_follows`, `shops`,
`shop_images`, `vibe_votes` (upsert on `user_id,shop_id,vibe`),
`reviews`, `claim_requests`. `fetch_shops` keeps the same 3 retry, 1
second base delay backoff policy as `fetchShops` in dbService.ts, and the
same "42P01 undefined table" tolerance for a missing `vibe_votes` table.

## app/services/storage_service.py

- `upload_image(file_bytes: bytes, content_type: str, folder: str = "shops") -> dict`:
  signed Cloudinary upload (replaces the old unsigned preset browser flow
  from storageService.ts), same 5MB limit and same `bitewise/<folder>`
  folder path, returns `{success, url, publicId}`
- `upload_images(files: list[tuple[bytes, str]], folder: str = "shops") -> dict`:
  sequential multi upload, returns `{success, urls, publicIds}`
- `delete_image(public_id: str, is_admin: bool, resource_type: str = "image") -> dict`:
  merges storageService.ts's `deleteImage` (browser caller) with
  api/cloudinary-delete.ts's admin gated handler (looks up the asset,
  destroys it with `invalidate=True`). The caller must resolve `is_admin`
  via `app.security.require_admin` (which checks `profiles.is_admin`, the
  same table/column the original handler checked) before calling this
  with `is_admin=True`.
- `initialize_storage() -> bool`: no-op, always True, mirrors the original

## app/services/gemini_service.py

- `generate_shop_description(name: str, vibes: list[str], city: str, area=None, cheeky_vibes=None, parking=None, facilities=None, open_hours=None) -> str`:
  uses `google-genai`'s `genai.Client(api_key=...).models.generate_content`
  with model `"gemini-2.5-flash"`, same prompt text as geminiService.ts,
  same two fallback strings (one for "no API key configured", one for
  "API call failed").

## requirements.txt

fastapi, uvicorn[standard], jinja2, python-multipart, python-dotenv,
supabase, cloudinary, google-genai, pydantic.

## .env.example

SUPABASE_URL, SUPABASE_ANON_KEY, GEMINI_API_KEY, CLOUDINARY_CLOUD_NAME,
CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET.

## Wiring guidance for the next engineer

- Build routers under `app/routers/` (already scaffolded, empty) that call
  `app.security.get_current_user` / `require_user` / `require_admin` as
  FastAPI `Depends`, then pass the resulting Supabase client (from
  `get_request_supabase_client` or `get_supabase_client(token)`) into the
  matching `db_service` function.
- Sign up / log in routes should call `app.security.sign_up` /
  `app.security.log_in`, then set the `sb_access_token` httponly cookie
  from the returned `AuthResult.access_token`. Log out routes should call
  `app.security.log_out` (or `reset_auth_state`) and then delete the
  cookie.
- Image upload routes should accept `multipart/form-data` (via
  `python-multipart`, already in requirements.txt), read the file bytes
  and content type, then call `storage_service.upload_image` /
  `upload_images`, then persist the resulting URLs via
  `db_service.add_shop_images` or as part of `db_service.create_shop`.
- Image delete routes should depend on `app.security.require_admin`, then
  call `storage_service.delete_image(public_id, is_admin=True)` followed
  by `db_service.delete_shop_images` or `delete_shop_image` to remove the
  matching row(s).
