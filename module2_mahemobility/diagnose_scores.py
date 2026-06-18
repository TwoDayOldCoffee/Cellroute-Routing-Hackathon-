#!/usr/bin/env python3
"""
diagnose_scores.py
------------------
Diagnose why routes are still scoring low despite improved data.
"""

import pandas as pd
import numpy as np

CSV_PATH = 'data/cell_towers.csv'

print("=" * 60)
print("  CellRoute - Score Diagnostic")
print("=" * 60)

# Load data
df = pd.read_csv(CSV_PATH)

print(f"\n📊 Data Statistics:")
print(f"   Total towers: {len(df)}")
print(f"   Signal range: {df['signal_dbm'].min()} to {df['signal_dbm'].max()} dBm")
print(f"   Signal mean: {df['signal_dbm'].mean():.1f} dBm")
print(f"   Signal median: {df['signal_dbm'].median():.1f} dBm")

# Signal distribution
print(f"\n📊 Signal Distribution:")
bins = [-110, -100, -90, -80, -70, -60]
labels = ['Poor (<-100)', 'Weak (-90 to -100)', 'Moderate (-80 to -90)', 'Good (-70 to -80)', 'Excellent (>-70)']
df['signal_category'] = pd.cut(df['signal_dbm'], bins=bins, labels=labels)
print(df['signal_category'].value_counts().sort_index())

# By network type
print(f"\n📊 By Network Type:")
for net in ['2G', '3G', '4G']:
    subset = df[df['network_type'] == net]
    if len(subset) > 0:
        print(f"   {net}: {subset['signal_dbm'].mean():.1f} dBm avg ({len(subset)} towers)")

# Test scoring algorithms
print(f"\n🧪 Testing Scoring Algorithms:")

def score_method_1(dbm):
    """Linear scaling: -110 = 0%, -60 = 100%"""
    return max(0, min(100, (dbm + 110) * 2))

def score_method_2(dbm):
    """Percentage based on typical ranges"""
    if dbm >= -70:
        return 100
    elif dbm >= -80:
        return 70
    elif dbm >= -90:
        return 40
    elif dbm >= -100:
        return 20
    else:
        return 5

def score_method_3(dbm):
    """More generous scaling"""
    return max(0, min(100, (dbm + 100) * 5))

test_signals = [-69, -78, -85, -90, -95]
print("\n   dBm    Method1  Method2  Method3")
for sig in test_signals:
    s1 = score_method_1(sig)
    s2 = score_method_2(sig)
    s3 = score_method_3(sig)
    print(f"   {sig:3d}     {s1:3.0f}%     {s2:3.0f}%     {s3:3.0f}%")

# Route corridor analysis
print(f"\n🗺️  MG Road → Electronic City Corridor:")
route_towers = df[
    (df['lat'] >= 12.84) & (df['lat'] <= 12.98) &
    (df['lng'] >= 77.58) & (df['lng'] <= 77.68)
]

if len(route_towers) > 0:
    print(f"   Towers in corridor: {len(route_towers)}")
    print(f"   Avg signal: {route_towers['signal_dbm'].mean():.1f} dBm")
    print(f"   Network mix:")
    for net in route_towers['network_type'].value_counts().head(3).items():
        print(f"      {net[0]}: {net[1]} towers")
    
    # What score would this get?
    avg_sig = route_towers['signal_dbm'].mean()
    print(f"\n   Expected scores for {avg_sig:.1f} dBm average:")
    print(f"      Method 1 (linear): {score_method_1(avg_sig):.0f}%")
    print(f"      Method 2 (ranges): {score_method_2(avg_sig):.0f}%")
    print(f"      Method 3 (generous): {score_method_3(avg_sig):.0f}%")

print("\n" + "=" * 60)
print("💡 Recommendations:")
print("=" * 60)

avg_signal = df['signal_dbm'].mean()

if avg_signal < -85:
    print("⚠️  Average signal is still poor (-85 or worse)")
    print("   → Re-run ML predictor with better baselines")
    print("   → Edit SIGNAL_BASELINE in signal_ml_predictor.py")
elif score_method_1(avg_signal) < 40:
    print("⚠️  Scoring algorithm is too harsh")
    print("   → Use Method 3 (more generous)")
    print("   → Or adjust scoring in Module 2")
else:
    print("✅ Data looks good!")
    print("   → Delete data/connectivity_grid.geojson")
    print("   → Restart Module 2 to rebuild grid")

print()
