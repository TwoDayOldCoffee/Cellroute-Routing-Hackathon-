#!/usr/bin/env python3
"""
fetch_real_towers.py - WORKING VERSION
---------------------------------------
Fetches real OpenCellID data with proper field mapping.
"""

import os
import requests
import pandas as pd
import time
from pathlib import Path

# Configuration
API_KEY = "pk.ed0a3f06830403bff07f324eb8a9ceda"
OUTPUT_PATH = "data/cell_towers.csv"

# Bangalore bounds (tighter central area)
LAT_MIN, LAT_MAX = 12.90, 13.05
LNG_MIN, LNG_MAX = 77.50, 77.70
STEP = 0.01  # 1.1km chunks (safe under limit)

def fetch_chunk(lat_min, lng_min, lat_max, lng_max):
    """Fetch towers for a single chunk."""
    bbox = f"{lat_min},{lng_min},{lat_max},{lng_max}"
    url = f"https://opencellid.org/cell/getInArea?token={API_KEY}&BBOX={bbox}&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "cells" in data:
                return data["cells"]
    except:
        pass
    
    return []

def convert_towers(towers):
    """Convert API format to our format."""
    converted = []
    
    for tower in towers:
        # Map radio to network type
        radio = tower.get("radio", "").upper()
        network_map = {
            "GSM": "2G",
            "UMTS": "3G",
            "LTE": "4G",
            "NR": "5G"
        }
        network_type = network_map.get(radio, "UNKNOWN")
        
        # Get signal (API uses averageSignalStrength)
        signal = tower.get("averageSignalStrength", 0)
        if signal == 0:
            signal = -95  # Default
        
        converted.append({
            "lat": tower["lat"],
            "lng": tower["lon"],  # API uses "lon", we need "lng"
            "signal_dbm": int(signal),
            "network_type": network_type,
            "mcc": tower.get("mcc", 404),
            "mnc": tower.get("mnc", 0),
            "cell_id": tower.get("cellid", 0),  # API uses "cellid" not "cid"
            "range": tower.get("range", 1000),
            "samples": tower.get("samples", 1)
        })
    
    return converted

def main():
    """Fetch all towers for Bangalore."""
    print("=" * 60)
    print("  CellRoute - Real Tower Fetcher (WORKING VERSION)")
    print("=" * 60)
    
    # Calculate grid
    lat_steps = []
    lat = LAT_MIN
    while lat < LAT_MAX:
        lat_steps.append(lat)
        lat += STEP
    
    lng_steps = []
    lng = LNG_MIN
    while lng < LNG_MAX:
        lng_steps.append(lng)
        lng += STEP
    
    total_chunks = len(lat_steps) * len(lng_steps)
    
    print(f"\n📐 Area: {LAT_MAX-LAT_MIN:.2f}° × {LNG_MAX-LNG_MIN:.2f}° (Central Bangalore)")
    print(f"📦 Chunks: {total_chunks} ({len(lat_steps)}×{len(lng_steps)} grid)")
    print(f"🔲 Size: ~1.1km × 1.1km per chunk")
    print(f"⏱️  Time: ~{total_chunks * 0.5 / 60:.0f} minutes\n")
    
    all_towers = []
    seen_cells = set()
    chunk_num = 0
    
    print("🚀 Starting download...\n")
    start_time = time.time()
    
    for lat in lat_steps:
        for lng in lng_steps:
            chunk_num += 1
            
            # Fetch chunk
            raw_towers = fetch_chunk(lat, lng, lat + STEP, lng + STEP)
            
            if raw_towers:
                # Convert format
                converted = convert_towers(raw_towers)
                
                # Deduplicate
                new_count = 0
                for tower in converted:
                    cell_key = (tower["mcc"], tower["mnc"], tower["cell_id"])
                    if cell_key not in seen_cells:
                        seen_cells.add(cell_key)
                        all_towers.append(tower)
                        new_count += 1
                
                if new_count > 0:
                    print(f"   📡 Chunk {chunk_num}/{total_chunks}: +{new_count} towers (total: {len(all_towers)})")
            
            # Progress summary every 50 chunks
            if chunk_num % 50 == 0:
                elapsed = time.time() - start_time
                rate = chunk_num / elapsed
                remaining = (total_chunks - chunk_num) / rate
                print(f"\n   📊 Progress: {chunk_num}/{total_chunks} ({chunk_num/total_chunks*100:.0f}%)")
                print(f"   ⏱️  Time: {elapsed/60:.1f}m elapsed, ~{remaining/60:.1f}m left")
                print(f"   📈 Towers: {len(all_towers)} unique\n")
            
            # Rate limiting
            time.sleep(0.5)
    
    # Save results
    if all_towers:
        Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(all_towers)
        df.to_csv(OUTPUT_PATH, index=False)
        
        # Statistics
        network_counts = df['network_type'].value_counts()
        
        print(f"\n{'='*60}")
        print(f"✅ SUCCESS! Downloaded {len(all_towers)} unique towers")
        print(f"{'='*60}")
        print(f"\n📊 Network Distribution:")
        for net, count in network_counts.items():
            pct = count / len(all_towers) * 100
            print(f"   {net}: {count:,} ({pct:.1f}%)")
        
        print(f"\n💾 Saved to: {OUTPUT_PATH}")
        print(f"\n🚀 Next step: Restart Module 2")
        print(f"   python server.py\n")
    else:
        print("\n❌ No towers fetched!")

if __name__ == "__main__":
    main()
