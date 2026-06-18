# CellRoute

**Network-Aware Navigation for Better Connectivity**

CellRoute is an intelligent routing system that calculates the best routes based on cellular network connectivity, not just distance or time. Built for the urban professional who needs reliable connectivity during their commute.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

---

## Problem Statement

Traditional navigation apps optimize for distance or time, but ignore a critical factor: **cellular connectivity**. Dropped calls, interrupted video conferences, and failed GPS updates plague users who take routes through signal dead zones.

**CellRoute solves this** by incorporating real-time cellular signal data into route planning.

---

## Features

### **Multi-Route Comparison**
- **Shortest Route**: Minimizes distance
- **Fastest Route**: Minimizes travel time
- **Most Connected Route**: Maximizes signal strength

### **Real-Time Visualizations**
- **Signal Timeline**: See connectivity quality along your entire route
- **Trade-off Chart**: Compare time vs connectivity at a glance
- **Drop Zone Markers**: Identify areas with poor coverage

### **Journey Simulator**
- Simulate your drive before you start
- Watch signal strength change in real-time
- Adjust playback speed (1x-10x)

### **Data-Driven**
- **4,000+ cell towers** in Bangalore region
- **OpenCellID** database integration
- **3,907 grid cells** with coverage data

---

## Architecture

```
┌─────────────────────────────────────────┐
│  FRONTEND (cellroute_final.html)       │
│  Port: 8080                             │
│  • Single-page web application         │
│  • Leaflet.js for maps                 │
│  • Chart.js for visualizations         │
└──────────────┬──────────────────────────┘
               │ POST /route
               ↓
┌─────────────────────────────────────────┐
│  MODULE 1: Routing Engine               │
│  Port: 8000                             │
│  • Valhalla integration                 │
│  • Route variant generation (5 types)  │
│  • Orchestrates Module 2 calls         │
└──────────────┬──────────────────────────┘
               │ POST /signal/score_route
               ↓
┌─────────────────────────────────────────┐
│  MODULE 2: Connectivity Layer           │
│  Port: 8001                             │
│  • OpenCellID grid data                 │
│  • Signal strength scoring              │
│  • Drop zone detection                  │
└─────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- **Python 3.8+**
- **pip** (Python package manager)
- **Internet connection** (for Valhalla API and map tiles)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/routing-project.git
cd routing-project
```

2. **Install dependencies for Module 1**
```bash
cd cellroute-routing
pip install fastapi uvicorn httpx polyline
cd ..
```

3. **Install dependencies for Module 2**
```bash
cd module2_mahemobility
pip install fastapi uvicorn numpy pandas
cd ..
```

### Running the Application

**You need 3 terminals running simultaneously:**

#### Terminal 1: Start Module 2 (Connectivity Layer)
```bash
cd module2_mahemobility
python server.py
```
**Output:**
```
Loading connectivity grid …
Connectivity grid ready.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

#### Terminal 2: Start Module 1 (Routing Engine)
```bash
cd cellroute-routing
uvicorn main:app --host 0.0.0.0 --port 8000
```
**Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

#### Terminal 3: Serve Frontend
```bash
python3 -m http.server 8080
```
**Output:**
```
Serving HTTP on 0.0.0.0 port 8080
```

#### Access the Application
Open your browser and navigate to:
```
http://localhost:8080/cellroute_final.html
```

---

## Usage Guide

### Basic Usage

1. **Enter Origin**: Type a location in Bangalore (e.g., "MG Road, Bengaluru")
2. **Enter Destination**: Type destination (e.g., "Electronic City, Bengaluru")
3. **Click "Route"**: Wait 3-5 seconds for route calculation
4. **Explore Routes**: Click tabs to switch between routes
5. **Simulate Journey**: Click "Start" to see signal strength change along the route

### Tips for Best Results

**DO:**
- Always add ", Bengaluru" or ", Bangalore" to location names
- Use specific landmarks (e.g., "Koramangala 5th Block, Bengaluru")
- Wait for all 3 routes to load before switching tabs

**DON'T:**
- Use abbreviations (EC, MG) alone
- Enter locations outside Bangalore area
- Click Route button multiple times rapidly

---

## API Documentation

### Module 1: Routing Engine

**Endpoint:** `POST http://localhost:8000/route`

**Request:**
```json
{
  "origin": {
    "lat": 12.9716,
    "lng": 77.5946
  },
  "destination": {
    "lat": 12.8451,
    "lng": 77.6692
  }
}
```

**Response:**
```json
{
  "routes": [
    {
      "type": "shortest",
      "distance": 14.2,
      "eta": 31,
      "geometry": [
        {"lat": 12.9716, "lng": 77.5946},
        {"lat": 12.9800, "lng": 77.6100}
      ],
      "connectivity_score": 72.5,
      "segments": [...],
      "drop_zones": [...]
    }
  ]
}
```

---

### Module 2: Connectivity Layer

