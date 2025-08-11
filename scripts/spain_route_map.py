#!/usr/bin/env python3
"""
Builds a driving route between saved Spain trip places using Google Maps APIs.

What it does:
- Uses your saved list of Spain places (from your memories) as stops
- If GOOGLE_MAPS_API_KEY is set, calls the Google Directions API to:
  - Optimize waypoint order
  - Compute total distance and duration
  - Generate a Static Maps image (PNG) of the full route
- Always prints a shareable Google Maps link you can open in a browser

Setup:
  export GOOGLE_MAPS_API_KEY="YOUR_KEY"

Run:
  python scripts/spain_route_map.py

Outputs:
  - Prints ordered itinerary, total distance, total duration
  - Prints a Google Maps directions link (clickable/shareable)
  - Saves a static map image to spain_route.png (when API key is provided)
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from typing import List, Dict, Any, Tuple


# Places extracted from your memories
PLACES: List[str] = [
    "Royal Monastery of El Escorial, San Lorenzo de El Escorial, Spain",
    "Royal Palace of Madrid, Madrid, Spain",
    "Almudena Cathedral, Madrid, Spain",
    "San Ginés de Arlés Church, Madrid, Spain",
    "Toledo Cathedral, Toledo, Spain",
]


def _encode_param(value: str, safe: str = "-._~|,:") -> str:
    # Encodes a single param value, allowing separators that Google APIs expect (|,:)
    return urllib.parse.quote(value, safe=safe)


def _http_get_json(url: str) -> Dict[str, Any]:
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def _http_get_binary(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def build_gmaps_share_link(places: List[str], optimized: List[int] = None) -> str:
    """
    Build a shareable Google Maps link. If optimized order is provided (indices into waypoints),
    it will be used; otherwise, the original order is used.
    """
    origin = places[0]
    destination = places[-1]

    waypoints_list = places[1:-1]
    if optimized is not None:
        waypoints_list = [places[1:-1][i] for i in optimized]

    params = {
        "api": "1",
        "origin": origin,
        "destination": destination,
        "travelmode": "driving",
    }
    if waypoints_list:
        params["waypoints"] = "|".join(waypoints_list)

    encoded = {k: _encode_param(v) for k, v in params.items()}
    query = "&".join(f"{k}={v}" for k, v in encoded.items())
    return f"https://www.google.com/maps/dir/?{query}"


def call_directions(api_key: str, places: List[str]) -> Dict[str, Any]:
    """
    Calls Google Directions API with optimize:true for waypoints.
    Returns parsed route info including waypoint order, legs, overview polyline.
    """
    base = "https://maps.googleapis.com/maps/api/directions/json"

    origin = places[0]
    destination = places[-1]
    waypoints = places[1:-1]

    params = {
        "origin": origin,
        "destination": destination,
        "mode": "driving",
        "language": "en",
        "key": api_key,
    }
    if waypoints:
        params["waypoints"] = "optimize:true|" + "|".join(waypoints)

    # Manually build query string to preserve separators correctly
    encoded_pairs = [f"{k}={_encode_param(v)}" for k, v in params.items()]
    url = f"{base}?{'&'.join(encoded_pairs)}"

    data = _http_get_json(url)
    status = data.get("status")
    if status != "OK":
        raise RuntimeError(f"Directions API error: {status} - {data.get('error_message', '')}")

    route = data["routes"][0]
    waypoint_order = route.get("waypoint_order", list(range(len(waypoints))))
    legs = route.get("legs", [])
    overview_polyline = route.get("overview_polyline", {}).get("points", "")

    return {
        "waypoint_order": waypoint_order,
        "legs": legs,
        "polyline": overview_polyline,
    }


def save_static_map(api_key: str, polyline: str, ordered_places: List[str], out_path: str = "spain_route.png") -> str:
    """
    Saves a Static Maps image for the given route polyline and places.
    """
    base = "https://maps.googleapis.com/maps/api/staticmap"

    # Build repeated markers: one per stop (labels 1..9,A..)
    def marker_label(i: int) -> str:
        # Single-character labels only. Use 1..9 then A, B, ...
        if 1 <= i <= 9:
            return str(i)
        return chr(ord("A") + (i - 10))  # 10->A, 11->B, ...

    marker_params = []
    for idx, place in enumerate(ordered_places, start=1):
        label = marker_label(idx)
        marker_value = f"color:blue|label:{label}|{place}"
        marker_params.append(("markers", marker_value))

    # Polyline must be URL-encoded fully; prepend enc:
    path_value = "enc:" + urllib.parse.quote(polyline, safe="")

    query_items: List[Tuple[str, str]] = [
        ("size", "800x600"),
        ("key", api_key),
        ("path", path_value),
    ] + marker_params

    # Manually join to avoid double-encoding
    query = "&".join(f"{k}={_encode_param(v)}" for k, v in query_items)
    url = f"{base}?{query}"

    img = _http_get_binary(url)
    with open(out_path, "wb") as f:
        f.write(img)
    return out_path


def format_distance_meters(meters: int) -> str:
    # Simple formatter (km with 1 decimal if needed)
    km = meters / 1000.0
    if km >= 10:
        return f"{int(round(km))} km"
    return f"{km:.1f} km"


def format_duration_seconds(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def main() -> None:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")

    print("Spain Trip Planned Stops (from memories):")
    for i, p in enumerate(PLACES, start=1):
        print(f"  {i}. {p}")
    print("")

    if not api_key:
        print("No GOOGLE_MAPS_API_KEY found. Skipping Directions API call.")
        share_link = build_gmaps_share_link(PLACES)
        print("Open this link for directions (original order):")
        print(share_link)
        print("\nTo compute optimized route and download a static map image, set GOOGLE_MAPS_API_KEY and re-run.")
        sys.exit(0)

    # Call Directions with optimize:true
    info = call_directions(api_key, PLACES)
    waypoint_order = info["waypoint_order"]
    legs = info["legs"]
    polyline = info["polyline"]

    # Build ordered places: start + optimized(waypoints) + end
    optimized_waypoints = [PLACES[1:-1][i] for i in waypoint_order]
    ordered_places = [PLACES[0]] + optimized_waypoints + [PLACES[-1]]

    # Compute totals
    total_meters = 0
    total_seconds = 0
    for leg in legs:
        dist = leg.get("distance", {}).get("value", 0)
        dur = leg.get("duration", {}).get("value", 0)
        total_meters += int(dist or 0)
        total_seconds += int(dur or 0)

    print("Optimized Itinerary:")
    for i, p in enumerate(ordered_places, start=1):
        print(f"  {i}. {p}")

    print(f"\nTotal Distance: {format_distance_meters(total_meters)}")
    print(f"Total Duration: {format_duration_seconds(total_seconds)}")

    # Shareable link using optimized order
    share_link = build_gmaps_share_link(PLACES, optimized=waypoint_order)
    print("\nOpen this link for directions (optimized order):")
    print(share_link)

    # Save static map image
    try:
        out_img = save_static_map(api_key, polyline, ordered_places, out_path="spain_route.png")
        print(f"\nStatic route map saved to: {out_img}")
    except Exception as e:
        print(f"\nFailed to save static map image: {e}")


if __name__ == "__main__":
    main()
