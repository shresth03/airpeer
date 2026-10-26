"""Google Routes API trip comparison and CO2 estimates."""
import json
from pathlib import Path

import requests

ROOT = Path(__file__).parent
URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = ",".join([
    "routes.distanceMeters", "routes.duration", "routes.polyline.encodedPolyline",
    "routes.legs.steps.travelMode", "routes.legs.steps.distanceMeters",
    "routes.legs.steps.transitDetails.transitLine.vehicle.type",
    "routes.legs.steps.transitDetails.transitLine.nameShort",
])
MODES = {"DRIVE": "Driving", "TRANSIT": "Transit", "BICYCLE": "Cycling", "WALK": "Walking"}
# Google transit vehicle types -> our emission factor keys. Anything else falls back to bus.
VEHICLE_FACTOR = {
    "SUBWAY": "metro", "METRO_RAIL": "metro", "MONORAIL": "metro",
    "TRAM": "tram", "LIGHT_RAIL": "tram",
    "RAIL": "rail", "HEAVY_RAIL": "rail", "COMMUTER_TRAIN": "rail",
    "HIGH_SPEED_TRAIN": "rail", "LONG_DISTANCE_TRAIN": "rail",
}
DEMO_FILE = ROOT / "data" / "demo_route.json"


def load_factors():
    return json.loads((ROOT / "data" / "clean" / "emission_factors.json").read_text())


def fetch_all(origin, destination, api_key, timeout=15):
    """Call computeRoutes once per mode; return {mode: raw JSON or {'error': ...}}."""
    raw = {}
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK}
    for mode in MODES:
        body = {"origin": {"address": origin}, "destination": {"address": destination}, "travelMode": mode}
        if mode == "DRIVE":
            body["routingPreference"] = "TRAFFIC_AWARE"
        try:
            r = requests.post(URL, headers=headers, json=body, timeout=timeout)
            raw[mode] = r.json() if r.ok else {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
        except requests.RequestException as e:
            raw[mode] = {"error": str(e)}
    return {"origin": origin, "destination": destination, "responses": raw}


def _seconds(duration):
    return float(duration.rstrip("s")) if duration else 0.0


def summarise(raw, factors=None):
    """Turn raw responses into one option per mode with time, distance, CO2 and polyline."""
    factors = factors or load_factors()
    options = []
    for mode, label in MODES.items():
        resp = raw["responses"].get(mode, {})
        routes = resp.get("routes") or []
        if not routes:
            options.append({"mode": mode, "label": label, "available": False,
                            "reason": resp.get("error", "No route found for this mode.")})
            continue
        route = routes[0]
        km = route.get("distanceMeters", 0) / 1000
        steps = [s for leg in route.get("legs", []) for s in leg.get("steps", [])]
        lines = []
        if mode == "DRIVE":
            co2 = km * factors["car"]["kg_co2e_per_km"]
        elif mode == "TRANSIT":
            co2 = 0.0
            for s in steps:
                if s.get("travelMode") != "TRANSIT":
                    continue  # walking legs inside a transit trip are zero
                line = s.get("transitDetails", {}).get("transitLine", {})
                key = VEHICLE_FACTOR.get(line.get("vehicle", {}).get("type"), "bus")
                co2 += s.get("distanceMeters", 0) / 1000 * factors[key]["kg_co2e_per_km"]
                lines.append(f"{line.get('nameShort') or key} ({key})")
        else:
            co2 = 0.0
        options.append({"mode": mode, "label": label, "available": True, "km": km,
                        "minutes": _seconds(route.get("duration")) / 60, "kg_co2": co2,
                        "polyline": route.get("polyline", {}).get("encodedPolyline"), "lines": lines})
    return options


def recommend(options, tolerance_min=15):
    """Lowest-CO2 option whose extra time over driving is within tolerance (driving itself always qualifies)."""
    avail = [o for o in options if o["available"]]
    if not avail:
        return None
    drive = next((o for o in avail if o["mode"] == "DRIVE"), None)
    base = drive["minutes"] if drive else min(o["minutes"] for o in avail)
    ok = [o for o in avail if o["minutes"] - base <= tolerance_min]
    return min(ok, key=lambda o: (o["kg_co2"], o["minutes"]))


def fastest_and_alternative(options, tolerance_min=15):
    """Return (fastest, alternative, within_tolerance).

    The alternative is the lowest-CO2 option that is greener than the fastest and at most
    tolerance_min slower. If none fits, it is the greener option closest to fitting, i.e. the
    one with the least extra time (within_tolerance=False). It is None when the fastest option
    is already the cleanest.
    """
    avail = [o for o in options if o["available"]]
    if not avail:
        return None, None, False
    fastest = min(avail, key=lambda o: o["minutes"])
    greener = [o for o in avail if o is not fastest and o["kg_co2"] < fastest["kg_co2"]]
    if not greener:
        return fastest, None, False
    within = [o for o in greener if o["minutes"] - fastest["minutes"] <= tolerance_min]
    if within:
        return fastest, min(within, key=lambda o: (o["kg_co2"], o["minutes"])), True
    return fastest, min(greener, key=lambda o: (o["minutes"], o["kg_co2"])), False


def yearly_saving_kg(baseline, chosen, trips_per_week=3, weeks=52):
    """CO2 saved per year by taking chosen instead of baseline, return trip, trips_per_week days a week."""
    if not baseline or not chosen:
        return None
    return (baseline["kg_co2"] - chosen["kg_co2"]) * 2 * trips_per_week * weeks


def load_demo():
    return json.loads(DEMO_FILE.read_text())


if __name__ == "__main__":
    import sys
    import tomllib

    key = tomllib.loads((ROOT / ".streamlit" / "secrets.toml").read_text())["GOOGLE_MAPS_API_KEY"]
    origin, dest = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else (
        "Stockholm Central Station, Stockholm", "KTH Royal Institute of Technology, Stockholm")
    raw = fetch_all(origin, dest, key)
    DEMO_FILE.write_text(json.dumps(raw, indent=1))
    opts = summarise(raw)
    for o in opts:
        print(o["label"], {k: o[k] for k in ("km", "minutes", "kg_co2", "lines") if k in o} or o["reason"])
    print("Recommended:", recommend(opts)["label"])
