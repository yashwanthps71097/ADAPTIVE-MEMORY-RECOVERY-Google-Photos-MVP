import sqlite3
import json
from typing import List, Optional, Dict, Any
from pathlib import Path
from src.config import SQLITE_DB_PATH
from src.database.models import PhotoMetadata, EventCluster

def get_connection(db_path: Path = SQLITE_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path = SQLITE_DB_PATH) -> None:
    """Initializes the SQLite schema for photos and clusters."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS photos (
                photo_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                thumbnail_path TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                camera_model TEXT,
                latitude REAL,
                longitude REAL,
                city TEXT,
                region TEXT,
                neighborhood TEXT,
                event_cluster_id TEXT,
                faces_json TEXT,
                visual_tags_json TEXT,
                scene_type TEXT,
                caption TEXT,
                embedding_vector_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS event_clusters (
                cluster_id TEXT PRIMARY KEY,
                cluster_name TEXT NOT NULL,
                region TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                photo_count INTEGER NOT NULL,
                sample_photo_ids_json TEXT
            );
        """)
        
        # Indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_photos_timestamp ON photos(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_photos_region ON photos(region);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_photos_cluster ON photos(event_cluster_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_photos_scene ON photos(scene_type);")
        conn.commit()

def upsert_photo(photo: PhotoMetadata, db_path: Path = SQLITE_DB_PATH) -> None:
    """Inserts or updates a photo record."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO photos (
                photo_id, filename, storage_path, thumbnail_path, timestamp,
                camera_model, latitude, longitude, city, region, neighborhood,
                event_cluster_id, faces_json, visual_tags_json, scene_type,
                caption, embedding_vector_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            photo.photo_id,
            photo.filename,
            photo.storage_path,
            photo.thumbnail_path,
            photo.timestamp,
            photo.exif.camera_model if photo.exif else None,
            photo.location.latitude if photo.location else None,
            photo.location.longitude if photo.location else None,
            photo.location.city if photo.location else None,
            photo.location.region if photo.location else None,
            photo.location.neighborhood if photo.location else None,
            photo.event_cluster_id,
            json.dumps([f.model_dump() for f in photo.faces]),
            json.dumps(photo.visual_tags),
            photo.scene_type,
            photo.caption,
            photo.embedding_vector_id
        ))
        conn.commit()

def update_photo_cluster(photo_id: str, cluster_id: str, db_path: Path = SQLITE_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE photos SET event_cluster_id = ? WHERE photo_id = ?", (cluster_id, photo_id))
        conn.commit()

def upsert_cluster(cluster: EventCluster, db_path: Path = SQLITE_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO event_clusters (
                cluster_id, cluster_name, region, start_time, end_time,
                photo_count, sample_photo_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cluster.cluster_id,
            cluster.cluster_name,
            cluster.region,
            cluster.start_time,
            cluster.end_time,
            cluster.photo_count,
            json.dumps(cluster.sample_photo_ids)
        ))
        conn.commit()

def get_photo_by_id(photo_id: str, db_path: Path = SQLITE_DB_PATH) -> Optional[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM photos WHERE photo_id = ?", (photo_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        res["faces"] = json.loads(res["faces_json"]) if res.get("faces_json") else []
        res["visual_tags"] = json.loads(res["visual_tags_json"]) if res.get("visual_tags_json") else []
        return res

def get_all_photos(db_path: Path = SQLITE_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM photos ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["faces"] = json.loads(d["faces_json"]) if d.get("faces_json") else []
            d["visual_tags"] = json.loads(d["visual_tags_json"]) if d.get("visual_tags_json") else []
            result.append(d)
        return result

def get_all_clusters(db_path: Path = SQLITE_DB_PATH) -> List[Dict[str, Any]]:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM event_clusters ORDER BY start_time DESC")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["sample_photo_ids"] = json.loads(d["sample_photo_ids_json"]) if d.get("sample_photo_ids_json") else []
            result.append(d)
        return result

def get_related_photos(photo_id: str, limit: int = 8, db_path: Path = SQLITE_DB_PATH) -> List[Dict[str, Any]]:
    """
    Finds other photos taken at the SAME location / event cluster as the target photo.
    Prioritization hierarchy:
    1. Same neighborhood & city (exact location)
    2. Same event_cluster_id (same trip/event)
    3. Same city or region & scene_type
    4. Same region
    Excludes the target photo itself and duplicate filenames.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM photos WHERE photo_id = ?", (photo_id,))
        target = cursor.fetchone()
        if not target:
            return []
        
        target = dict(target)
        t_nid = target.get("neighborhood")
        t_city = target.get("city")
        t_reg = target.get("region")
        t_cluster = target.get("event_cluster_id")
        t_scene = target.get("scene_type")
        t_fn = target.get("filename")

        results = []
        seen_filenames = {t_fn} if t_fn else set()
        seen_pids = {photo_id}

        def add_rows(query, params):
            cursor.execute(query, params)
            for row in cursor.fetchall():
                d = dict(row)
                fn = d.get("filename")
                pid = d.get("photo_id")
                if pid not in seen_pids and fn not in seen_filenames:
                    seen_pids.add(pid)
                    if fn:
                        seen_filenames.add(fn)
                    d["faces"] = json.loads(d["faces_json"]) if d.get("faces_json") else []
                    d["visual_tags"] = json.loads(d["visual_tags_json"]) if d.get("visual_tags_json") else []
                    results.append(d)
                    if len(results) >= limit:
                        return True
            return False

        # Pass 1: Same neighborhood & city (exact venue)
        if t_nid and t_city:
            if add_rows("SELECT * FROM photos WHERE neighborhood = ? AND city = ? AND photo_id != ? ORDER BY timestamp DESC", (t_nid, t_city, photo_id)):
                return results

        # Pass 2: Same city (same town, e.g. Calangute)
        if t_city:
            if add_rows("SELECT * FROM photos WHERE city = ? AND photo_id != ? ORDER BY timestamp DESC", (t_city, photo_id)):
                return results

        # Pass 3: Same event cluster with matching scene_type (e.g. hotel/resort in Goa trip)
        if t_cluster and t_scene:
            if add_rows("SELECT * FROM photos WHERE event_cluster_id = ? AND scene_type = ? AND photo_id != ? ORDER BY timestamp DESC", (t_cluster, t_scene, photo_id)):
                return results

        # Pass 4: Same event_cluster_id (same overall trip)
        if t_cluster:
            if add_rows("SELECT * FROM photos WHERE event_cluster_id = ? AND photo_id != ? ORDER BY timestamp DESC", (t_cluster, photo_id)):
                return results

        # Pass 5: Same region with matching scene_type
        if t_reg and t_scene:
            if add_rows("SELECT * FROM photos WHERE region = ? AND scene_type = ? AND photo_id != ? ORDER BY timestamp DESC", (t_reg, t_scene, photo_id)):
                return results

        # Pass 6: Same region
        if t_reg:
            add_rows("SELECT * FROM photos WHERE region = ? AND photo_id != ? ORDER BY timestamp DESC", (t_reg, photo_id))

        return results

