import json, math, os
from collections import defaultdict
from typing import Dict, Any, Optional

import pandas as pd
import numpy as np

# ── Constants ──────────────────────────────────────────────────────────────
BANGALORE_BBOX = {
    "lat_min": 12.70, "lat_max": 13.20,
    "lng_min": 77.40, "lng_max": 77.80,
}
GRID_SIZE_M = 100
DEG_PER_100M_LAT     = GRID_SIZE_M / 111_320
DEG_PER_100M_LNG_BASE = GRID_SIZE_M / 111_320

NET_RANK = {"NR": 4, "LTE": 3, "UMTS": 2, "GSM": 1}

MNC_TO_OPERATOR = {
    '472': 'Jio', '481': 'Jio',
    '10': 'Airtel', '98': 'Airtel',
    '20': 'Vi', '67': 'Vi',
    '1': 'BSNL', '12': 'BSNL',
    '11': 'Vodafone', '29': 'Vodafone',
}

# Known Bangalore tunnel / underground zones (lat, lng, radius_deg)
TUNNEL_ZONES = [
    (12.9716, 77.5946, 0.008),
    (12.9784, 77.5713, 0.006),
    (12.8995, 77.6700, 0.010),
]

# Confidence values per data-quality tier
CONFIDENCE_VALUES = {
    "HIGH":        0.98,
    "MEDIUM":      0.85,
    "LOW":         0.70,
    "AI_INFERRED": 0.80,
}

# Penalty applied to uncertain cells (partial — not full dead-zone)
PENALTY_VALUE = 0.50


# ── Helper functions ───────────────────────────────────────────────────────

def _lat_cell(lat: float) -> int:
    return int((lat - BANGALORE_BBOX["lat_min"]) / DEG_PER_100M_LAT)

def _lng_cell(lng: float, lat: float) -> int:
    deg_per_cell = DEG_PER_100M_LNG_BASE / math.cos(math.radians(lat))
    return int((lng - BANGALORE_BBOX["lng_min"]) / deg_per_cell)

def _cell_center(lat_idx: int, lng_idx: int) -> tuple:
    mid_lat = BANGALORE_BBOX["lat_min"] + (lat_idx + 0.5) * DEG_PER_100M_LAT
    deg_per_lng = DEG_PER_100M_LNG_BASE / math.cos(math.radians(mid_lat))
    mid_lng = BANGALORE_BBOX["lng_min"] + (lng_idx + 0.5) * deg_per_lng
    return round(mid_lat, 6), round(mid_lng, 6)

def _is_tunnel(lat: float, lng: float) -> bool:
    for tlat, tlng, r in TUNNEL_ZONES:
        if math.hypot(lat - tlat, lng - tlng) < r:
            return True
    return False

def _dominant_network(net_counts: Dict[str, int]) -> str:
    if not net_counts:
        return "UNKNOWN"
    return max(net_counts, key=lambda n: (NET_RANK.get(n, 0), net_counts[n]))


def dbm_to_percent(dbm: float) -> float:
    """
    Map dBm → [0, 1] using the spec's range: -60 dBm (ceiling) to -120 dBm (floor).
    Linear normalisation so the full range is used and routes produce different values.
    """
    return float(np.clip((dbm - (-120.0)) / ((-60.0) - (-120.0)), 0.0, 1.0))


# ── Main class ─────────────────────────────────────────────────────────────

