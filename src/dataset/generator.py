import os
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
from PIL import Image, ImageDraw, ImageFont
from src.config import RAW_PHOTOS_DIR
from src.indexing.exif_extractor import REFERENCE_GEOLOCATIONS

# 5 Ground Truth Benchmark Targets defined in problemStatement.md & implementationPlan.md
BENCHMARK_TARGETS = [
    {
        "target_id": "target_1_goa_cafe",
        "scenario_name": "Target #1: Goa trip café with friend",
        "description": "Small cozy café in Fontainhas Latin Quarter during Goa trip with friend Alex, warm indoor lighting, coffee on wooden table",
        "filename": "IMG_GOA_CAFE_4021.jpg",
        "timestamp": "2023-11-14T11:42:10Z",
        "lat": 15.4989,
        "lon": 73.8278,
        "city": "Panaji",
        "region": "Goa",
        "neighborhood": "Fontainhas",
        "faces": ["face_cluster_1"],
        "scene_type": "cafe",
        "visual_tags": ["café", "coffee cup", "wood table", "indoor", "warm lighting", "friend", "pastry"],
        "color_theme": ((75, 45, 25), (210, 160, 110)),
        "caption": "Enjoying morning espresso and warm conversation at a small cozy Portuguese café in Fontainhas with Alex."
    },
    {
        "target_id": "target_2_rainy_market",
        "scenario_name": "Target #2: Outdoor street food market during a rainy trip",
        "description": "Rainy monsoon evening at an outdoor street food market in Mumbai, steaming hot chai and umbrellas",
        "filename": "IMG_MUMBAI_RAIN_2104.jpg",
        "timestamp": "2022-07-22T18:15:30Z",
        "lat": 19.0596,
        "lon": 72.8295,
        "city": "Mumbai",
        "region": "Maharashtra",
        "neighborhood": "Bandra West",
        "faces": [],
        "scene_type": "street_food",
        "visual_tags": ["street food", "rain", "umbrella", "monsoon", "tea", "chai", "steaming food", "evening market"],
        "color_theme": ((30, 45, 60), (90, 130, 160)),
        "caption": "Hot cutting chai and monsoon rain dripping from colorful market tarps in Bandra."
    },
    {
        "target_id": "target_3_birthday_celebration",
        "scenario_name": "Target #3: Group birthday celebration in a restaurant with warm candle lighting",
        "description": "Dinner celebration with glowing candles on chocolate cake and friends smiling around restaurant table",
        "filename": "IMG_BDAY_PARTY_8812.jpg",
        "timestamp": "2022-12-18T20:45:00Z",
        "lat": 12.9784,
        "lon": 77.6408,
        "city": "Bangalore",
        "region": "Karnataka",
        "neighborhood": "Indiranagar",
        "faces": ["face_cluster_2", "face_cluster_1"],
        "scene_type": "celebration",
        "visual_tags": ["birthday", "cake", "candle lighting", "restaurant", "celebration", "friends", "evening dinner"],
        "color_theme": ((80, 20, 30), (220, 140, 80)),
        "caption": "Surprise birthday dinner with close friends, blowing out warm candles over decadent chocolate cake."
    },
    {
        "target_id": "target_4_mountain_sunrise",
        "scenario_name": "Target #4: Mountain sunrise hike photo from 3 years ago",
        "description": "Scenic alpine sunrise over mist-covered pine valleys during mountain hike with companion Rohan",
        "filename": "IMG_MANALI_HIKE_1045.jpg",
        "timestamp": "2021-10-08T06:12:45Z",
        "lat": 32.3166,
        "lon": 77.1578,
        "city": "Manali",
        "region": "Himachal Pradesh",
        "neighborhood": "Solang Valley",
        "faces": ["face_cluster_3"],
        "scene_type": "mountain_hiking",
        "visual_tags": ["mountain", "sunrise", "hiking", "trek", "solang valley", "morning mist", "pine trees", "peaks"],
        "color_theme": ((20, 35, 70), (230, 150, 70)),
        "caption": "Golden morning sunrise hitting the snow-dusted Himalayan peaks during our Solang valley ridge hike."
    },
    {
        "target_id": "target_5_dog_beach",
        "scenario_name": "Target #5: Pet photo at a dog-friendly beach resort",
        "description": "Playful golden retriever running along the shoreline at sunny tropical beach resort in South Goa",
        "filename": "IMG_PALOLEM_DOG_5541.jpg",
        "timestamp": "2023-03-25T09:30:15Z",
        "lat": 15.0100,
        "lon": 74.0232,
        "city": "Canacona",
        "region": "Goa",
        "neighborhood": "Palolem Beach",
        "faces": [],
        "scene_type": "pet_beach",
        "visual_tags": ["dog", "pet", "golden retriever", "beach resort", "sand", "ocean waves", "sunny morning", "palolem"],
        "color_theme": ((20, 90, 120), (235, 205, 130)),
        "caption": "Our happy golden retriever splashing into the gentle waves of sunny Palolem Beach resort."
    }
]

