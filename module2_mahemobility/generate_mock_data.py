"""
generate_mock_data.py
---------------------
Generates a realistic mock OpenCellID CSV for Bangalore.
Covers the FULL bounding box with strong spatial variance so that
routes through different corridors produce meaningfully different scores.

Key design choices that create route differentiation:
  - Urban cores (MG Road, Koramangala, Whitefield, Electronic City) get
    signal -70 to -80 dBm with high 4G/5G density
  - Peri-urban / rural areas get -95 to -115 dBm with mostly 2G/3G
  - Weak corridors (NICE Road arc, Hosur Road south, far north) are
    explicitly penalised → any route through them scores badly
  - Tunnel zones have NO towers (handled as hard-red in ConnectivityGrid)

Output: data/cell_towers.csv  (same schema as real OpenCellID)
"""

import os, random, math
import pandas as pd
import numpy as np

random.seed(42)
np.random.seed(42)

# ── Bangalore bounding box ──────────────────────────────────────────────────
LAT_MIN, LAT_MAX = 12.70, 13.20
LNG_MIN, LNG_MAX = 77.40, 77.80

# ── Dense urban clusters (more towers + better signal) ──────────────────────
#    (lat, lng, radius_deg, signal_boost_dBm)
URBAN_CORES = [
    (12.9716, 77.5946, 0.06, 25),   # MG Road / Cubbon Park
    (12.9352, 77.6244, 0.05, 22),   # Koramangala
    (12.9784, 77.6408, 0.05, 20),   # Indiranagar
    (12.9698, 77.7500, 0.06, 18),   # Whitefield IT corridor
    (13.0358, 77.5970, 0.05, 15),   # Hebbal
    (12.9010, 77.5800, 0.04, 18),   # JP Nagar
    (13.0827, 77.5800, 0.05, 12),   # Yelahanka
    (12.9250, 77.5000, 0.04, 14),   # Banashankari
    (13.0100, 77.6500, 0.04, 12),   # KR Puram
    (12.8400, 77.6700, 0.05, 10),   # Electronic City Phase 1
    (12.8600, 77.6600, 0.04, 12),   # Electronic City Phase 2
    (12.9200, 77.6900, 0.03, 10),   # Marathahalli
    (13.0600, 77.6400, 0.04, 10),   # Banaswadi
    (12.9800, 77.5500, 0.04, 16),   # Malleshwaram
]

# ── Weak-signal corridors (highways between cities, peri-urban) ────────────
#    Routes through these areas will score lower — this is what creates
#    meaningful differentiation between the three route types.
WEAK_CORRIDORS = [
    # NICE Road western arc (low density, peri-urban)
    {"lat_range": (12.78, 12.92), "lng_range": (77.40, 77.52), "signal_floor": -110},
    # Tumkur Road (NH-48) far north
    {"lat_range": (13.10, 13.20), "lng_range": (77.50, 77.60), "signal_floor": -108},
    # Hosur Road far south (before Electronic City)
    {"lat_range": (12.70, 12.82), "lng_range": (77.60, 77.72), "signal_floor": -105},
    # Outer ring road east (sparse)
    {"lat_range": (12.85, 12.97), "lng_range": (77.73, 77.80), "signal_floor": -107},
]

# ── Known tunnel / underpass zones (hard red — no towers) ──────────────────
TUNNEL_ZONES = [
    (12.9716, 77.5946, 0.001),   # MG Road metro underground
    (12.9784, 77.5713, 0.001),   # Majestic underpass
    (12.8995, 77.6700, 0.002),   # NICE Road tunnel stretch
]


def is_near_tunnel(lat, lng):
    for tlat, tlng, r in TUNNEL_ZONES:
        if math.hypot(lat - tlat, lng - tlng) < r:
            return True
    return False


def in_weak_corridor(lat, lng):
    for c in WEAK_CORRIDORS:
        if (c["lat_range"][0] <= lat <= c["lat_range"][1] and
                c["lng_range"][0] <= lng <= c["lng_range"][1]):
            return c["signal_floor"]
    return None


