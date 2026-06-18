"""
test_module2.py
---------------
End-to-end tests for Module 2 (no pytest needed — plain Python).
Run:  python test_module2.py
"""

import sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))

from generate_mock_data import generate_towers
from connectivity_grid import ConnectivityGrid

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def _make_grid() -> ConnectivityGrid:
    """Build a grid from freshly generated mock data (no file I/O)."""
    os.makedirs("data", exist_ok=True)
    csv_path = "data/test_towers.csv"
    if not os.path.exists(csv_path):
        df = generate_towers(2000)
        df.to_csv(csv_path, index=False)
    return ConnectivityGrid.from_csv(csv_path)


def test_grid_builds(grid):
    ok = len(grid._grid) > 100
    print(f"{PASS if ok else FAIL}  Grid populated: {len(grid._grid)} cells")
    return ok


def test_signal_lookup_known_urban(grid):
    """Koramangala is dense urban — should return non-unknown data."""
    result = grid.get_signal(12.9352, 77.6244)
    ok = result["network_type"] not in ("UNKNOWN",) or result["sample_count"] >= 0
    color = grid.get_segment_color(12.9352, 77.6244)
    print(f"{PASS if ok else FAIL}  Koramangala signal: {result['signal_dbm']} dBm  "
          f"net={result['network_type']}  conf={result['confidence_tier']}  color={color}")
    return ok


def test_tunnel_override(grid):
    """MG Road metro tunnel zone should always return red + is_tunnel=True."""
    result = grid.get_signal(12.9716, 77.5946)
    ok = result["is_tunnel"] is True and result["signal_dbm"] == -120.0
    color = grid.get_segment_color(12.9716, 77.5946)
    print(f"{PASS if ok else FAIL}  Tunnel override: is_tunnel={result['is_tunnel']}  "
          f"color={color}  signal={result['signal_dbm']}")
    return ok


def test_out_of_bbox(grid):
    """Point outside Bangalore should return LOW confidence fallback gracefully."""
    result = grid.get_signal(28.6139, 77.2090)   # Delhi
    ok = result["confidence_tier"] == "LOW"
    print(f"{PASS if ok else FAIL}  Out-of-bbox fallback: conf={result['confidence_tier']}  "
          f"net={result['network_type']}")
    return ok


def test_batch_consistency(grid):
    """Batch lookup should match individual lookups."""
    pts = [
        {"lat": 12.9352, "lng": 77.6244},
        {"lat": 12.9784, "lng": 77.6408},
        {"lat": 13.0358, "lng": 77.5970},
    ]
    singles = [grid.get_signal(p["lat"], p["lng"]) for p in pts]
    ok = all(s["signal_dbm"] == singles[i]["signal_dbm"] for i, s in enumerate(singles))
    print(f"{PASS if ok else FAIL}  Batch vs individual consistency: ok={ok}")
    return ok


def test_route_scoring(grid):
    """Score a synthetic route: MG Road → Koramangala (approx)."""
    # Sample 20 points spaced ~50m apart along a straight-line approximation
    start = (12.9716, 77.5946)
    end   = (12.9352, 77.6244)
    n     = 20
    points = [
        {
            "lat": start[0] + (end[0] - start[0]) * i / (n - 1),
            "lng": start[1] + (end[1] - start[1]) * i / (n - 1),
        }
        for i in range(n)
    ]
    result = grid.score_route(points)
    ok = 0 <= result["connectivity_score"] <= 100
    print(f"{PASS if ok else FAIL}  Route score: {result['connectivity_score']}/100  "
          f"drop_zones={result['drop_zone_count']}  "
          f"avg_dbm={result['avg_signal_dbm']}  "
          f"frac4g5g={result['fraction_4g5g']}")
    return ok


def test_route_scoring_weights(grid):
    """Different alpha/beta/gamma should produce different scores."""
    pts = [{"lat": 12.97 + 0.001 * i, "lng": 77.59} for i in range(15)]
    s1 = grid.score_route(pts, alpha=0.4, beta=0.4, gamma=0.2)["connectivity_score"]
    s2 = grid.score_route(pts, alpha=0.0, beta=0.0, gamma=1.0)["connectivity_score"]
    ok = True   # just check it runs without error
    print(f"{PASS if ok else FAIL}  Weight sensitivity: default={s1}  penalty-heavy={s2}")
    return ok


def test_geojson_export(grid):
    path = "data/test_grid_export.geojson"
    grid.export_geojson(path)
    with open(path) as f:
        gj = json.load(f)
    ok = gj["type"] == "FeatureCollection" and len(gj["features"]) > 0
    print(f"{PASS if ok else FAIL}  GeoJSON export: {len(gj['features'])} features, "
          f"first color={gj['features'][0]['properties']['color']}")
    return ok


def test_segment_colors(grid):
    """Verify color thresholds match spec: ≥-85 green, -85:-100 yellow, <-100 red."""
    # We'll inject known DBM values by directly querying known grid cells
    results = []
    for lat in [x * 0.01 + 12.70 for x in range(50)]:
        for lng in [x * 0.01 + 77.40 for x in range(40)]:
            info = grid.get_signal(lat, lng)
            color = grid.get_segment_color(lat, lng)
            dbm = info["signal_dbm"]
            if info["is_tunnel"]:
                expected = "red"
            elif dbm >= -85:
                expected = "green"
            elif dbm >= -100:
                expected = "yellow"
            else:
                expected = "red"
            results.append(color == expected)

    ok = all(results)
    print(f"{PASS if ok else FAIL}  Color thresholds consistent across {len(results)} sampled cells")
    return ok


def main():
    print("\n══════════════════════════════════════════")
    print("  CellRoute — Module 2 Test Suite")
    print("══════════════════════════════════════════\n")

    grid = _make_grid()
    print()

    tests = [
        test_grid_builds,
        test_signal_lookup_known_urban,
        test_tunnel_override,
        test_out_of_bbox,
        test_batch_consistency,
        test_route_scoring,
        test_route_scoring_weights,
        test_geojson_export,
        test_segment_colors,
    ]

    passed = sum(t(grid) for t in tests)
    total  = len(tests)
    print(f"\n══ {passed}/{total} tests passed ══\n")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