class ConnectivityGrid:
    def __init__(self):
        self._raw: Dict[tuple, dict] = defaultdict(lambda: {
            "signals": [], "networks": defaultdict(int), "operators": defaultdict(int), "count": 0
        })
        self._grid: Dict[tuple, dict] = {}
        self._built = False
        self.ml_model = None     # injected by server.py after startup

    # ── Construction ──────────────────────────────────────────────────────

    @classmethod
    def from_csv(cls, csv_path: str) -> "ConnectivityGrid":
        print(f"📂  Loading {csv_path} …")
        df = pd.read_csv(csv_path)
        df.rename(columns={"lon": "lng"}, inplace=True, errors="ignore")

        bb = BANGALORE_BBOX
        df = df[
            (df["lat"] >= bb["lat_min"]) & (df["lat"] <= bb["lat_max"]) &
            (df["lng"] >= bb["lng_min"]) & (df["lng"] <= bb["lng_max"])
        ].copy()

        df['operator'] = df['net'].astype(str).map(MNC_TO_OPERATOR).fillna('Other')

        if "radio" in df.columns and "network_type" not in df.columns:
            radio_map = {"NR": "NR", "LTE": "LTE", "UMTS": "UMTS", "GSM": "GSM", "CDMA": "GSM"}
            df["network_type"] = df["radio"].map(radio_map).fillna("GSM")

        sig_col = next((c for c in ("averageSignal", "signal_dbm", "signal") if c in df.columns), None)
        df["signal_dbm"] = pd.to_numeric(df[sig_col], errors="coerce").fillna(-100) if sig_col else -100.0

        grid = cls()
        for _, row in df.iterrows():
            lat, lng = float(row["lat"]), float(row["lng"])
            key  = (_lat_cell(lat), _lng_cell(lng, lat))
            cell = grid._raw[key]
            cell["signals"].append(float(row["signal_dbm"]))
            net = str(row.get("network_type", "GSM")).upper()
            cell["networks"][net] += 1
            cell["operators"][str(row.get("operator", "Other"))] += 1
            cell["count"] += 1

        grid._finalise()
        return grid

    def _finalise(self):
        for key, raw in self._raw.items():
            signals = raw["signals"]
            n       = raw["count"]
            avg_dbm = float(np.mean(signals)) if signals else -110.0
            nets    = dict(raw["networks"])
            dom_net = _dominant_network(nets)
            hi_net  = nets.get("LTE", 0) + nets.get("NR", 0)
            frac_4g5g = hi_net / n if n > 0 else 0.0

            tier = "HIGH" if n >= 3 else "MEDIUM" if n >= 1 else "LOW"

            ops = dict(raw.get("operators", {}))
            dominant_operator = max(ops, key=ops.get) if ops else "Other"

            lat_c, lng_c = _cell_center(*key)
            self._grid[key] = {
                "avg_dbm":         round(avg_dbm, 1),
                "dominant_network": dom_net,
                "sample_count":    n,
                "fraction_4g5g":   round(frac_4g5g, 3),
                "confidence_tier": tier,
                "confidence":      CONFIDENCE_VALUES[tier],
                "is_tunnel":       _is_tunnel(lat_c, lng_c),
                "lat": lat_c, "lng": lng_c,
                "operator": dominant_operator,  # add this
                "operators": ops,               # add this too — all operators in cell
            }
        self._built = True

    # ── Signal lookup ──────────────────────────────────────────────────────

    def get_signal(self, lat: float, lng: float) -> Dict[str, Any]:
        """
        Priority order:
          1. Hard tunnel override → always -120 dBm, red
          2. HIGH/MEDIUM confidence cell data → use directly
          3. LOW confidence cell exists → blend with AI if available
          4. No cell data → AI prediction if available, else conservative fallback
        """
        if not self._built:
            raise RuntimeError("Grid not built.")

        # 1. Tunnel hard override
        if _is_tunnel(lat, lng):
            return {
                "signal_dbm":      -120.0,
                "network_type":    "NONE",
                "confidence":      1.0,
                "confidence_tier": "HIGH",
                "is_tunnel":       True,
                "fraction_4g5g":   0.0,
                "sample_count":    0,
            }

        key  = (_lat_cell(lat), _lng_cell(lng, lat))
        cell = self._grid.get(key)

        # 2. HIGH / MEDIUM confidence — use real data directly
        if cell and cell["confidence_tier"] in ("HIGH", "MEDIUM"):
            return {
                "signal_dbm":      cell["avg_dbm"],
                "network_type":    cell["dominant_network"],
                "confidence":      cell["confidence"],
                "confidence_tier": cell["confidence_tier"],
                "is_tunnel":       cell["is_tunnel"],
                "fraction_4g5g":   cell["fraction_4g5g"],
                "sample_count":    cell["sample_count"],
            }

        # 3 & 4. LOW confidence or missing → try AI
        if self.ml_model is not None and self.ml_model.is_trained:
            ai_dbm = float(self.ml_model.predict(lat, lng))
            # If we have a LOW-confidence cell, blend: 40% real data, 60% AI
            if cell:
                blended_dbm = 0.40 * cell["avg_dbm"] + 0.60 * ai_dbm
                frac_4g5g   = cell["fraction_4g5g"]
            else:
                blended_dbm = ai_dbm
                frac_4g5g   = 0.4   # conservative assumption
            return {
                "signal_dbm":      round(blended_dbm, 1),
                "network_type":    "AI_INFERRED",
                "confidence":      CONFIDENCE_VALUES["AI_INFERRED"],
                "confidence_tier": "AI_INFERRED",
                "is_tunnel":       False,
                "fraction_4g5g":   frac_4g5g,
                "sample_count":    cell["sample_count"] if cell else 0,
            }

        # 5. No AI — conservative fallback
        if cell:
            return {
                "signal_dbm":      cell["avg_dbm"],
                "network_type":    cell["dominant_network"],
                "confidence":      CONFIDENCE_VALUES["LOW"],
                "confidence_tier": "LOW",
                "is_tunnel":       cell["is_tunnel"],
                "fraction_4g5g":   cell["fraction_4g5g"],
                "sample_count":    cell["sample_count"],
            }

        return {
            "signal_dbm":      -110.0,
            "network_type":    "UNKNOWN",
            "confidence":      CONFIDENCE_VALUES["LOW"],
            "confidence_tier": "LOW",
            "is_tunnel":       False,
            "fraction_4g5g":   0.0,
            "sample_count":    0,
        }

    def get_segment_color(self, lat: float, lng: float) -> str:
        info = self.get_signal(lat, lng)
        if info["is_tunnel"]:
            return "red"
        dbm = info["signal_dbm"]
        return "green" if dbm >= -85 else "yellow" if dbm >= -100 else "red"

    # ── Route scoring ──────────────────────────────────────────────────────

    def score_route(
        self,
        sampled_points: list,
        alpha: float = 0.40,
        beta:  float = 0.40,
        gamma: float = 0.20,
    ) -> Dict[str, Any]:
        """
        Formula (from spec):
          raw = α·norm_avg_signal + β·fraction_4g5g − γ·(drop_zones / route_km)
          adj = raw × avg_confidence + PENALTY × (1 − avg_confidence)
          score = clip(adj, 0, 100)

        dbm_to_percent uses the spec's linear [-120, -60] normalisation so
        different routes through areas with different tower density actually
        produce different scores.
        """
        if not sampled_points:
            return {"connectivity_score": 0, "drop_zones": [], "segments": []}

        signals_norm, frac4g5gs, confidences = [], [], []
        segments = []

        for pt in sampled_points:
            info  = self.get_signal(pt["lat"], pt["lng"])
            dbm   = info["signal_dbm"]
            conf  = info["confidence"]
            color = self.get_segment_color(pt["lat"], pt["lng"])

            # Use linear spec normalisation — avoids the flat S-curve that
            # caused all routes to cluster around the same value
            signals_norm.append(dbm_to_percent(dbm))
            frac4g5gs.append(info["fraction_4g5g"])
            confidences.append(conf)

            segments.append({
                "lat":          pt["lat"],
                "lng":          pt["lng"],
                "signal":       dbm,
                "color":        color,
                "network_type": info["network_type"],
                "confidence":   conf,
                "is_tunnel":    info["is_tunnel"],
            })

        avg_signal_norm = float(np.mean(signals_norm))
        avg_frac4g5g    = float(np.mean(frac4g5gs))
        avg_conf        = float(np.mean(confidences))

        drop_zones  = _count_drop_zones([s["color"] for s in segments])
        route_km    = len(sampled_points) * 0.05   # 50 m per sample point

        raw_score = (
            alpha * avg_signal_norm
            + beta  * avg_frac4g5g
            - gamma * (drop_zones / max(route_km, 0.1))
        )
        raw_score = float(np.clip(raw_score, 0.0, 1.0))

        # Confidence-weighted adjustment
        adj_score   = raw_score * avg_conf + PENALTY_VALUE * (1.0 - avg_conf)
        final_score = round(float(np.clip(adj_score * 100, 0.0, 100.0)), 1)

        return {
            "connectivity_score": final_score,
            "avg_signal_dbm":     round(float(np.mean([s["signal"] for s in segments])), 1),
            "drop_zone_count":    drop_zones,
            "drop_zones":         _extract_drop_zones(segments),
            "segments":           segments,
        }

    # ── GeoJSON export ─────────────────────────────────────────────────────

    def export_geojson(self, path: str):
        features = []
        for key, cell in self._grid.items():
            lat, lng = cell["lat"], cell["lng"]
            half_lat = DEG_PER_100M_LAT / 2
            half_lng = (DEG_PER_100M_LNG_BASE / math.cos(math.radians(lat))) / 2
            coords = [[[
                lng - half_lng, lat - half_lat], [lng + half_lng, lat - half_lat],
                [lng + half_lng, lat + half_lat], [lng - half_lng, lat + half_lat],
                [lng - half_lng, lat - half_lat],
            ]]
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": coords},
                "properties": cell,
            })
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f)


# ── Utility helpers ────────────────────────────────────────────────────────

def _count_drop_zones(colors: list) -> int:
    """Count contiguous red stretches (each = 1 drop zone)."""
    count, in_red = 0, False
    for c in colors:
        if c == "red" and not in_red:
            count += 1
            in_red = True
        elif c != "red":
            in_red = False
    return count


def _extract_drop_zones(segments: list) -> list:
    """Return list of {start, end, is_tunnel} dicts for each red stretch."""
    zones, in_red, start = [], False, None
    for seg in segments:
        if seg["color"] == "red" and not in_red:
            in_red, start = True, seg
        elif seg["color"] != "red" and in_red:
            in_red = False
            zones.append({
                "start":     {"lat": start["lat"], "lng": start["lng"]},
                "end":       {"lat": seg["lat"],   "lng": seg["lng"]},
                "is_tunnel": start["is_tunnel"],
            })
    # Close any open zone at end of route
    if in_red and start:
        zones.append({
            "start":     {"lat": start["lat"], "lng": start["lng"]},
            "end":       {"lat": segments[-1]["lat"], "lng": segments[-1]["lng"]},
            "is_tunnel": start["is_tunnel"],
        })
    return zones