**Endpoint:** `POST http://localhost:8001/signal/score_route`

**Request:**
```json
{
  "points": [
    {"lat": 12.9716, "lng": 77.5946},
    {"lat": 12.9800, "lng": 77.6100}
  ],
  "alpha": 0.4,
  "beta": 0.4,
  "gamma": 0.2
}
```

**Response:**
```json
{
  "connectivity_score": 72.5,
  "avg_signal_dbm": -85.3,
  "fraction_4g5g": 0.65,
  "drop_zones": [
    {
      "start": {"lat": 12.98, "lng": 77.61},
      "end": {"lat": 12.99, "lng": 77.62},
      "is_tunnel": false
    }
  ],
  "segments": [
    {
      "lat": 12.9716,
      "lng": 77.5946,
      "signal": -85,
      "color": "green",
      "network_type": "LTE",
      "confidence": 0.9
    }
  ]
}
```

---

## Testing

### Health Checks

**Module 1:**
```bash
curl http://localhost:8000/health
```
Expected: `{"status": "ok", "module": "routing", "port": 8000}`

**Module 2:**
```bash
curl http://localhost:8001/health
```
Expected: `{"status": "ok", "grid_cells": 3907, ...}`

### Test Route

```bash
curl -X POST http://localhost:8000/route \
  -H "Content-Type: application/json" \
  -d '{
    "origin": {"lat": 12.9716, "lng": 77.5946},
    "destination": {"lat": 12.8451, "lng": 77.6692}
  }'
```

---

## Troubleshooting

### Issue: "Access blocked" on map tiles

**Cause:** OpenStreetMap blocking localhost requests

**Fix:** The frontend now uses CartoDB tiles (already fixed in `cellroute_final.html`)

---

### Issue: "Module 1 error"

**Cause:** Module 2 not running or CORS not configured

**Fix:**
1. Ensure Module 2 is running on port 8001 FIRST
2. Check that Module 1 has CORS middleware:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

### Issue: Shortest and Connected routes are identical

**Cause:** Old routing logic with limited diversity

**Fix:** Use the improved `main_improved.py` with diverse routing parameters

---

### Issue: Routes fail for some locations

**Cause:** Geocoding failure (location not found)

**Solutions:**
- Add ", Bengaluru" to location names
- Use more specific landmarks
- Check browser console (F12) for detailed error messages

---

## Data Sources

- **Routing**: [Valhalla](https://valhalla.openstreetmap.de/) (Open-source routing engine)
- **Cell Tower Data**: [OpenCellID](https://opencellid.org/) (Global cell tower database)
- **Maps**: [CartoDB](https://carto.com/) (Base map tiles)
- **Geocoding**: [Nominatim](https://nominatim.openstreetmap.org/) (OpenStreetMap geocoder)

---

## Technology Stack

### Frontend
- **HTML5/CSS3/JavaScript** (Vanilla JS - no frameworks)
- **Leaflet.js** (Interactive maps)
- **Chart.js** (Data visualizations)

### Backend
- **Python 3.8+**
- **FastAPI** (API framework)
- **Uvicorn** (ASGI server)
- **NumPy/Pandas** (Data processing)
- **httpx** (Async HTTP client)

---

## Project Structure

```
routing-project/
├── cellroute_final.html          # Frontend (single-page app)
├── cellroute-routing/             # Module 1: Routing Engine
│   └── main.py                    # FastAPI routing logic
├── module2_mahemobility/          # Module 2: Connectivity Layer
│   ├── server.py                  # FastAPI server
│   ├── connectivity_grid.py       # Grid computation logic
│   ├── generate_mock_data.py      # Mock data generator
│   └── data/
│       ├── cell_towers.csv        # Tower locations (4,000 towers)
│       └── connectivity_grid.geojson  # Grid cells (3,907 cells)
└── README.md                      # This file
```

---

## Features Roadmap

### Implemented 
- [x] Multi-route comparison (Shortest/Fastest/Connected)
- [x] Real-time signal scoring
- [x] Journey simulator
- [x] Drop zone detection
- [x] Interactive visualizations
- [x] Weather impact display

### Future Enhancements 
- [ ] Multi-carrier support (Airtel, Jio, Vi)
- [ ] Crowdsourced signal data
- [ ] Offline mode
- [ ] Mobile app (React Native)
- [ ] Emergency mode (prioritize connectivity)
- [ ] Route history and favorites

---

## Acknowledgments

- OpenStreetMap contributors for map data
- OpenCellID for cell tower database
- Valhalla routing engine team
- FastAPI community

---

## Screenshots

### Main Interface
![CellRoute Main Interface](docs/screenshots/main-interface.png)

### Route Comparison
![Route Comparison](docs/screenshots/route-comparison.png)

### Journey Simulator
![Journey Simulator](docs/screenshots/journey-simulator.png)

---

**For queries during hackathon evaluation, check the browser console (F12) for detailed logs!**
