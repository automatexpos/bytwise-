"""
Python translation of services/storageService.ts and api/cloudinary-delete.ts.

The original browser client used an unsigned Cloudinary upload preset
(VITE_CLOUDINARY_UPLOAD_PRESET) because uploads happened directly from the
user's browser and could not hold a secret API key. Now that uploads run
on the server, they are switched to a signed upload using the Cloudinary
API key and secret from app.config, which is simpler and does not require
an upload preset to be configured in the Cloudinary dashboard. Delete
logic is unchanged in spirit: only admins may delete an image, mirrored
here as an explicit `is_admin` argument that the caller resolves via
app.security.require_admin before calling `delete_image`.
"""

from typing import Any, Optional

import cloudinary
import cloudinary.api
import cloudinary.uploader

from app.config import get_settings

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB, same limit as storageService.ts


def _configure_cloudinary() -> None:
    """Applies Cloudinary credentials from settings to the cloudinary SDK."""
    settings = get_settings()
    if not settings.is_cloudinary_configured:
        raise RuntimeError(
            "Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET in the environment."
        )
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


def upload_image(
    file_bytes: bytes,
    content_type: str,
    folder: str = "shops",
) -> dict[str, Any]:
    """
    Uploads a single image to Cloudinary with a signed, server side upload.

    Python equivalent of uploadImage in storageService.ts, adapted from an
    unsigned preset upload (browser side) to a signed upload (server
    side). Validates content type and file size the same way the
    original did (must be an image/* mime type, max 5MB), and uploads
    into the same `bitewise/<folder>` folder path.

    Returns
    -------
    dict with keys: success (bool), url (str, on success), publicId (str,
    on success), error (str, on failure).
    """
    if not content_type.startswith("image/"):
        raise ValueError("Invalid file type. Please upload an image file.")

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError("File too large. Maximum size is 5MB")

    _configure_cloudinary()

    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            folder=f"bitewise/{folder}",
        )
    except Exception as error:  # noqa: BLE001
        raise RuntimeError(
            getattr(error, "message", None) or str(error) or "Cloudinary image upload failed."
        ) from error

    secure_url = result.get("secure_url")
    public_id = result.get("public_id")
    if not secure_url or not public_id:
        raise RuntimeError("Cloudinary image upload failed.")

    return {"success": True, "url": secure_url, "publicId": public_id}


def upload_images(
    files: list[tuple[bytes, str]],
    folder: str = "shops",
) -> dict[str, Any]:
    """
    Uploads multiple images sequentially.

    Python equivalent of uploadImages in storageService.ts. `files` is a
    list of (file_bytes, content_type) tuples. Uploads are done one by
    one (not in parallel) to mirror the original's sequential upload
    strategy, which avoided concurrency issues with session refresh, RLS,
    or network hangs.

    Returns
    -------
    dict with keys: success (bool), urls (list[str]), publicIds (list[str]).
    """
    urls: list[str] = []
    public_ids: list[str] = []

    for file_bytes, content_type in files:
        result = upload_image(file_bytes, content_type, folder)
        urls.append(result["url"])
        public_ids.append(result.get("publicId") or "")

    return {"success": True, "urls": urls, "publicIds": public_ids}


def delete_image(public_id: str, is_admin: bool, resource_type: str = "image") -> dict[str, Any]:
    """
    Deletes an image from Cloudinary. Admin only.

    Python equivalent of the merged behavior of deleteImage in
    storageService.ts (the browser side caller, which posted to
    /api/cloudinary-delete with a bearer token) and the handler in
    api/cloudinary-delete.ts (which verified the caller's Supabase
    session, checked profiles.is_admin, then called
    cloudinary.uploader.destroy).

    The admin check itself is expected to have already happened via
    app.security.require_admin at the route layer (which loads
    profiles.is_admin the same way api/cloudinary-delete.ts did); this
    function receives that result as `is_admin` and re-enforces it here
    so the storage service cannot be called directly to bypass the
    admin gate.

    Parameters
    ----------
    public_id:
        The Cloudinary public id to delete.
    is_admin:
        Whether the caller is a platform admin. Mirrors the
        `profile?.is_admin` check in api/cloudinary-delete.ts.
    resource_type:
        Cloudinary resource type, defaults to 'image' same as the original.

    Returns
    -------
    dict with keys: success (bool), lookup (dict or None), destroy (dict).
    """
    if not is_admin:
        return {"success": False, "error": "Only administrators can delete images."}

    if not public_id or not isinstance(public_id, str):
        return {"success": False, "error": "A Cloudinary public ID is required."}

    _configure_cloudinary()

    existing_asset: Optional[dict[str, Any]] = None
    try:
        existing_asset = cloudinary.api.resource(
            public_id, resource_type=resource_type, type="upload"
        )
    except Exception as lookup_error:  # noqa: BLE001
        # Mirrors the try/except around cloudinary.api.resource in
        # api/cloudinary-delete.ts, which only logged on lookup failure
        # and continued on to attempt the destroy call regardless.
        print(f"Cloudinary lookup failed for {public_id}: {lookup_error}")

    try:
        destroy_result = cloudinary.uploader.destroy(
            public_id, resource_type=resource_type, type="upload", invalidate=True
        )
    except Exception as error:  # noqa: BLE001
        return {
            "success": False,
            "error": getattr(error, "message", None) or str(error) or "Could not delete the Cloudinary image.",
        }

    lookup_payload = None
    if existing_asset:
        lookup_payload = {
            "public_id": existing_asset.get("public_id"),
            "asset_id": existing_asset.get("asset_id"),
            "resource_type": existing_asset.get("resource_type"),
            "type": existing_asset.get("type"),
            "format": existing_asset.get("format"),
            "version": existing_asset.get("version"),
            "secure_url": existing_asset.get("secure_url"),
        }

    success = destroy_result.get("result") == "ok"
    return {"success": success, "lookup": lookup_payload, "destroy": destroy_result}


def initialize_storage() -> bool:
    """
    Verifies the storage integration is reachable.

    Python equivalent of initializeStorage in storageService.ts, which
    was a no-op that always returned True (bucket creation/verification
    was intentionally left to manual setup, per STORAGE_SETUP.md in the
    source project).
    """
    return True