# Additional episodic templates to generate realistic ~240 photo library
SCENE_TEMPLATES = [
    # Goa Trip Album (Nov 2023)
    {
        "region": "Goa", "city": "Anjuna", "neighborhood": "Anjuna Beach",
        "lat": 15.5828, "lon": 73.7432, "base_time": datetime(2023, 11, 12, 10, 0),
        "scene_type": "beach",
        "visual_tags": ["beach", "sea", "sand", "waves", "sunny", "coconut trees", "anjuna"],
        "captions": ["Relaxing on the sunbeds at Anjuna beach listening to the waves.", "Strolling along the rocky coastline of Anjuna."],
        "color_theme": ((30, 110, 140), (230, 210, 150)), "count": 25
    },
    {
        "region": "Goa", "city": "Anjuna", "neighborhood": "Anjuna Beach",
        "lat": 15.5825, "lon": 73.7430, "base_time": datetime(2023, 11, 13, 17, 30),
        "scene_type": "beach_cafe",
        "visual_tags": ["beach café", "shack", "sunset", "cocktail", "outdoor seating", "ocean view"],
        "captions": ["Sunset drinks at a vibrant wooden beach shack overlooking Anjuna waters.", "Evening sea breeze with cold beverages at the beach café."],
        "color_theme": ((120, 50, 60), (235, 160, 80)), "count": 20
    },
    {
        "region": "Goa", "city": "Panaji", "neighborhood": "Fontainhas",
        "lat": 15.4985, "lon": 73.8275, "base_time": datetime(2023, 11, 14, 14, 0),
        "scene_type": "heritage_town",
        "visual_tags": ["portuguese house", "yellow walls", "heritage", "latin quarter", "fontainhas", "architecture"],
        "captions": ["Wandering through the vibrant Portuguese colonial alleys of Fontainhas.", "Bright yellow and blue tiled heritage balconies."],
        "color_theme": ((190, 140, 30), (220, 70, 40)), "count": 25
    },
    # Pondicherry French Quarter Trip (Feb 2023)
    {
        "region": "Puducherry", "city": "Pondicherry", "neighborhood": "White Town (French Quarter)",
        "lat": 11.9340, "lon": 79.8335, "base_time": datetime(2023, 2, 18, 12, 0),
        "scene_type": "cafe",
        "visual_tags": ["french café", "croissant", "coffee", "white town", "courtyard", "bougainvillea"],
        "captions": ["Sunny brunch in a heritage French courtyard café with fresh pastries.", "Iced latte under bright pink bougainvillea vines."],
        "color_theme": ((160, 60, 110), (240, 220, 180)), "count": 30
    },
    {
        "region": "Puducherry", "city": "Pondicherry", "neighborhood": "Promenade Beach",
        "lat": 11.9318, "lon": 79.8358, "base_time": datetime(2023, 2, 19, 18, 0),
        "scene_type": "promenade",
        "visual_tags": ["promenade", "sea breeze", "evening walk", "rocky shore", "lighthouse"],
        "captions": ["Breezy evening stroll along the Promenade sea wall.", "Waves crashing against black rocks as street lights turn on."],
        "color_theme": ((40, 60, 90), (140, 170, 200)), "count": 20
    },
    # Manali Mountains Trip (Oct 2021)
    {
        "region": "Himachal Pradesh", "city": "Manali", "neighborhood": "Solang Valley",
        "lat": 32.3166, "lon": 77.1578, "base_time": datetime(2021, 10, 7, 11, 0),
        "scene_type": "mountain_scenery",
        "visual_tags": ["mountain valley", "river", "pine forest", "clouds", "autumn trees", "nature"],
        "captions": ["Crisp mountain air beside the roaring Beas river.", "Panoramic autumn foliage across the valley ridge."],
        "color_theme": ((40, 75, 45), (190, 160, 90)), "count": 35
    },
    # Mumbai Urban & Food Moments (July 2022)
    {
        "region": "Maharashtra", "city": "Mumbai", "neighborhood": "Bandra West",
        "lat": 19.0596, "lon": 72.8295, "base_time": datetime(2022, 7, 23, 19, 0),
        "scene_type": "restaurant",
        "visual_tags": ["restaurant", "dinner", "friends", "indoor dining", "tasty food", "mumbai"],
        "captions": ["Late night seafood dinner with friends at a bustling Bandra diner.", "Sharing steaming plates of coastal curries."],
        "color_theme": ((90, 40, 30), (200, 120, 70)), "count": 30
    },
    # Bangalore Casual & Celebrations (2022-2023)
    {
        "region": "Karnataka", "city": "Bangalore", "neighborhood": "Indiranagar",
        "lat": 12.9784, "lon": 77.6408, "base_time": datetime(2023, 5, 14, 16, 0),
        "scene_type": "urban_cafe",
        "visual_tags": ["specialty coffee", "brewery", "urban cafe", "indoor plants", "weekend hangout"],
        "captions": ["Pour-over coffee on a lazy Sunday afternoon with friends.", "Green open garden seating at an artisanal roastery."],
        "color_theme": ((45, 65, 50), (180, 150, 110)), "count": 45
    }
]

