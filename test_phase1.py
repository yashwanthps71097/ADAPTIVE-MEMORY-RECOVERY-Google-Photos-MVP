import sys
import unittest
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from src.config import (
    RAW_PHOTOS_DIR, THUMBNAILS_DIR, SQLITE_DB_PATH,
    QDRANT_STORAGE_PATH, COLLECTION_NAME, VECTOR_DIMENSION
)
from src.database.db import get_all_photos, get_all_clusters, get_photo_by_id
from src.storage.vector_store import LocalVectorStore
from src.indexing.embedder import global_embedder

class TestPhase1Ingestion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vector_store = LocalVectorStore(
            storage_path=QDRANT_STORAGE_PATH,
            collection_name=COLLECTION_NAME
        )
        cls.photos = get_all_photos(SQLITE_DB_PATH)
        cls.clusters = get_all_clusters(SQLITE_DB_PATH)

    def test_01_photo_dataset_and_thumbnails(self):
        """Test that realistic photo collection and WebP thumbnails exist."""
        raw_files = list(RAW_PHOTOS_DIR.glob("*.jpg"))
        self.assertGreaterEqual(len(raw_files), 200, "Should have at least 200 raw photos in library")
        
        thumb_files = list(THUMBNAILS_DIR.glob("*.webp"))
        self.assertGreaterEqual(len(thumb_files), 200, "Should have corresponding WebP thumbnails")

        # Verify all 5 benchmark targets are physically present on disk
        expected_targets = [
            "IMG_GOA_CAFE_4021.jpg",
            "IMG_MUMBAI_RAIN_2104.jpg",
            "IMG_BDAY_PARTY_8812.jpg",
            "IMG_MANALI_HIKE_1045.jpg",
            "IMG_PALOLEM_DOG_5541.jpg"
        ]
        for t_file in expected_targets:
            self.assertTrue((RAW_PHOTOS_DIR / t_file).exists(), f"Target photo {t_file} must exist on disk")

    def test_02_database_records_and_metadata(self):
        """Test SQLite schema and metadata population."""
        self.assertGreaterEqual(len(self.photos), 200, "SQLite photos table must have >= 200 records")
        
        # Verify Target #1 metadata details
        t1 = next((p for p in self.photos if "4021" in p["filename"]), None)
        self.assertIsNotNone(t1, "Target #1 record must exist in SQLite database")
        self.assertEqual(t1["region"], "Goa")
        self.assertEqual(t1["neighborhood"], "Fontainhas")
        self.assertEqual(t1["scene_type"], "cafe")
        self.assertTrue(len(t1["faces"]) > 0, "Target #1 must have companion face annotation")

    def test_03_spatio_temporal_clusters(self):
        """Test that ST-DBSCAN identified semantic trips/events."""
        self.assertGreaterEqual(len(self.clusters), 5, "Should identify at least 5 semantic event clusters")
        cluster_names = [c["cluster_name"] for c in self.clusters]
        
        # Verify Goa trip event is formed
        has_goa = any("Goa" in name for name in cluster_names)
        self.assertTrue(has_goa, "Must discover a Goa Trip event cluster")
        
        # Verify photos have cluster assignments
        clustered_photos = [p for p in self.photos if p["event_cluster_id"]]
        self.assertGreater(len(clustered_photos), 150, "Most photos should be assigned to an event cluster")

    def test_04_qdrant_vector_store_integrity(self):
        """Test Qdrant collection size and vector search capability."""
        total_vectors = self.vector_store.count()
        self.assertGreaterEqual(total_vectors, 200, "Qdrant collection must index >= 200 vectors")

    def test_05_retrieval_baseline_all_5_scenarios(self):
        """Verify vector search accuracy across all 5 benchmark scenarios."""
        scenarios = [
            ("small cozy café in Goa with my friend", "IMG_GOA_CAFE_4021.jpg", "Target 1 (Goa Café)"),
            ("outdoor street food market in rain monsoon", "IMG_MUMBAI_RAIN_2104.jpg", "Target 2 (Rainy Market)"),
            ("group birthday party celebration cake candles", "IMG_BDAY_PARTY_8812.jpg", "Target 3 (Birthday Celebration)"),
            ("mountain sunrise hike peaks trail", "IMG_MANALI_HIKE_1045.jpg", "Target 4 (Mountain Sunrise)"),
            ("golden retriever dog playing at beach resort", "IMG_PALOLEM_DOG_5541.jpg", "Target 5 (Dog Beach)")
        ]

        print("\n" + "=" * 70)
        print("RUNNING 5 BENCHMARK SCENARIO RETRIEVAL TESTS")
        print("=" * 70)

        for query, expected_filename, scenario_name in scenarios:
            query_vec = global_embedder.embed_text(query)
            hits = self.vector_store.search(query_vec, top_k=5)
            self.assertTrue(len(hits) > 0, f"Query '{query}' returned 0 hits")
            
            top_hit = hits[0]
            top_filename = top_hit["payload"]["filename"]
            score = top_hit["score"]
            
            print(f"[{scenario_name}]")
            print(f"  Query: '{query}'")
            print(f"  Top Hit: {top_filename} [Score: {score:.4f}]")
            print(f"  Target:  {expected_filename}")
            
            self.assertEqual(
                top_filename, expected_filename,
                f"For scenario '{scenario_name}', expected {expected_filename} at Rank 1, got {top_filename}"
            )
            self.assertGreater(score, 0.85, f"Expected cosine similarity > 0.85, got {score}")

    def test_06_payload_filtering(self):
        """Test Qdrant payload filtering by geographic region."""
        query_vec = global_embedder.embed_text("café coffee")
        # Filter only to Goa
        goa_hits = self.vector_store.search(query_vec, top_k=10, region_filter="Goa")
        self.assertTrue(len(goa_hits) > 0)
        for h in goa_hits:
            self.assertEqual(h["payload"]["region"], "Goa", "All returned hits must be in Goa when region filter is active")

if __name__ == "__main__":
    unittest.main()
