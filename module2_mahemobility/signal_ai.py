"""
signal_ai.py
------------
Thin adapter that wraps SignalPredictor (7-feature XGBoost/RF model)
so it can be injected into ConnectivityGrid as `_grid.ml_model`.

The original version only used [lat, lng] → identical scores for all routes.
This version uses the full feature set:
  1. dist_1, dist_2, dist_3  — distance to 3 nearest towers (km)
  2. tower_density            — tower count within 1 km radius
  3. network_encoded          — 2G=1, 3G=2, 4G=3, 5G=4
  4. avg_nearby_signal        — mean signal of 3 nearest towers (dBm)
  5. pct_4g                   — fraction of 4G towers nearby

Usage (in server.py lifespan):
    ai = SignalAI()
    ai.train_on_existing_data(CSV_PATH)
    _grid.ml_model = ai
"""

import numpy as np
import pandas as pd
from scipy.spatial import KDTree

try:
    import xgboost as xgb
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

# ── Constants ──────────────────────────────────────────────────────────────

NETWORK_ENCODING = {"5G": 4, "NR": 4, "LTE": 3, "4G": 3, "UMTS": 2, "3G": 2, "GSM": 1, "2G": 1}
SIGNAL_BASELINE  = {"5G": -72, "NR": -72, "4G": -78, "LTE": -78, "3G": -85, "UMTS": -85, "2G": -90, "GSM": -90}
_KM_PER_DEG      = 111.32   # approximate
_1KM_DEG         = 1.0 / _KM_PER_DEG   # ~0.009 degrees


# ── Main class ─────────────────────────────────────────────────────────────

class SignalAI:
    """
    7-feature ML signal predictor.  Drop-in replacement for the old
    2-feature version.  ConnectivityGrid calls predict(lat, lng).
    """

    def __init__(self):
        self.model       = None
        self.tower_tree  = None
        self.towers_df   = None
        self.is_trained  = False

    # ── Public API expected by ConnectivityGrid ────────────────────────────

    def train_on_existing_data(self, csv_path: str):
        """Load towers, build KD-tree, generate samples, train model."""
        self._load_towers(csv_path)
        X, y = self._generate_training_data(n_samples=5000)
        self._train(X, y)

    def predict(self, lat: float, lng: float) -> float:
        """Return predicted signal_dbm for (lat, lng).  Conservative fallback if untrained."""
        if not self.is_trained:
            return -105.0
        features = self._extract_features(lat, lng)
        return float(self.model.predict([features])[0])

    # ── Internal helpers ───────────────────────────────────────────────────

    def _load_towers(self, csv_path: str):
        print(f"📂  SignalAI: loading towers from {csv_path} …")
        df = pd.read_csv(csv_path)

        # Normalise column names
        df.rename(columns={"lon": "lng"}, inplace=True, errors="ignore")

        # Network type column
        if "radio" in df.columns and "network_type" not in df.columns:
            radio_map = {"NR": "NR", "LTE": "LTE", "UMTS": "UMTS", "GSM": "GSM", "CDMA": "GSM"}
            df["network_type"] = df["radio"].map(radio_map).fillna("GSM")
        if "network_type" not in df.columns:
            df["network_type"] = "GSM"

        # Signal column
        for col in ("averageSignal", "signal_dbm", "signal"):
            if col in df.columns:
                df["signal_dbm"] = pd.to_numeric(df[col], errors="coerce").fillna(-100)
                break
        else:
            df["signal_dbm"] = -100.0

        # Drop rows missing lat/lng
        df = df.dropna(subset=["lat", "lng"])

        self.towers_df  = df.reset_index(drop=True)
        coords          = df[["lat", "lng"]].values
        self.tower_tree = KDTree(coords)
        print(f"✅  SignalAI: {len(df)} towers loaded, KD-tree built.")

    def _extract_features(self, lat: float, lng: float, network_type: str = "4G") -> list:
        """Build 7-element feature vector for a coordinate."""
        point = [lat, lng]
        k     = min(3, len(self.towers_df))

        # Distances to nearest k towers (converted to km)
        dists, idxs = self.tower_tree.query(point, k=k)
        if k < 3:
            dists = list(dists) + [0.5] * (3 - k)   # pad
            idxs  = list(idxs)  + [idxs[-1]] * (3 - k)
        dists_km = [d * _KM_PER_DEG for d in dists[:3]]

        # Tower density within 1 km radius
        nearby = self.tower_tree.query_ball_point(point, _1KM_DEG)
        density = len(nearby)

        # Network type of calling context (dominant nearby network)
        if nearby:
            nets = self.towers_df.iloc[nearby]["network_type"].value_counts()
            dom_net = nets.index[0] if len(nets) else network_type
        else:
            dom_net = network_type
        net_encoded = NETWORK_ENCODING.get(str(dom_net).upper(), 1)

        # Average signal of 3 nearest towers
        near_towers = self.towers_df.iloc[list(idxs[:3])]
        avg_signal  = float(near_towers["signal_dbm"].mean())

        # Fraction of 4G/5G towers within 1 km
        if nearby:
            near_df = self.towers_df.iloc[nearby]
            hi_net  = near_df["network_type"].isin(["LTE", "NR", "4G", "5G"]).sum()
            pct_4g  = hi_net / len(nearby)
        else:
            pct_4g = 0.0

        return [*dists_km, density, net_encoded, avg_signal, pct_4g]

    def _generate_training_data(self, n_samples: int = 5000):
        """Sample from actual tower positions with small perturbations."""
        print(f"🔄  SignalAI: generating {n_samples} training samples …")
        n_sample = min(n_samples, len(self.towers_df))
        sample   = self.towers_df.sample(n=n_sample, random_state=42)

        X, y = [], []
        for _, row in sample.iterrows():
            # Small random offset (~220 m std)
            lat = float(row["lat"]) + np.random.normal(0, 0.002)
            lng = float(row["lng"]) + np.random.normal(0, 0.002)

            features = self._extract_features(lat, lng, str(row.get("network_type", "GSM")))

            # Realistic target: baseline + distance decay + noise
            net_str    = str(row.get("network_type", "GSM")).upper()
            base_sig   = SIGNAL_BASELINE.get(net_str, -90)
            dist_pen   = -min(features[0] * 5, 20)   # up to -20 dBm for distance
            noise      = np.random.normal(0, 4)
            target_dbm = float(np.clip(base_sig + dist_pen + noise, -115, -55))

            X.append(features)
            y.append(target_dbm)

        return np.array(X), np.array(y)

    def _train(self, X: np.ndarray, y: np.ndarray):
        X_tr, X_val, y_tr, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

        if _HAS_XGB:
            self.model = xgb.XGBRegressor(
                n_estimators=150, max_depth=6, learning_rate=0.08,
                subsample=0.8, colsample_bytree=0.8, random_state=42,
                verbosity=0
            )
            algo = "XGBoost"
        else:
            self.model = RandomForestRegressor(
                n_estimators=120, max_depth=12, random_state=42, n_jobs=-1
            )
            algo = "RandomForest"

        self.model.fit(X_tr, y_tr)
        y_pred = self.model.predict(X_val)
        mae    = mean_absolute_error(y_val, y_pred)
        r2     = r2_score(y_val, y_pred)

        print(f"🧠  SignalAI trained ({algo}) — MAE: {mae:.2f} dBm, R²: {r2:.3f}")
        self.is_trained = True