def render_synthetic_image(
    output_path: Path,
    title: str,
    subtitle: str,
    color_top: tuple,
    color_bottom: tuple,
    badge_text: str = ""
) -> None:
    """Renders authentic photography for the photo using the curated realistic asset cache."""
    cache_dir = Path("data/real_photo_cache")
    if cache_dir.exists():
        # Match category based on output_path filename or title
        fn = output_path.name
        matched_candidates = []
        if "GOA_CAFE" in fn or "cafe" in title.lower() or "beverage" in title.lower():
            matched_candidates = list(cache_dir.glob("goa_beach_cafe_*.jpg"))
        elif "GOA" in fn or "beach" in title.lower():
            matched_candidates = list(cache_dir.glob("goa_beach_*.jpg"))
        elif "PUD" in fn or "pondicherry" in title.lower() or "french" in title.lower():
            matched_candidates = list(cache_dir.glob("puducherry_*.jpg"))
        elif "HIM" in fn or "manali" in title.lower() or "mountain" in title.lower():
            matched_candidates = list(cache_dir.glob("manali_*.jpg"))
        elif "MAH" in fn or "mumbai" in title.lower() or "rain" in title.lower():
            matched_candidates = list(cache_dir.glob("mumbai_*.jpg"))
        elif "KAR" in fn or "bangalore" in title.lower() or "bday" in title.lower():
            matched_candidates = list(cache_dir.glob("bangalore_*.jpg"))
        elif "DOG" in fn or "pet" in title.lower():
            matched_candidates = list(cache_dir.glob("dog_*.jpg"))
        elif "MEDICINE" in fn or "pharmacy" in title.lower():
            matched_candidates = list(cache_dir.glob("medicine_*.jpg"))
        elif "DRESS" in fn or "shopping" in title.lower():
            matched_candidates = list(cache_dir.glob("shopping_*.jpg"))

        if not matched_candidates:
            matched_candidates = list(cache_dir.glob("*.jpg"))

        if matched_candidates:
            chosen = random.choice(matched_candidates)
            img = Image.open(chosen).convert("RGB")
            img.save(output_path, "JPEG", quality=90)
            return

    width, height = 800, 600
    image = Image.new("RGB", (width, height), (35, 45, 60))
    image.save(output_path, "JPEG", quality=90)

