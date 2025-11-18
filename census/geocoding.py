"""
Geocoding utilities for Religious Ecologies project.

Uses Nominatim (OpenStreetMap) for geocoding with respectful rate limiting.
"""

import logging
import time
from typing import Optional, Tuple
from urllib.parse import urlencode

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Rate limiting: Nominatim requires 1 request per second maximum
NOMINATIM_RATE_LIMIT = 1.0  # seconds between requests
_last_request_time = 0


class GeocodingError(Exception):
    """Custom exception for geocoding errors."""

    pass


def _rate_limit():
    """Enforce rate limiting for Nominatim API requests."""
    global _last_request_time
    current_time = time.time()
    time_since_last_request = current_time - _last_request_time

    if time_since_last_request < NOMINATIM_RATE_LIMIT:
        sleep_time = NOMINATIM_RATE_LIMIT - time_since_last_request
        logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
        time.sleep(sleep_time)

    _last_request_time = time.time()


def geocode_address(
    address: str,
    city: Optional[str] = None,
    county: Optional[str] = None,
    state: Optional[str] = None,
) -> Tuple[Optional[float], Optional[float], str]:
    """
    Geocode an address using Nominatim (OpenStreetMap).

    Args:
        address: Street address to geocode
        city: City name (optional, improves accuracy)
        county: County name (optional, improves accuracy)
        state: State code (optional, improves accuracy)

    Returns:
        Tuple of (latitude, longitude, status):
        - latitude: Float latitude or None if geocoding failed
        - longitude: Float longitude or None if geocoding failed
        - status: "success", "failed", or "skipped"

    Raises:
        GeocodingError: If there's a critical error with the geocoding service
    """
    # Skip if no address provided
    if not address or not address.strip():
        logger.info("Skipping geocoding: no address provided")
        return None, None, "skipped"

    # Build full address string for better accuracy
    address_parts = [address.strip()]
    if city:
        address_parts.append(city.strip())
    if county:
        # Nominatim handles county better with "County" suffix
        county_name = county.strip()
        if not county_name.lower().endswith("county"):
            county_name = f"{county_name} County"
        address_parts.append(county_name)
    if state:
        address_parts.append(state.strip())

    full_address = ", ".join(address_parts)
    logger.info(f"Geocoding address: {full_address}")

    # Enforce rate limiting
    _rate_limit()

    # Build Nominatim API request
    base_url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": full_address,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
        "countrycodes": "us",  # Restrict to US for historical census data
    }

    # Set user agent as required by Nominatim usage policy
    headers = {
        "User-Agent": getattr(
            settings,
            "GEOCODING_USER_AGENT",
            "ReligiousEcologies/1.0 (Django geocoding)",
        )
    }

    try:
        response = requests.get(
            f"{base_url}?{urlencode(params)}", headers=headers, timeout=10
        )
        response.raise_for_status()

        results = response.json()

        if not results:
            logger.warning(f"Geocoding failed: no results found for '{full_address}'")
            return None, None, "failed"

        # Extract coordinates from first result
        result = results[0]
        lat = float(result["lat"])
        lon = float(result["lon"])

        logger.info(f"Successfully geocoded '{full_address}' to ({lat:.6f}, {lon:.6f})")
        return lat, lon, "success"

    except requests.exceptions.RequestException as e:
        logger.error(f"Geocoding request failed for '{full_address}': {e}")
        raise GeocodingError(f"Geocoding service error: {e}")

    except (KeyError, ValueError, IndexError) as e:
        logger.error(f"Error parsing geocoding response for '{full_address}': {e}")
        return None, None, "failed"


def should_geocode(instance) -> bool:
    """
    Determine if a ReligiousBody instance should be geocoded.

    Returns True if:
    - Address is provided
    - Coordinates are missing OR address/location has changed

    Args:
        instance: ReligiousBody model instance

    Returns:
        Boolean indicating whether geocoding should be performed
    """
    # Always skip if no address
    if not instance.address or not instance.address.strip():
        return False

    # Geocode if coordinates are missing
    if instance.latitude is None or instance.longitude is None:
        return True

    # Check if address or location has changed (requires checking DB state)
    if instance.pk:
        try:
            from census.models import ReligiousBody

            old_instance = ReligiousBody.objects.get(pk=instance.pk)

            # Re-geocode if address changed
            if old_instance.address != instance.address:
                logger.info(
                    f"Address changed from '{old_instance.address}' to '{instance.address}'"
                )
                return True

            # Re-geocode if location (city/county/state) changed
            if old_instance.location_id != instance.location_id:
                logger.info("Location changed, re-geocoding")
                return True

        except Exception as e:
            logger.error(f"Error checking if geocoding needed: {e}")
            # If we can't determine, geocode to be safe
            return True

    # Don't geocode if coordinates exist and nothing changed
    return False
