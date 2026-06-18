from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import polyline
import asyncio
import math

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OSRM_URL = "http://router.project-osrm.org/route/v1/driving"
VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"
MODULE2_URL  = "http://localhost:8001/signal/score_route"

# ── Seeded community alerts ────────────────────────────────────────────────
alerts_db = [
    {"id": 1, "type": "no_signal",   "icon": "📵", "title": "No Signal",
     "message": "Complete blackout near underpass, 160m stretch", "location": "Near NICE Road underpass",
     "lat": 12.9352, "lng": 77.6245, "age": "2h ago",  "severity": "high"},
    {"id": 2, "type": "5g_unstable", "icon": "📶", "title": "5G Unstable",
     "message": "5G drops to 4G repeatedly during peak hours", "location": "MG Road",
     "lat": 12.9716, "lng": 77.5946, "age": "5h ago",  "severity": "medium"},
    {"id": 3, "type": "weak_signal", "icon": "⚠️",  "title": "Weak Signal",
     "message": "1-2 bars only, calls drop frequently", "location": "Bannerghatta Road",
     "lat": 12.9010, "lng": 77.6069, "age": "1d ago",  "severity": "medium"},
]
_alert_counter = len(alerts_db) + 1

_route_cache = {}

# ── Pydantic models ────────────────────────────────────────────────────────

class RouteRequest(BaseModel):
    origin:      dict
    destination: dict
    mode:        str = "normal"

class AlertRequest(BaseModel):
    type:     str
    title:    str
    message:  str
    lat:      float
    lng:      float
    location: str = "Unknown location"  # TEAMMATE'S ADDITION
    severity: str = "medium"


# ── Geometry helpers ───────────────────────────────────────────────────────

def _haversine_km(a: dict, b: dict) -> float:
    R  = 6371.0
    phi1, phi2 = math.radians(a["lat"]), math.radians(b["lat"])
    dphi = math.radians(b["lat"] - a["lat"])
    dlam = math.radians(b["lng"] - a["lng"])
    h  = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def _midpoint(a: dict, b: dict) -> dict:
    return {"lat": (a["lat"] + b["lat"]) / 2, "lng": (a["lng"] + b["lng"]) / 2}


