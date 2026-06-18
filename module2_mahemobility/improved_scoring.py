"""
improved_scoring.py
-------------------
Paste this function into your Module 2's server.py to get better scores.

Replace the old dbm_to_score or signal_to_score function with this.
"""

def dbm_to_score(signal_dbm):
    """
    Convert signal strength (dBm) to connectivity score (0-100).
    
    More generous scoring that reflects real-world usability:
    - Excellent (>= -70 dBm): 90-100%
    - Good (-70 to -80 dBm): 70-90%
    - Fair (-80 to -90 dBm): 50-70%
    - Weak (-90 to -100 dBm): 25-50%
    - Poor (< -100 dBm): 0-25%
    """
    if signal_dbm >= -70:
        # Excellent signal
        return min(100, 90 + (signal_dbm + 70))
    elif signal_dbm >= -80:
        # Good signal: -80 = 70%, -70 = 90%
        return 70 + (signal_dbm + 80) * 2
    elif signal_dbm >= -90:
        # Fair signal: -90 = 50%, -80 = 70%
        return 50 + (signal_dbm + 90) * 2
    elif signal_dbm >= -100:
        # Weak signal: -100 = 25%, -90 = 50%
        return 25 + (signal_dbm + 100) * 2.5
    else:
        # Poor signal: < -100 = 0-25%
        return max(0, 25 + (signal_dbm + 105))

# Test the function
if __name__ == '__main__':
    print("Signal (dBm) → Score (%)")
    print("-" * 30)
    for dbm in [-69, -75, -80, -85, -90, -95, -100]:
        score = dbm_to_score(dbm)
        print(f"{dbm:4d} dBm → {score:5.1f}%")
    
    print("\nYour ML predictions:")
    print("  4G avg (-78.5 dBm) → ", dbm_to_score(-78.5), "%")
    print("  3G avg (-83.8 dBm) → ", dbm_to_score(-83.8), "%")
    print("  2G avg (-89.9 dBm) → ", dbm_to_score(-89.9), "%")
