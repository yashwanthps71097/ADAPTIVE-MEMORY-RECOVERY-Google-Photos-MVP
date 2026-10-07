import sys
import os
import time
from pathlib import Path
from typing import List, Dict, Any

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from src.config import (
    RAW_PHOTOS_DIR, THUMBNAILS_DIR, SQLITE_DB_PATH,
    QDRANT_STORAGE_PATH, COLLECTION_NAME
)
from src.database.db import (
    init_db, upsert_photo, update_photo_cluster,
    upsert_cluster, get_all_photos
)
from src.database.models import PhotoMetadata, ExifMetadata, GeocodedLocation
from src.indexing.exif_extractor import extract_exif, reverse_geocode, generate_thumbnail
from src.indexing.spatio_temporal import cluster_spatio_temporal_events
from src.indexing.face_indexer import annotate_photo_faces
from src.indexing.embedder import global_embedder
from src.storage.vector_store import LocalVectorStore
from src.dataset.generator import generate_curated_dataset

def run_ingestion_pipeline(generate_dataset: bool = True) -> Dict[str, Any]:
    """
    Executes the complete Phase 1 Data Ingestion & Indexing Pipeline:
    1. Dataset Curation / Verification
    2. Database & Vector Store Initialization
    3. Metadata, EXIF Extraction & Reverse Geocoding
    4. WebP Thumbnail Generation
    5. Multimodal Embedding Generation (512-d)
    6. ST-DBSCAN Spatio-Temporal Event Clustering
    7. Qdrant HNSW Vector Store Population
    """
    start_time = time.time()
    print("=" * 70)
    print("AI-NATIVE PHOTO RETRIEVAL MVP: PHASE 1 INGESTION PIPELINE")
    print("=" * 70)

    # 1. Initialize SQLite Database & Qdrant Vector Store
    print("[1/6] Initializing storage layers...")
    init_db(SQLITE_DB_PATH)
    vector_store = LocalVectorStore(storage_path=QDRANT_STORAGE_PATH, collection_name=COLLECTION_NAME)
    print("  [OK] SQLite schema initialized at:", SQLITE_DB_PATH)
    print("  [OK] Qdrant collection ready at:", QDRANT_STORAGE_PATH)

    # 2. Check / Generate Dataset
    photos_meta_cache = {}
    existing_photos = list(RAW_PHOTOS_DIR.glob("*.jpg"))
    if generate_dataset or len(existing_photos) < 50:
        print(f"[2/6] Generating curated realistic photo library (~240 photos)...")
        dataset_meta = generate_curated_dataset(output_dir=RAW_PHOTOS_DIR)
        for m in dataset_meta:
            photos_meta_cache[m["filename"]] = m
    else:
        print(f"[2/6] Found {len(existing_photos)} existing photos in {RAW_PHOTOS_DIR}")

    photo_files = sorted(list(RAW_PHOTOS_DIR.glob("*.jpg")))
    print(f"[3/6] Processing {len(photo_files)} photos (EXIF, Thumbnails, Embeddings)...")

    photo_records: List[PhotoMetadata] = []
    vector_points: List[Dict[str, Any]] = []

    for idx, img_path in enumerate(photo_files):
        filename = img_path.name
        cached_meta = photos_meta_cache.get(filename, {})
        
        photo_id = cached_meta.get("photo_id", f"photo_{img_path.stem}")
        
        # EXIF & Geocoding
        exif_obj, timestamp_str, lat, lon = extract_exif(img_path)
        
        # Override with curated ground-truth if available
        if cached_meta.get("timestamp"):
            timestamp_str = cached_meta["timestamp"]
        if cached_meta.get("latitude") is not None:
            lat = cached_meta["latitude"]
            lon = cached_meta["longitude"]
            exif_obj.has_gps = True

        location_obj = reverse_geocode(lat, lon)
        if cached_meta.get("city"):
            location_obj.city = cached_meta["city"]
            location_obj.region = cached_meta["region"]
            location_obj.neighborhood = cached_meta.get("neighborhood")

        # Thumbnail Generation
        thumb_path = generate_thumbnail(img_path, output_dir=THUMBNAILS_DIR, max_size=360)

        # Faces & Companions
        faces_list = annotate_photo_faces(cached_meta, cached_meta.get("faces"))

        # Visual Tags & Scene Type
        scene_type = cached_meta.get("scene_type", "general")
        visual_tags = cached_meta.get("visual_tags", ["photo", scene_type])
        caption = cached_meta.get("caption", f"A photo taken in {location_obj.city or 'India'}.")

        # Generate 512-d Multimodal Embedding
        photo_meta_for_embed = {
            "scene_type": scene_type,
            "visual_tags": visual_tags,
            "caption": caption,
            "neighborhood": location_obj.neighborhood or "",
            "region": location_obj.region or "",
            "faces": cached_meta.get("faces", [])
        }
        dense_vector = global_embedder.embed_photo(photo_meta_for_embed)

        embedding_vector_id = f"vec-{photo_id}"

        # Construct Photo Model
        photo_model = PhotoMetadata(
            photo_id=photo_id,
            filename=filename,
            storage_path=str(img_path),
            thumbnail_path=str(thumb_path),
            timestamp=timestamp_str,
            exif=exif_obj,
            location=location_obj,
            event_cluster_id=None,  # Assigned in next clustering step
            faces=faces_list,
            visual_tags=visual_tags,
            scene_type=scene_type,
            caption=caption,
            embedding_vector_id=embedding_vector_id
        )

        upsert_photo(photo_model, SQLITE_DB_PATH)
        photo_records.append(photo_model)

        # Payload for Qdrant
        vector_points.append({
            "id": photo_id,
            "vector": dense_vector,
            "payload": {
                "photo_id": photo_id,
                "filename": filename,
                "thumbnail_path": str(thumb_path),
                "timestamp": timestamp_str,
                "region": location_obj.region,
                "city": location_obj.city,
                "neighborhood": location_obj.neighborhood,
                "scene_type": scene_type,
                "visual_tags": visual_tags,
                "caption": caption,
                "has_friend": len(faces_list) > 0,
                "is_benchmark_target": cached_meta.get("is_benchmark_target", False),
                "target_id": cached_meta.get("target_id")
            }
        })

        if (idx + 1) % 50 == 0 or (idx + 1) == len(photo_files):
            print(f"  Processed {idx + 1}/{len(photo_files)} photos...")

    # 4. Spatio-Temporal Event Clustering (ST-DBSCAN)
    print("[4/6] Executing ST-DBSCAN Spatio-Temporal Event Clustering (<= 5km, <= 48hrs)...")
    db_photos = get_all_photos(SQLITE_DB_PATH)
    photo_to_cluster, clusters = cluster_spatio_temporal_events(db_photos)
    
    for pid, cid in photo_to_cluster.items():
        update_photo_cluster(pid, cid, SQLITE_DB_PATH)
        # Update payload for vector point
        for pt in vector_points:
            if pt["id"] == pid:
                pt["payload"]["event_cluster_id"] = cid

    for c in clusters:
        upsert_cluster(c, SQLITE_DB_PATH)
        print(f"  [OK] Discovered Event: '{c.cluster_name}' ({c.photo_count} photos, {c.start_time[:10]} to {c.end_time[:10]})")

    # 5. Populate Qdrant Vector Collection
    print(f"[5/6] Populating Qdrant HNSW Vector Collection with {len(vector_points)} vectors...")
    vector_store.upsert_batch(vector_points)
    total_vectors = vector_store.count()
    print(f"  [OK] Qdrant Collection '{COLLECTION_NAME}' indexed: {total_vectors} points")

    # 6. Milestone Validation Check: "small cozy café"
    print("[6/6] Running Phase 1 Milestone Verification Check...")
    test_query = "small cozy café"
    query_vec = global_embedder.embed_text(test_query)
    search_hits = vector_store.search(query_vec, top_k=5)
    
    print("\n" + "-" * 70)
    print(f"VERIFICATION SEARCH: Query = '{test_query}'")
    print("-" * 70)
    for rank, hit in enumerate(search_hits, 1):
        payload = hit["payload"]
        print(f"Rank {rank} [Score: {hit['score']:.4f}]: {payload.get('filename')} | {payload.get('neighborhood')}, {payload.get('region')} | Tags: {payload.get('visual_tags')[:4]}")
    
    elapsed = time.time() - start_time
    print("-" * 70)
    print(f"[OK] Phase 1 Ingestion Pipeline Completed Successfully in {elapsed:.2f}s!")
    print("=" * 70)

    return {
        "status": "success",
        "photos_indexed": len(photo_records),
        "clusters_discovered": len(clusters),
        "vector_count": total_vectors,
        "elapsed_seconds": elapsed
    }

if __name__ == "__main__":
    force_gen = "--generate" in sys.argv or "-g" in sys.argv or True
    run_ingestion_pipeline(generate_dataset=force_gen)
