"""
config.py
---------
Configuration loader for CellRoute Module 2.
Loads API keys and settings from environment variables or .env file.
"""

import os
from pathlib import Path
from typing import Optional

# Try to load from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    
    # Look for .env in current directory and parent directory
    env_path = Path('.env')
    if not env_path.exists():
        env_path = Path('..') / '.env'
    
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded config from {env_path}")
except ImportError:
    print("ℹ️  python-dotenv not installed. Using environment variables only.")


class Config:
    """Configuration settings for Module 2."""
    
    # API Keys
    OPENCELLID_API_KEY: str = os.getenv('OPENCELLID_API_KEY', '')
    OPENWEATHER_API_KEY: str = os.getenv('OPENWEATHER_API_KEY', '')
    
    # Bangalore bounding box
    BBOX_MIN_LAT: float = float(os.getenv('BBOX_MIN_LAT', '12.7342'))
    BBOX_MIN_LNG: float = float(os.getenv('BBOX_MIN_LNG', '77.3791'))
    BBOX_MAX_LAT: float = float(os.getenv('BBOX_MAX_LAT', '13.1734'))
    BBOX_MAX_LNG: float = float(os.getenv('BBOX_MAX_LNG', '77.8811'))
    
    # Data paths
    CSV_PATH: str = os.getenv('CSV_PATH', 'data/cell_towers.csv')
    GEOJSON_PATH: str = os.getenv('GEOJSON_PATH', 'data/connectivity_grid.geojson')
    
    # Server settings
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', '8001'))
    
    # Feature flags
    USE_REAL_DATA: bool = os.getenv('USE_REAL_DATA', 'true').lower() == 'true'
    ENABLE_CACHING: bool = os.getenv('ENABLE_CACHING', 'true').lower() == 'true'
    
    @classmethod
    def is_configured(cls) -> bool:
        """Check if API keys are properly configured."""
        return bool(cls.OPENCELLID_API_KEY and not cls.OPENCELLID_API_KEY.startswith('YOUR_'))
    
    @classmethod
    def print_config(cls):
        """Print current configuration (with masked API keys)."""
        print("=" * 60)
        print("  Module 2 Configuration")
        print("=" * 60)
        
        if cls.OPENCELLID_API_KEY:
            masked = cls.OPENCELLID_API_KEY[:10] + "..." + cls.OPENCELLID_API_KEY[-4:]
            print(f"  OpenCellID API Key: {masked}")
        else:
            print(f"  OpenCellID API Key: ⚠️  NOT SET")
        
        if cls.OPENWEATHER_API_KEY:
            masked = cls.OPENWEATHER_API_KEY[:10] + "..." + cls.OPENWEATHER_API_KEY[-4:]
            print(f"  OpenWeather API Key: {masked}")
        else:
            print(f"  OpenWeather API Key: ⚠️  NOT SET")
        
        print(f"  Use Real Data: {cls.USE_REAL_DATA}")
        print(f"  CSV Path: {cls.CSV_PATH}")
        print(f"  Server: {cls.HOST}:{cls.PORT}")
        print("=" * 60)


# Create a singleton instance
config = Config()
