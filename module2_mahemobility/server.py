"""
server.py
---------
FastAPI server for Module 2 — Connectivity Data + Processing Layer.

Endpoints
---------
GET  /signal?lat=12.97&lng=77.59
     Single-point signal lookup.

POST /signal/batch
     Body: {"points": [{"lat": ..., "lng": ...}, ...]}
     Batch lookup for many points (used by Module 1 routing engine).

POST /signal/score_route
     Body: {"points": [...], "alpha": 0.4, "beta": 0.4, "gamma": 0.2}
     Full route scoring: returns score, segments, drop_zones.

GET  /grid/geojson
     Returns the full connectivity_grid.geojson (for frontend heatmap).

GET  /health
     Returns grid stats and status.

Usage
-----
  python server.py
  # → http://127.0.0.1:8001
"""

import os, sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import uvicorn
from signal_ai import SignalAI

# Make sure our module is importable from same dir
sys.path.insert(0, str(Path(__file__).parent))
from connectivity_grid import ConnectivityGrid

# ── Global grid instance (loaded once on startup) ─────────────────────────
_grid: Optional[ConnectivityGrid] = None
GRID_GEOJSON_PATH = "data/connectivity_grid.geojson"
CSV_PATH = "data/cell_towers.csv"


# Update your lifespan function:
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _grid
    print("🚀  Loading connectivity grid …")

    if not os.path.exists(CSV_PATH):
        print("⚠️   CSV not found — generating mock data …")
        os.system(f"python generate_mock_data.py")

    # 1. Load the standard Grid
    _grid = ConnectivityGrid.from_csv(CSV_PATH)

    # 2. Initialize and Train the AI Model [cite: 37]
    print("🧠  Training Signal Strength Regressor (AI Track) ...")
    ai_model = SignalAI()
    ai_model.train_on_existing_data(CSV_PATH)
    
    # 3. Connect (Inject) the AI into the Grid instance
    _grid.ml_model = ai_model 

    if not os.path.exists(GRID_GEOJSON_PATH):
        _grid.export_geojson(GRID_GEOJSON_PATH)

    print("✅  Connectivity Grid + AI Model ready.")
    yield
    print("👋  Shutting down.")


app = FastAPI(
    title="CellRoute — Module 2: Connectivity Layer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ────────────────────────────────────────────────────────

class Point(BaseModel):
    lat: float
    lng: float

class BatchRequest(BaseModel):
    points: List[Point]

class ScoreRouteRequest(BaseModel):
    points: List[Point]
    alpha: float = Field(default=0.40, ge=0, le=1)
    beta:  float = Field(default=0.40, ge=0, le=1)
    gamma: float = Field(default=0.20, ge=0, le=1)


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    if _grid is None:
        return {"status": "loading"}
    return {
        "status": "ok",
        "grid_cells": len(_grid._grid),
        "csv_path": CSV_PATH,
        "geojson_path": GRID_GEOJSON_PATH,
    }


@app.get("/signal")
def get_signal(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
):
    """
    Single-point signal lookup.

    Returns:
      signal_dbm, network_type, confidence, confidence_tier, is_tunnel,
      fraction_4g5g, sample_count, color
    """
    if _grid is None:
        raise HTTPException(503, "Grid not ready yet")

    result = _grid.get_signal(lat, lng)
    result["color"] = _grid.get_segment_color(lat, lng)
    return result


@app.post("/signal/batch")
def get_signal_batch(req: BatchRequest):
    """
    Batch lookup for multiple points.
    Used by Module 1 (routing engine) when sampling route polylines.
    """
    if _grid is None:
        raise HTTPException(503, "Grid not ready yet")

    results = []
    for pt in req.points:
        info = _grid.get_signal(pt.lat, pt.lng)
        info["color"] = _grid.get_segment_color(pt.lat, pt.lng)
        info["lat"] = pt.lat
        info["lng"] = pt.lng
        results.append(info)
    return {"results": results}


@app.post("/signal/score_route")
def score_route(req: ScoreRouteRequest):
    """
    Full connectivity scoring for a route.

    Accepts sampled points, returns:
      - connectivity_score (0–100)
      - avg_signal_dbm
      - fraction_4g5g
      - drop_zones  (list with start/end coords)
      - segments    (per-point colour + signal info)
    """
    if _grid is None:
        raise HTTPException(503, "Grid not ready yet")

    points = [{"lat": p.lat, "lng": p.lng} for p in req.points]
    result = _grid.score_route(
        points,
        alpha=req.alpha,
        beta=req.beta,
        gamma=req.gamma,
    )
    return result


@app.get("/grid/geojson")
def get_grid_geojson():
    """
    Returns the full connectivity GeoJSON grid.
    Frontend can use this for a heatmap toggle layer.
    """
    if not os.path.exists(GRID_GEOJSON_PATH):
        if _grid is None:
            raise HTTPException(503, "Grid not ready yet")
        _grid.export_geojson(GRID_GEOJSON_PATH)
    return FileResponse(GRID_GEOJSON_PATH, media_type="application/json")


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=False)