def urban_influence(lat, lng):
    """Returns (weight 0→1, signal_boost dBm)."""
    best_w, best_boost = 0.0, 0.0
    for clat, clng, r, boost in URBAN_CORES:
        d = math.hypot(lat - clat, lng - clng)
        w = max(0.0, 1.0 - d / r)
        if w > best_w:
            best_w, best_boost = w, boost
    return best_w, best_boost


def generate_towers(n=8000):
    rows = []
    attempts = 0
    while len(rows) < n and attempts < n * 5:
        attempts += 1
        lat = random.uniform(LAT_MIN, LAT_MAX)
        lng = random.uniform(LNG_MIN, LNG_MAX)

        uw, boost = urban_influence(lat, lng)

        # Bias ~55% of towers to be near urban cores
        if uw < 0.05 and random.random() < 0.55:
            clat, clng, r, boost = random.choice(URBAN_CORES)
            lat = float(np.clip(clat + random.gauss(0, r * 0.8), LAT_MIN, LAT_MAX))
            lng = float(np.clip(clng + random.gauss(0, r * 0.8), LNG_MIN, LNG_MAX))
            uw, boost = urban_influence(lat, lng)

        # No towers inside tunnel zones
        if is_near_tunnel(lat, lng):
            continue

        # Network type: urban skews heavily 4G/5G
        if uw > 0.65:
            net = random.choices(["NR", "LTE", "UMTS", "GSM"],
                                 weights=[0.30, 0.55, 0.10, 0.05])[0]
        elif uw > 0.25:
            net = random.choices(["NR", "LTE", "UMTS", "GSM"],
                                 weights=[0.08, 0.52, 0.25, 0.15])[0]
        elif uw > 0.05:
            net = random.choices(["NR", "LTE", "UMTS", "GSM"],
                                 weights=[0.02, 0.30, 0.38, 0.30])[0]
        else:
            net = random.choices(["NR", "LTE", "UMTS", "GSM"],
                                 weights=[0.00, 0.15, 0.40, 0.45])[0]

        # Signal strength — spatial gradient with high variance
        weak_floor = in_weak_corridor(lat, lng)
        if weak_floor is not None:
            base = weak_floor + random.gauss(5, 5)
        else:
            base = -105 + uw * boost + random.gauss(0, 8)

        net_bonus = {"NR": 8, "LTE": 4, "UMTS": 0, "GSM": -5}.get(net, 0)
        signal = float(np.clip(base + net_bonus, -120, -50))

        # Sample count → drives confidence tier
        if uw > 0.5:
            samples = random.randint(3, 25)
        elif uw > 0.1:
            samples = random.randint(1, 10)
        else:
            samples = random.randint(1, 4)

        rows.append({
            "mcc": random.choice([404, 405]),
            "net": random.randint(1, 99),
            "area": random.randint(100, 9999),
            "cell": random.randint(1000, 99999),
            "unit": 0,
            "lon": round(lng, 6),
            "lat": round(lat, 6),
            "range": random.randint(100, 2000),
            "samples": samples,
            "changeable": 1,
            "created": 1680000000,
            "updated": 1700000000,
            "averageSignal": round(signal, 1),
            "network_type": net,
        })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    df = generate_towers(8000)
    out = "data/cell_towers.csv"
    df.to_csv(out, index=False)
    print(f"✅  Generated {len(df)} mock towers → {out}")
    print(f"   signal: mean={df['averageSignal'].mean():.1f}, "
          f"std={df['averageSignal'].std():.1f}, "
          f"min={df['averageSignal'].min():.1f}, max={df['averageSignal'].max():.1f}")
    print(f"   lat: {df['lat'].min():.3f}–{df['lat'].max():.3f}  "
          f"lng: {df['lon'].min():.3f}–{df['lon'].max():.3f}")
    print(f"   network types: {df['network_type'].value_counts().to_dict()}")
    print(df[["lat", "lon", "averageSignal", "network_type", "samples"]].head(5))
