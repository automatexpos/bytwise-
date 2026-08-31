"""
Python translation of services/geminiService.ts.

Uses the `google-genai` pip package (the Python equivalent of the
@google/genai npm package) with the same model, 'gemini-2.5-flash', the
same prompt construction, and the same fallback text used when no API
key is configured or the API call fails.
"""

from typing import Any, Optional

from google import genai

from app.config import get_settings

MODEL_NAME = "gemini-2.5-flash"


def _build_prompt(
    name: str,
    vibes: list[str],
    city: str,
    area: Optional[str] = None,
    cheeky_vibes: Optional[list[str]] = None,
    parking: Optional[str] = None,
    facilities: Optional[dict[str, bool]] = None,
    open_hours: Optional[dict[str, str]] = None,
) -> str:
    """Builds the same prompt string assembled in geminiService.ts."""
    cheeky_vibes = cheeky_vibes or []
    facilities = facilities or {}
    open_hours = open_hours or {}

    area_part = f", {area}" if area else ""
    vibes_part = ", ".join(vibes)
    cheeky_part = ", ".join(cheeky_vibes) or "none"
    parking_part = parking or "unknown"

    facilities_part = ", ".join(
        key for key, enabled in facilities.items() if enabled
    ) or "none"

    hours_part = "; ".join(
        f"{day}: {value}" for day, value in open_hours.items() if value
    ) or "not provided"

    return (
        "Write a short, useful, locally relevant description (max 2 sentences) "
        f'for a cafe, restaurant, bakery, chai spot, or hidden gem named "{name}" '
        f"in {city}{area_part}. Standard vibes: {vibes_part}. "
        f"Cheeky vibes: {cheeky_part}. Parking: {parking_part}. "
        f"Facilities: {facilities_part}. Opening hours: {hours_part}."
    )


def generate_shop_description(
    name: str,
    vibes: list[str],
    city: str,
    area: Optional[str] = None,
    cheeky_vibes: Optional[list[str]] = None,
    parking: Optional[str] = None,
    facilities: Optional[dict[str, bool]] = None,
    open_hours: Optional[dict[str, str]] = None,
) -> str:
    """
    Generates a short shop description using the Gemini API.

    Python equivalent of generateShopDescription in geminiService.ts.
    Returns a deterministic fallback description if GEMINI_API_KEY is not
    configured, and a slightly different fallback if the API call itself
    fails, matching the two distinct fallback strings used in the
    original.

    Parameters mirror the `details` object from the TS signature
    (area, cheekyVibes, parking, facilities, openHours), flattened into
    keyword arguments.
    """
    settings = get_settings()

    if not settings.is_gemini_configured:
        return (
            f"A wonderful coffee shop named {name} located in {city}. "
            f"Known for being {', '.join(vibes)}."
        )

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = _build_prompt(
            name, vibes, city, area, cheeky_vibes, parking, facilities, open_hours
        )

        response: Any = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        return response.text or "A hidden gem waiting to be discovered."
    except Exception as error:  # noqa: BLE001
        print(f"Gemini API Error: {error}")
        return f"A fantastic spot in {city} known for {', '.join(vibes)}."
