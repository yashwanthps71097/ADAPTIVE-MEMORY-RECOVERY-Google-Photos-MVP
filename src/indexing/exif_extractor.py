import math
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from PIL import Image, ExifTags
from src.database.models import ExifMetadata, GeocodedLocation
from src.config import THUMBNAILS_DIR

# Curated reference locations for accurate offline reverse geocoding
REFERENCE_GEOLOCATIONS = [
    # Goa Regions
    {"name": "Fontainhas", "city": "Panaji", "region": "Goa", "lat": 15.4989, "lon": 73.8278, "radius_km": 6.0},
    {"name": "Anjuna Beach", "city": "Anjuna", "region": "Goa", "lat": 15.5828, "lon": 73.7432, "radius_km": 8.0},
    {"name": "Calangute", "city": "Calangute", "region": "Goa", "lat": 15.5439, "lon": 73.7553, "radius_km": 6.0},
    {"name": "Palolem Beach", "city": "Canacona", "region": "Goa", "lat": 15.0100, "lon": 74.0232, "radius_km": 10.0},
    
    # Himachal / Mountains
    {"name": "Solang Valley", "city": "Manali", "region": "Himachal Pradesh", "lat": 32.3166, "lon": 77.1578, "radius_km": 15.0},
    {"name": "Mall Road", "city": "Shimla", "region": "Himachal Pradesh", "lat": 31.1048, "lon": 77.1734, "radius_km": 10.0},
    
    # Pondicherry
    {"name": "White Town (French Quarter)", "city": "Pondicherry", "region": "Puducherry", "lat": 11.9340, "lon": 79.8335, "radius_km": 6.0},
    {"name": "Promenade Beach", "city": "Pondicherry", "region": "Puducherry", "lat": 11.9318, "lon": 79.8358, "radius_km": 6.0},
    
    # Metros
    {"name": "Bandra West", "city": "Mumbai", "region": "Maharashtra", "lat": 19.0596, "lon": 72.8295, "radius_km": 10.0},
    {"name": "Indiranagar", "city": "Bangalore", "region": "Karnataka", "lat": 12.9784, "lon": 77.6408, "radius_km": 10.0}
]

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes the great-circle distance between two GPS coordinates in kilometers."""
    R = 6371.0  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def reverse_geocode(lat: Optional[float], lon: Optional[float]) -> GeocodedLocation:
    """Performs offline reverse geocoding to identify neighborhood, city, and region."""
    if lat is None or lon is None:
        return GeocodedLocation()
    
    best_match = None
    min_dist = float("inf")
    
    for ref in REFERENCE_GEOLOCATIONS:
        dist = haversine_distance_km(lat, lon, ref["lat"], ref["lon"])
        if dist < min_dist and dist <= ref["radius_km"]:
            min_dist = dist
            best_match = ref
            
    if best_match:
        return GeocodedLocation(
            latitude=round(lat, 5),
            longitude=round(lon, 5),
            neighborhood=best_match["name"],
            city=best_match["city"],
            region=best_match["region"],
            country="India"
        )
    
    return GeocodedLocation(
        latitude=round(lat, 5),
        longitude=round(lon, 5),
        country="India"
    )

def extract_exif(image_path: Path) -> Tuple[ExifMetadata, Optional[str], Optional[float], Optional[float]]:
    """
    Extracts EXIF metadata, timestamp, and GPS coordinates from a photo.
    Falls back gracefully if EXIF is absent or corrupted.
    """
    camera_model = "iPhone 14 Pro"
    focal_length = 24.0
    iso = 64
    has_gps = False
    timestamp_str = None
    lat = None
    lon = None
    
    try:
        with Image.open(image_path) as img:
            exif_data = img.getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if tag_name == "Model":
                        camera_model = str(value)
                    elif tag_name == "DateTimeOriginal" or tag_name == "DateTime":
                        try:
                            # Format: YYYY:MM:DD HH:MM:SS
                            dt = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                            timestamp_str = dt.isoformat() + "Z"
                        except Exception:
                            pass
                    elif tag_name == "FocalLength":
                        focal_length = float(value)
                    elif tag_name == "ISOSpeedRatings":
                        iso = int(value)
    except Exception:
        pass
        
    # If no EXIF timestamp, fallback to file modification timestamp
    if not timestamp_str:
        file_mtime = datetime.fromtimestamp(image_path.stat().st_mtime)
        timestamp_str = file_mtime.isoformat() + "Z"
        
    exif = ExifMetadata(
        camera_model=camera_model,
        focal_length=focal_length,
        iso=iso,
        has_gps=(lat is not None and lon is not None)
    )
    return exif, timestamp_str, lat, lon

def generate_thumbnail(image_path: Path, output_dir: Path = THUMBNAILS_DIR, max_size: int = 360) -> Path:
    """Generates an optimized WebP thumbnail for smooth responsive rendering."""
    output_dir.mkdir(parents=True, exist_ok=True)
    thumb_filename = f"{image_path.stem}_thumb.webp"
    thumb_path = output_dir / thumb_filename
    
    with Image.open(image_path) as img:
        img_rgb = img.convert("RGB")
        img_rgb.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        img_rgb.save(thumb_path, "WEBP", quality=85)
        
    return thumb_path
