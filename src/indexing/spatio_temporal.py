import math
from datetime import datetime
from typing import List, Dict, Any, Tuple
import numpy as np
from src.config import ST_DISTANCE_KM_THRESHOLD, ST_TIME_HOURS_THRESHOLD, ST_MIN_SAMPLES
from src.database.models import EventCluster
from src.indexing.exif_extractor import haversine_distance_km

def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parses ISO timestamp string to datetime object."""
    clean_ts = ts_str.rstrip("Z")
    try:
        return datetime.fromisoformat(clean_ts)
    except Exception:
        return datetime.now()

def cluster_spatio_temporal_events(
    photos: List[Dict[str, Any]],
    distance_threshold_km: float = ST_DISTANCE_KM_THRESHOLD,
    time_threshold_hours: float = ST_TIME_HOURS_THRESHOLD,
    min_samples: int = ST_MIN_SAMPLES
) -> Tuple[Dict[str, str], List[EventCluster]]:
    """
    ST-DBSCAN clustering algorithm over photo collection.
    Groups photos into semantic Trips/Events based on:
    - Haversine GPS distance <= distance_threshold_km (5 km)
    - Timestamp delta <= time_threshold_hours (48 hrs)
    
    Returns:
    - photo_id_to_cluster_id: mapping from photo_id to cluster_id
    - clusters: list of EventCluster models
    """
    n = len(photos)
    if n == 0:
        return {}, []

    # Parse timestamps and coords
    parsed_data = []
    for p in photos:
        ts = parse_iso_timestamp(p["timestamp"])
        lat = p.get("latitude")
        lon = p.get("longitude")
        parsed_data.append({
            "photo_id": p["photo_id"],
            "timestamp": ts,
            "lat": lat,
            "lon": lon,
            "region": p.get("region") or p.get("city") or "General"
        })

    visited = [False] * n
    cluster_labels = [-1] * n
    current_cluster_id = 0

    def get_neighbors(i: int) -> List[int]:
        neighbors = []
        p_i = parsed_data[i]
        for j in range(n):
            if i == j:
                continue
            p_j = parsed_data[j]
            # Time delta check
            time_delta_hrs = abs((p_i["timestamp"] - p_j["timestamp"]).total_seconds()) / 3600.0
            if time_delta_hrs > time_threshold_hours:
                continue
            
            # Spatial distance check
            if p_i["lat"] is not None and p_i["lon"] is not None and p_j["lat"] is not None and p_j["lon"] is not None:
                dist_km = haversine_distance_km(p_i["lat"], p_i["lon"], p_j["lat"], p_j["lon"])
                if dist_km <= distance_threshold_km:
                    neighbors.append(j)
            else:
                # If GPS is missing but same region/trip label and within 24h, group together
                if p_i["region"] == p_j["region"] and time_delta_hrs <= 24.0:
                    neighbors.append(j)
        return neighbors

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        neighbors = get_neighbors(i)
        
        if len(neighbors) < min_samples - 1:
            # Noise / standalone
            cluster_labels[i] = -1
        else:
            cluster_labels[i] = current_cluster_id
            queue = list(neighbors)
            while queue:
                j = queue.pop(0)
                if not visited[j]:
                    visited[j] = True
                    j_neighbors = get_neighbors(j)
                    if len(j_neighbors) >= min_samples - 1:
                        queue.extend([k for k in j_neighbors if k not in queue])
                if cluster_labels[j] == -1:
                    cluster_labels[j] = current_cluster_id
            current_cluster_id += 1

    # Map labels to EventCluster objects
    clusters_dict: Dict[int, List[int]] = {}
    for idx, label in enumerate(cluster_labels):
        if label != -1:
            clusters_dict.setdefault(label, []).append(idx)

    photo_to_cluster = {}
    event_clusters: List[EventCluster] = []

    for label, indices in clusters_dict.items():
        sample_photos = [parsed_data[i] for i in indices]
        sample_photos.sort(key=lambda x: x["timestamp"])
        
        start_ts = sample_photos[0]["timestamp"]
        end_ts = sample_photos[-1]["timestamp"]
        
        # Region inference from majority in cluster
        regions = [p["region"] for p in sample_photos if p["region"] != "General"]
        dominant_region = max(set(regions), key=regions.count) if regions else "Trip"
        
        cluster_id = f"event-{dominant_region.lower().replace(' ', '-')}-{start_ts.strftime('%b-%Y').lower()}"
        cluster_name = f"{dominant_region} Trip ({start_ts.strftime('%b %Y')})"
        
        sample_ids = [p["photo_id"] for p in sample_photos]
        for pid in sample_ids:
            photo_to_cluster[pid] = cluster_id
            
        event_clusters.append(EventCluster(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            region=dominant_region,
            start_time=start_ts.isoformat() + "Z",
            end_time=end_ts.isoformat() + "Z",
            photo_count=len(indices),
            sample_photo_ids=sample_ids[:5]
        ))

    return photo_to_cluster, event_clusters