def generate_curated_dataset(output_dir: Path = RAW_PHOTOS_DIR) -> List[Dict[str, Any]]:
    """Generates the ~240 photo library including the 5 ground-truth targets."""
    output_dir.mkdir(parents=True, exist_ok=True)
    all_photos_meta = []
    
    print(f"[*] Generating curated photo library into: {output_dir}")
    
    # 1. Render and register 5 Benchmark Targets
    for target in BENCHMARK_TARGETS:
        file_path = output_dir / target["filename"]
        badge = "[BENCHMARK TARGET]"
        render_synthetic_image(
            file_path,
            title=target["scenario_name"],
            subtitle=f"{target['neighborhood']}, {target['city']} • {target['timestamp'][:10]}",
            color_top=target["color_theme"][0],
            color_bottom=target["color_theme"][1],
            badge_text=badge
        )
        all_photos_meta.append({
            "photo_id": f"target_{target['target_id']}",
            "filename": target["filename"],
            "storage_path": str(file_path),
            "timestamp": target["timestamp"],
            "latitude": target["lat"],
            "longitude": target["lon"],
            "city": target["city"],
            "region": target["region"],
            "neighborhood": target["neighborhood"],
            "faces": target["faces"],
            "visual_tags": target["visual_tags"],
            "scene_type": target["scene_type"],
            "caption": target["caption"],
            "is_benchmark_target": True,
            "target_id": target["target_id"]
        })
        
    # 2. Render and register background library photos (~230 photos)
    photo_seq = 1000
    for template in SCENE_TEMPLATES:
        count = template["count"]
        base_time = template["base_time"]
        
        for i in range(count):
            photo_seq += 1
            # Proximity timestamp: stagger within 48h to form realistic trip clusters
            time_offset = timedelta(hours=random.uniform(0.5, 44.0), minutes=random.randint(0, 59))
            photo_ts = base_time + time_offset
            
            # Slight GPS jitter within <= 3 km
            lat_jitter = random.uniform(-0.015, 0.015)
            lon_jitter = random.uniform(-0.015, 0.015)
            photo_lat = round(template["lat"] + lat_jitter, 5)
            photo_lon = round(template["lon"] + lon_jitter, 5)
            
            # Companions
            faces = []
            if template["region"] == "Goa" and random.random() < 0.45:
                faces.append("face_cluster_1")  # Friend Alex in Goa
            elif template["scene_type"] in ["celebration", "restaurant"] and random.random() < 0.6:
                faces.append("face_cluster_2")  # Friend Priya in dinner
            elif template["region"] == "Himachal Pradesh" and random.random() < 0.4:
                faces.append("face_cluster_3")  # Hiking buddy Rohan
                
            fname = f"IMG_{template['region'][:3].upper()}_{photo_seq}.jpg"
            file_path = output_dir / fname
            caption = random.choice(template["captions"])
            
            render_synthetic_image(
                file_path,
                title=f"{template['neighborhood']} - {template['scene_type'].replace('_', ' ').title()}",
                subtitle=f"{template['city']}, {template['region']} • {photo_ts.strftime('%Y-%m-%d %H:%M')}",
                color_top=template["color_theme"][0],
                color_bottom=template["color_theme"][1],
                badge_text=f"{template['city'].upper()}"
            )
            
            all_photos_meta.append({
                "photo_id": f"photo_{photo_seq}",
                "filename": fname,
                "storage_path": str(file_path),
                "timestamp": photo_ts.isoformat() + "Z",
                "latitude": photo_lat,
                "longitude": photo_lon,
                "city": template["city"],
                "region": template["region"],
                "neighborhood": template["neighborhood"],
                "faces": faces,
                "visual_tags": list(set(template["visual_tags"] + [template["scene_type"]])),
                "scene_type": template["scene_type"],
                "caption": caption,
                "is_benchmark_target": False
            })
            
    print(f"[OK] Successfully generated {len(all_photos_meta)} curated photos in library.")
    return all_photos_meta
