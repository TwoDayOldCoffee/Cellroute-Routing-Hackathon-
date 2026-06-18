# CellRoute — Module 2: Connectivity Data + Processing Layer

## What this module does

Provides a **signal lookup API** for any (lat, lng) in Bangalore.
Used by Module 1 (routing engine) to annotate route segments with connectivity data.

---

## Files

| File | Purpose |
|---|---|
| `generate_mock_data.py` | Generates realistic fake OpenCellID CSV if you don't have the real one |
| `connectivity_grid.py` | Core engine: ingests CSV, builds 100m grid, scores routes |
| `server.py` | FastAPI server exposing the endpoints below |
| `test_module2.py` | End-to-end test suite (run before integrating) |

---

## Quick Start

```bash
# 1. Install deps
pip install fastapi uvicorn pandas numpy scipy

# 2. Generate mock data (skip if you have real OpenCellID CSV)
python generate_mock_data.py
# → creates data/cell_towers.csv

# 3. Start the server
python server.py
# → http://127.0.0.1:8001

# 4. Run tests (optional but recommended)
python test_module2.py
```

### Using real OpenCellID data
Download the India CSV from https://opencellid.org/downloads  
Filter by MCC 404/405 and the Bangalore bbox, save as `data/cell_towers.csv`.  
The ingestion pipeline handles the rest automatically.

---

## API Endpoints

### `GET /signal?lat=12.97&lng=77.59`
Single-point lookup.

**Response:**
```json
{
  "signal_dbm": -78.5,
  "network_type": "LTE",
  "confidence": 0.95,
  "confidence_tier": "HIGH",
  "is_tunnel": false,
  "fraction_4g5g": 0.82,
  "sample_count": 7,
  "color": "green"
}
```

---

### `POST /signal/batch`
Batch lookup — used by Module 1 for polyline sampling.

**Request:**
```json
{ "points": [{"lat": 12.97, "lng": 77.59}, ...] }
```

**Response:**
```json
{ "results": [ { ...same fields as /signal... } ] }
```

---

### `POST /signal/score_route`
Full route scoring. Module 1 calls this with sampled points.

**Request:**
```json
{
  "points": [{"lat": 12.97, "lng": 77.59}, ...],
  "alpha": 0.4,
  "beta":  0.4,
  "gamma": 0.2
}
```

**Response:**
```json
{
  "connectivity_score": 72.4,
  "avg_signal_dbm": -81.2,
  "avg_confidence": 0.88,
  "fraction_4g5g": 0.74,
  "drop_zone_count": 2,
  "drop_zones": [
    { "start": {"lat": ..., "lng": ...}, "end": {...}, "is_tunnel": false }
  ],
  "segments": [
    { "lat": ..., "lng": ..., "signal": -78.5, "color": "green",
      "network_type": "LTE", "confidence": 0.95, "is_tunnel": false }
  ]
}
```

---

### `GET /grid/geojson`
Returns the full `connectivity_grid.geojson` for the frontend heatmap toggle.

---

## Scoring Formula (from spec)

```
raw_score = α·norm_signal + β·frac_4g5g − γ·(drop_zones / route_len_km)
adjusted  = raw_score × confidence + 0.30 × (1 − confidence)
final     = adjusted × 100   (clipped to [0, 100])
```

Weights are tunable via query params. Defaults: α=0.40, β=0.40, γ=0.20.

---

## Segment Colors

| Color | Condition |
|---|---|
| 🟢 green | signal ≥ −85 dBm |
| 🟡 yellow | −100 ≤ signal < −85 dBm |
| 🔴 red | signal < −100 dBm, OR tunnel zone |

Tunnel zones are **always red** regardless of OpenCellID data.

---

## Integration Contract (for Module 1)

Module 1 should:
1. Sample route polyline every ~50m → list of `{lat, lng}` points
2. `POST /signal/score_route` with those points
3. Use `segments` array for per-segment coloring
4. Use `connectivity_score`, `drop_zones` for route metadata

That's it — Module 1 doesn't need to call the grid directly.