def _route_fingerprint(geometry: list, n: int = 10) -> tuple:
    step = max(1, len(geometry) // n)
    return tuple(
        (round(geometry[i]["lat"], 3), round(geometry[i]["lng"], 3))
        for i in range(0, len(geometry), step)
    )


def _subsample(geometry: list, max_points: int = 120) -> list:
    if len(geometry) <= max_points:
        return geometry
    step = len(geometry) / max_points
    return [geometry[int(i * step)] for i in range(max_points)]


# ── ANTI-BACKTRACKING: Detect routes that loop backwards ──────────────────

def _has_backtracking(geometry: list, origin: dict, dest: dict, threshold: float = 0.25) -> bool:
    """
    Detect if route has significant backtracking.
    
    Returns True if more than threshold% of segments go backwards
    relative to the origin→destination bearing.
    
    Args:
        geometry: Route coordinates
        origin: Start point
        dest: End point
        threshold: Max acceptable ratio of backward segments (default 25%)
    """
    if len(geometry) < 3:
        return False
    
    # Overall bearing from origin to destination
    overall_bearing = math.atan2(
        dest["lng"] - origin["lng"],
        dest["lat"] - origin["lat"]
    )
    
    backward_count = 0
    total_segments = len(geometry) - 1
    
    for i in range(total_segments):
        p1 = geometry[i]
        p2 = geometry[i + 1]
        
        # Segment bearing
        seg_bearing = math.atan2(
            p2["lng"] - p1["lng"],
            p2["lat"] - p1["lat"]
        )
        
        # Angle difference
        diff = abs(seg_bearing - overall_bearing)
        
        # Normalize to 0-π
        if diff > math.pi:
            diff = 2 * math.pi - diff
        
        # If angle > 100°, segment goes significantly backwards
        if diff > (100 * math.pi / 180):
            backward_count += 1
    
    backward_ratio = backward_count / total_segments
    
    # Debug: print routes with high backtracking
    if backward_ratio > threshold:
        print(f"   ⚠️  Rejected route: {backward_ratio*100:.1f}% backtracking")
    
    return backward_ratio > threshold


# ── Valhalla call ──────────────────────────────────────────────────────────

async def call_valhalla(
    origin: dict,
    destination: dict,
    costing_options: dict = None,
    waypoints: list = None,
) -> dict | None:
    locations = [{"lat": origin["lat"], "lon": origin["lng"]}]
    for wp in (waypoints or []):
        locations.append({"lat": wp["lat"], "lon": wp["lng"], "type": "through"})
    locations.append({"lat": destination["lat"], "lon": destination["lng"]})

    payload = {
        "locations": locations,
        "costing":   "auto",
        "directions_options": {"units": "kilometers"},
    }
    if costing_options:
        payload["costing_options"] = costing_options

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(VALHALLA_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        summary = data["trip"]["summary"]
        shape   = data["trip"]["legs"][0]["shape"]
        decoded = polyline.decode(shape, 6)

        return {
            "distance": summary["length"],
            "eta":      round(summary["time"] / 60),
            "geometry": [{"lat": lat, "lng": lng} for lat, lng in decoded],
        }
    except Exception as e:
        print(f"   ⚠️  Valhalla error: {e}")
        return None

async def call_osrm(origin: dict, destination: dict) -> list:
    url = (
        f"{OSRM_URL}/{origin['lng']},{origin['lat']};"
        f"{destination['lng']},{destination['lat']}"
        f"?alternatives=true&geometries=geojson&overview=full&steps=false"
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        routes = []
        for r in data.get("routes", []):
            coords = r["geometry"]["coordinates"]
            routes.append({
                "distance": r["distance"] / 1000,
                "eta": round(r["duration"] / 60),
                "geometry": [{"lat": lat, "lng": lng} for lng, lat in coords],
            })
        print(f"   OSRM returned {len(routes)} routes")
        return routes
    except Exception as e:
        print(f"   ⚠️  OSRM error: {e}")
        return []

# ── Module 2 scoring ───────────────────────────────────────────────────────

async def score_route(geometry: list) -> dict:
    points = _subsample(geometry, max_points=120)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(MODULE2_URL, json={"points": points})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"   ⚠️  Module 2 error: {e}")
        return {
            "connectivity_score": 50,
            "segments":   [{"lat": p["lat"], "lng": p["lng"], "signal": -95, "color": "yellow"} for p in points],
            "drop_zones": [],
        }


# ── Route deduplication ────────────────────────────────────────────────────

def _deduplicate(routes: list, keep: int = 6) -> list:
    seen, unique = set(), []
    for r in routes:
        if r is None:
            continue
        fp = _route_fingerprint(r["geometry"])
        if fp not in seen:
            seen.add(fp)
            unique.append(r)
        if len(unique) == keep:
            break
    return unique


# ── Main route endpoint ────────────────────────────────────────────────────

@app.post("/route")
async def get_route(req: RouteRequest):
    try:
        origin = req.origin
        dest   = req.destination
        mode   = req.mode
        dist   = _haversine_km(origin, dest)

        cache_key = f"{round(origin['lat'],3)},{round(origin['lng'],3)}-{round(dest['lat'],3)},{round(dest['lng'],3)}"

        print(f"🚗 {origin['lat']:.4f},{origin['lng']:.4f} → {dest['lat']:.4f},{dest['lng']:.4f}  ({dist:.1f} km)")

        # ── Generate diverse candidates using costing variations ─────────
        # Use Valhalla's built-in parameters instead of forced waypoints
        # This creates natural route diversity without artificial detours

        # ── Get routes from Valhalla with rate limit protection ─────────
        try:
            route1 = await call_valhalla(origin, dest, {"auto": {"shortest": True}})
            await asyncio.sleep(1)
            route2 = await call_valhalla(origin, dest)
            await asyncio.sleep(1)
            route3 = await call_valhalla(origin, dest, {"auto": {"use_highways": 1.0}})
            await asyncio.sleep(1)
            route4 = await call_valhalla(origin, dest, {"auto": {"use_highways": 0.1}})
            await asyncio.sleep(1)
            route5 = await call_valhalla(origin, dest, {"auto": {"use_tolls": 0.0}})
            await asyncio.sleep(1)
            route6 = await call_valhalla(origin, dest, {"auto": {"use_tolls": 1.0}})
            await asyncio.sleep(1)
            route7 = await call_valhalla(origin, dest, {"auto": {"use_highways": 0.5}})
            await asyncio.sleep(1)
            route8 = await call_valhalla(origin, dest, {"auto": {"use_highways": 0.7}})

            all_routes = [route1, route2, route3, route4, route5, route6, route7, route8]

            valid = [
                r for r in all_routes
                if r and not _has_backtracking(r["geometry"], origin, dest, threshold=0.40)
            ]

            if not valid and all_routes:
                print("   ⚠️  All routes filtered! Using unfiltered.")
                valid = [r for r in all_routes if r]

            if not valid:
                raise RuntimeError("No valid routes from Valhalla")

            valid = sorted(valid, key=lambda r: r["distance"])
            candidates = _deduplicate(valid, keep=6)

            # ── OSRM fallback if fewer than 3 distinct candidates ──────────
            if len(candidates) < 3:
                print("   🔄 Fewer than 3 candidates, trying OSRM...")
                osrm_routes = await call_osrm(origin, dest)
                for r in osrm_routes:
                    if not _has_backtracking(r["geometry"], origin, dest, threshold=0.40):
                        candidates.append(r)
                candidates = _deduplicate(candidates, keep=6)
                print(f"   After OSRM: {len(candidates)} candidates")

            dist_labels = [f"{round(r['distance'], 1)}km/{r['eta']}min" for r in candidates]
            print(f"   Valid candidates: {len(candidates)} → {dist_labels}")
        except Exception as e:
            print(f"   ⚠️  Routing failed: {e}")
            if cache_key in _route_cache:
                print("   📦 Serving cached routes")
                return _route_cache[cache_key]
            raise

        # ── Score all candidates in parallel ───────────────────────────
        scored_data = await asyncio.gather(*[score_route(r["geometry"]) for r in candidates])
        for r, s in zip(candidates, scored_data):
            r.update(s)

        scores = [(r["connectivity_score"], round(r["distance"], 1), r["eta"]) for r in candidates]
        print(f"   Scores: {scores}")

        # ── Select the three output routes ─────────────────────────────
        # FIXED: Always pick actual fastest, even if it's also shortest
        shortest_r = min(candidates, key=lambda r: r["distance"])
        fastest_candidates = [r for r in candidates if r is not shortest_r]
        fastest_r = min(fastest_candidates, key=lambda r: r["eta"]) if fastest_candidates else shortest_r

        taken = {id(shortest_r), id(fastest_r)}
        remaining = [r for r in candidates if id(r) not in taken]
        if not remaining:
            remaining = candidates

        min_dist = min(r["distance"] for r in candidates)

        def connected_score(r):
            dist_overhead = (r["distance"] - min_dist) / min_dist
            if dist_overhead <= 0.6:  # up to 60% longer = no penalty
                return r["connectivity_score"]
            else:  # beyond 60% longer, penalise heavily
                excess = dist_overhead - 0.6
                return r["connectivity_score"] - (50 * excess)

        connected_r = max(candidates, key=connected_score)

        shortest_r["type"]  = "shortest"
        fastest_r["type"]   = "fastest"
        connected_r["type"] = "connected"

        routes = [shortest_r, fastest_r, connected_r]

        # Emergency mode: sort by ETA, flag dead zones
        if mode == "emergency":
            routes = sorted(routes, key=lambda r: r["eta"])

        _route_cache[cache_key] = {"routes": routes}
        return {"routes": routes}

    except Exception as e:
        print(f"❌ {e}")
        raise


# ── Community alerts ───────────────────────────────────────────────────────

@app.get("/alerts")
def get_alerts():
    return {"alerts": alerts_db}

@app.post("/alerts")
def post_alert(alert: AlertRequest):
    global _alert_counter
    icon_map = {"no_signal": "📵", "5g_unstable": "📶", "weak_signal": "⚠️", "congestion": "🐌"}
    new = {
        "id":       _alert_counter,
        "type":     alert.type,
        "icon":     icon_map.get(alert.type, "📢"),
        "title":    alert.title,
        "message":  alert.message,
        "location": alert.location,  # TEAMMATE'S ADDITION
        "lat":      alert.lat,
        "lng":      alert.lng,
        "reporter": "community",
        "age":      "just now",
        "severity": alert.severity,
    }
    alerts_db.append(new)
    _alert_counter += 1
    return {"ok": True, "alert": new}