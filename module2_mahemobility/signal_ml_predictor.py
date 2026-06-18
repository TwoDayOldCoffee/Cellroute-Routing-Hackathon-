#!/usr/bin/env python3
"""
signal_ml_predictor.py
----------------------
ML-based signal strength prediction using XGBoost/Random Forest.

Features:
- Distance to nearest 3 towers
- Tower density (within 1km)
- Network type (2G/3G/4G)
- Geographic clustering

Fills gaps in OpenCellID data with AI-inferred signal strength.
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import pickle
import json

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("⚠️  XGBoost not installed, using Random Forest instead")
    from sklearn.ensemble import RandomForestRegressor

from sklearn.ensemble import RandomForestRegressor
from scipy.spatial import KDTree

INPUT_CSV = 'data/cell_towers.csv'
MODEL_FILE = 'data/signal_predictor_model.pkl'
SCALER_FILE = 'data/signal_scaler.pkl'

# Network type encoding
NETWORK_ENCODING = {
    '2G': 1,
    '3G': 2,
    '4G': 3,
    '5G': 4,
    'UNKNOWN': 0
}

# Realistic signal ranges by network type
SIGNAL_BASELINE = {
    '5G': -75,
    '4G': -80,
    '3G': -85,
    '2G': -90,
    'UNKNOWN': -95
}

class SignalPredictor:
    """ML-based signal strength predictor."""
    
    def __init__(self):
        self.model = None
        self.tower_tree = None
        self.towers_df = None
        
    def load_towers(self, csv_path):
        """Load tower data and build spatial index."""
        print(f"📂 Loading towers from {csv_path}...")
        self.towers_df = pd.read_csv(csv_path)
        
        # Build KD-tree for fast nearest neighbor search
        coords = self.towers_df[['lat', 'lng']].values
        self.tower_tree = KDTree(coords)
        
        print(f"✅ Loaded {len(self.towers_df)} towers")
        return self
    
    def extract_features(self, lat, lng, network_type='4G'):
        """
        Extract features for a given location.
        
        Features:
        1. Distance to nearest 3 towers
        2. Tower density (count within 1km)
        3. Network type (encoded)
        4. Average signal of nearby towers
        """
        # Query point
        point = np.array([[lat, lng]])
        
        # Feature 1-3: Distance to nearest 3 towers (in km)
        distances, indices = self.tower_tree.query(point, k=3)
        dist_1, dist_2, dist_3 = (distances[0] * 111)  # Convert degrees to km
        
        # Feature 4: Tower density (count within 1km = ~0.009 degrees)
        nearby_indices = self.tower_tree.query_ball_point(point[0], 0.009)
        tower_density = len(nearby_indices)
        
        # Feature 5: Network type encoding
        network_encoded = NETWORK_ENCODING.get(network_type, 0)
        
        # Feature 6-8: Average signal of nearest 3 towers (if available)
        nearby_towers = self.towers_df.iloc[indices[0]]
        avg_nearby_signal = nearby_towers['signal_dbm'].mean()
        
        # Feature 9: Network type distribution in area
        if nearby_indices:
            nearby_network = self.towers_df.iloc[nearby_indices]['network_type'].value_counts()
            pct_4g = nearby_network.get('4G', 0) / len(nearby_indices)
        else:
            pct_4g = 0
        
        features = [
            dist_1, dist_2, dist_3,        # Distance to 3 nearest towers
            tower_density,                  # Tower count nearby
            network_encoded,                # Network type
            avg_nearby_signal,              # Avg signal nearby
            pct_4g                          # % of 4G towers nearby
        ]
        
        return features
    
    def generate_training_data(self, n_samples=5000):
        """
        Generate synthetic training data from existing towers.
        
        Strategy: Use actual tower locations as training points,
        with slight perturbations to create more samples.
        """
        print(f"🔄 Generating {n_samples} training samples...")
        
        X_train = []
        y_train = []
        
        # Sample from existing towers
        sample_towers = self.towers_df.sample(min(n_samples, len(self.towers_df)))
        
        for _, tower in sample_towers.iterrows():
            # Add small random offset to create variations
            lat_offset = np.random.normal(0, 0.002)  # ~220m std
            lng_offset = np.random.normal(0, 0.002)
            
            lat = tower['lat'] + lat_offset
            lng = tower['lng'] + lng_offset
            
            # Extract features
            features = self.extract_features(lat, lng, tower['network_type'])
            
            # Target: Realistic signal based on network type and distance
            base_signal = SIGNAL_BASELINE[tower['network_type']]
            
            # Decay with distance to nearest tower
            distance_penalty = -min(features[0] * 5, 20)  # -5 dBm per km
            
            # Random variation
            noise = np.random.normal(0, 5)
            
            predicted_signal = base_signal + distance_penalty + noise
            predicted_signal = max(-110, min(-60, predicted_signal))  # Clamp
            
            X_train.append(features)
            y_train.append(predicted_signal)
        
        return np.array(X_train), np.array(y_train)
    
    def train(self, X_train, y_train):
        """Train the signal prediction model."""
        print("🤖 Training model...")
        
        # Split data
        X_tr, X_val, y_tr, y_val = train_test_split(
            X_train, y_train, test_size=0.2, random_state=42
        )
        
        if HAS_XGB:
            # XGBoost model
            self.model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42
            )
            print("   Using XGBoost")
        else:
            # Random Forest fallback
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
            print("   Using Random Forest")
        
        # Train
        self.model.fit(X_tr, y_tr)
        
        # Evaluate
        y_pred = self.model.predict(X_val)
        mae = mean_absolute_error(y_val, y_pred)
        r2 = r2_score(y_val, y_pred)
        
        print(f"✅ Model trained!")
        print(f"   MAE: {mae:.2f} dBm")
        print(f"   R²: {r2:.3f}")
        
        # Feature importance
        if hasattr(self.model, 'feature_importances_'):
            importance = self.model.feature_importances_
            features = ['dist_1', 'dist_2', 'dist_3', 'density', 
                       'network_type', 'avg_signal', 'pct_4g']
            
            print("\n📊 Feature Importance:")
            for feat, imp in sorted(zip(features, importance), 
                                   key=lambda x: x[1], reverse=True):
                print(f"   {feat}: {imp:.3f}")
        
        return self
    
    def predict(self, lat, lng, network_type='4G'):
        """Predict signal strength at a location."""
        features = self.extract_features(lat, lng, network_type)
        features = np.array(features).reshape(1, -1)
        signal = self.model.predict(features)[0]
        return int(signal)
    
    def save(self, model_path=MODEL_FILE):
        """Save trained model."""
        with open(model_path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'network_encoding': NETWORK_ENCODING,
                'signal_baseline': SIGNAL_BASELINE
            }, f)
        print(f"💾 Model saved to {model_path}")
    
    @classmethod
    def load(cls, model_path=MODEL_FILE, csv_path=INPUT_CSV):
        """Load trained model."""
        predictor = cls()
        predictor.load_towers(csv_path)
        
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
            predictor.model = data['model']
        
        print(f"✅ Model loaded from {model_path}")
        return predictor


def improve_tower_data():
    """Use ML model to improve signal estimates in tower data."""
    print("=" * 60)
    print("  ML-Based Signal Strength Predictor")
    print("=" * 60)
    
    # Initialize predictor
    predictor = SignalPredictor()
    predictor.load_towers(INPUT_CSV)
    
    # Generate training data
    X_train, y_train = predictor.generate_training_data(n_samples=5000)
    
    # Train model
    predictor.train(X_train, y_train)
    
    # Save model
    predictor.save()
    
    # Improve tower data
    print("\n🔄 Improving tower signal estimates...")
    towers_improved = []
    
    for idx, tower in predictor.towers_df.iterrows():
        # Predict signal for this tower location
        predicted_signal = predictor.predict(
            tower['lat'], 
            tower['lng'], 
            tower['network_type']
        )
        
        tower_dict = tower.to_dict()
        tower_dict['signal_dbm'] = predicted_signal
        towers_improved.append(tower_dict)
        
        if (idx + 1) % 1000 == 0:
            print(f"   Processed {idx + 1}/{len(predictor.towers_df)} towers...")
    
    # Save improved data
    df_improved = pd.DataFrame(towers_improved)
    output_path = 'data/cell_towers_ml.csv'
    df_improved.to_csv(output_path, index=False)
    
    print(f"\n✅ Improved tower data saved to {output_path}")
    
    # Show statistics
    print("\n📊 Signal Distribution (ML-predicted):")
    bins = [-110, -100, -90, -80, -70, -60]
    labels = ['-110 to -100', '-100 to -90', '-90 to -80', '-80 to -70', '-70 to -60']
    df_improved['signal_range'] = pd.cut(df_improved['signal_dbm'], bins=bins, labels=labels)
    print(df_improved['signal_range'].value_counts().sort_index())
    
    print("\n📊 By Network Type:")
    for net_type in ['2G', '3G', '4G']:
        if net_type in df_improved['network_type'].values:
            avg_signal = df_improved[df_improved['network_type'] == net_type]['signal_dbm'].mean()
            print(f"   {net_type}: {avg_signal:.1f} dBm average")
    
    print("\n🚀 Next Steps:")
    print("   1. Backup original: mv data/cell_towers.csv data/cell_towers_original.csv")
    print("   2. Use ML version: mv data/cell_towers_ml.csv data/cell_towers.csv")
    print("   3. Restart Module 2: python server.py")
    print("\n   Your routes will now use AI-predicted signal strength! 🤖")


if __name__ == '__main__':
    improve_tower_data()
