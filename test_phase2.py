import sys
import unittest
from pathlib import Path

# Configure UTF-8 encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi.testclient import TestClient

from src.config import (
    SQLITE_DB_PATH, QDRANT_STORAGE_PATH, COLLECTION_NAME,
    RAW_PHOTOS_DIR, THUMBNAILS_DIR
)
from src.database.db import get_all_photos, get_all_clusters
from src.storage.vector_store import LocalVectorStore
from src.engine.schemas import ExtractedMemoryCues, CueChip, SearchRequest
from src.engine.understand import GroqCueExtractor, global_cue_extractor
from src.engine.connect import HybridRetriever, global_retriever
from src.engine.session import SessionManager, global_session_manager
from src.api.main import app

class TestPhase2UnderstandAndConnect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_client = TestClient(app)
        cls.cue_extractor = global_cue_extractor
        cls.retriever = global_retriever
        cls.session_mgr = global_session_manager

    def test_01_llm_cue_extraction_primary_scenario(self):
        """
        Validate Deliverable: 'I'm looking for that small café we went to during our Goa trip with my friend'
        Correctly parses JSON memory facets.
        """
        query = "I'm looking for that small café we went to during our Goa trip with my friend."
        cues, chips = self.cue_extractor.extract_cues(query)

        print("\n" + "=" * 70)
        print("TEST 01: LLM CUE EXTRACTION (PRIMARY SCENARIO)")
        print("=" * 70)
        print(f"Query: '{query}'")
        print(f"Extracted Spatial: {cues.spatial.model_dump()}")
        print(f"Extracted Temporal: {cues.temporal.model_dump()}")
        print(f"Extracted Social: {cues.social.model_dump()}")
        print(f"Visual Concepts: {cues.visual_concepts}")
        print(f"Confidence Score: {cues.confidence_score}")
        print(f"Generated Chips: {[c.label for c in chips]}")

        # Assertions on parsed facets
        self.assertIsNotNone(cues.spatial.region, "Must extract region 'Goa'")
        self.assertEqual(cues.spatial.region.lower(), "goa")
        
        self.assertIsNotNone(cues.spatial.setting, "Must extract setting 'cafe'")
        self.assertIn("cafe", cues.spatial.setting.lower())

        self.assertIsNotNone(cues.social.companion_type, "Must extract companion 'friend'")
        self.assertIn("friend", cues.social.companion_type.lower())

        # Assert chips generated
        chip_types = [c.type for c in chips]
        self.assertIn("place", chip_types, "Must generate Place chip")
        self.assertIn("setting", chip_types, "Must generate Setting chip")
        self.assertIn("people", chip_types, "Must generate People chip")

    def test_02_cue_extractor_resilient_fallback(self):
        """Validate offline / heuristic fallback extraction when Groq is bypassed."""
        offline_extractor = GroqCueExtractor(api_key="")
        query = "monsoon cutting chai street food in Mumbai with Alex"
        cues, chips = offline_extractor.extract_cues(query)

        self.assertEqual(cues.spatial.region, "Mumbai")
        self.assertEqual(cues.spatial.setting, "street_food")
        self.assertEqual(cues.temporal.season, "monsoon")
        self.assertEqual(cues.social.companion_type, "friend")
        self.assertIn("Alex", cues.social.companion_names)
        self.assertTrue(len(chips) >= 4)

    def test_03_hybrid_retriever_constrained_to_goa(self):
        """
        Validate Deliverable: Hybrid search candidates constrained to Goa trip photos,
        and target photo IMG_GOA_CAFE_4021.jpg ranks #1.
        """
        query = "I'm looking for that small café we went to during our Goa trip with my friend."
        cues, chips = self.cue_extractor.extract_cues(query)
        candidates, metrics, relaxed = self.retriever.search(
            query=query,
            cues=cues,
            active_chips=chips,
            top_k=10
        )

        print("\n" + "=" * 70)
        print("TEST 03: HYBRID SEARCH CONSTRAINED CANDIDATES")
        print("=" * 70)
        print(f"Total candidates: {len(candidates)}, Relaxed filter: {relaxed}")
        print(f"Top-1 Candidate: {candidates[0].filename} (Score: {candidates[0].score:.4f})")
        print(f"Margin Delta (Top1 - Top5): {metrics.margin_delta:.4f}")
        print(f"Confidence Status: {metrics.status}")

        self.assertGreater(len(candidates), 0, "Must return candidate photos")
        
        # Verify all candidates are in Goa
        for cand in candidates:
            self.assertEqual(cand.region, "Goa", f"Candidate {cand.filename} must be constrained to Goa")

        # Verify Target #1 is ranked #1
        top_cand = candidates[0]
        self.assertEqual(top_cand.filename, "IMG_GOA_CAFE_4021.jpg", "Target 1 must be top-ranked candidate")
        self.assertGreaterEqual(top_cand.score, 0.80, "Top candidate score should be >= 0.80")
        self.assertTrue(len(top_cand.matched_cues) > 0, "Must have matched cue tags")

    def test_04_all_5_benchmark_scenarios_end_to_end(self):
        """Verify that the Understand + Connect pipeline retrieves Target #1 across all 5 benchmark scenarios."""
        scenarios = [
            (
                "I'm looking for that small café we went to during our Goa trip with my friend",
                "IMG_GOA_CAFE_4021.jpg",
                "Scenario 1: Goa Café with Friend"
            ),
            (
                "outdoor street food market in rain monsoon cutting chai Mumbai",
                "IMG_MUMBAI_RAIN_2104.jpg",
                "Scenario 2: Rainy Mumbai Street Food"
            ),
            (
                "group birthday party celebration cake candles dinner",
                "IMG_BDAY_PARTY_8812.jpg",
                "Scenario 3: Birthday Celebration"
            ),
            (
                "mountain sunrise hike peaks trail Solang Manali",
                "IMG_MANALI_HIKE_1045.jpg",
                "Scenario 4: Manali Mountain Sunrise Hike"
            ),
            (
                "golden retriever dog playing at Palolem beach resort in Goa",
                "IMG_PALOLEM_DOG_5541.jpg",
                "Scenario 5: Dog Playing at Beach"
            )
        ]

        print("\n" + "=" * 70)
        print("TEST 04: ALL 5 BENCHMARK SCENARIOS (UNDERSTAND + CONNECT)")
        print("=" * 70)

        for query, expected_filename, label in scenarios:
            cues, chips = self.cue_extractor.extract_cues(query)
            candidates, metrics, relaxed = self.retriever.search(
                query=query,
                cues=cues,
                active_chips=chips,
                top_k=5
            )

            self.assertTrue(len(candidates) > 0, f"Query '{query}' returned 0 candidates")
            top_cand = candidates[0]

            print(f"[{label}]")
            print(f"  Query:    '{query}'")
            print(f"  Cues:     {cues.model_dump()}")
            print(f"  Expected: {expected_filename}")
            print(f"  Top Hit:  {top_cand.filename} [Score: {top_cand.score:.4f}]")
            for c in candidates[:3]:
                print(f"    -> {c.filename}: Score={c.score:.4f}, Vec={c.vector_score}, Meta={c.metadata_score}, Temp={c.temporal_score}, Soc={c.social_score}")
            print(f"  Margin:   {metrics.margin_delta:.4f} | Status: {metrics.status}")

            self.assertEqual(
                top_cand.filename, expected_filename,
                f"For '{label}', expected {expected_filename} at Rank 1, got {top_cand.filename}"
            )
            self.assertGreaterEqual(top_cand.score, 0.80)

    def test_05_soft_filter_relaxation_overconstrained(self):
        """Test that overconstrained filter (0 exact matches) triggers relaxation rather than empty screen."""
        query = "small cafe coffee"
        cues, chips = self.cue_extractor.extract_cues(query)
        # Force a region filter for a place with no cafe photos
        candidates, metrics, relaxed = self.retriever.search(
            query=query,
            cues=cues,
            active_chips=chips,
            top_k=5,
            filter_region="NonExistentRegion"
        )
        self.assertTrue(relaxed, "Should trigger soft filter relaxation")
        self.assertGreater(len(candidates), 0, "Must return candidates via relaxed search pass")

    def test_06_fastapi_endpoints(self):
        """Test API Gateway endpoints: /api/health, /api/search, /api/session, /api/clusters, /api/photos."""
        # 1. Health Endpoint
        res_health = self.api_client.get("/api/health")
        self.assertEqual(res_health.status_code, 200)
        health_data = res_health.json()
        self.assertEqual(health_data["status"], "healthy")
        self.assertGreaterEqual(health_data["database_photos_count"], 200)

        # 2. Search Endpoint
        search_payload = {
            "query": "that small café during our Goa trip with my friend",
            "top_k": 5
        }
        res_search = self.api_client.post("/api/search", json=search_payload)
        self.assertEqual(res_search.status_code, 200)
        search_data = res_search.json()

        self.assertIn("session_id", search_data)
        session_id = search_data["session_id"]
        self.assertGreater(len(search_data["candidates"]), 0)
        self.assertEqual(search_data["candidates"][0]["filename"], "IMG_GOA_CAFE_4021.jpg")
        self.assertTrue(len(search_data["chips"]) >= 3)

        # Verify image URL formats
        first_cand = search_data["candidates"][0]
        self.assertTrue(first_cand["thumbnail_url"].startswith("/thumbnails/"))
        self.assertTrue(first_cand["full_photo_url"].startswith("/photos/"))

        # 3. Session Retrieval Endpoint
        res_session = self.api_client.get(f"/api/session/{session_id}")
        self.assertEqual(res_session.status_code, 200)
        session_data = res_session.json()
        self.assertEqual(session_data["session_id"], session_id)
        self.assertEqual(session_data["turn_count"], 1)

        # 4. Chip Update Endpoint
        chip_to_update = session_data["chips"][0]["id"]
        res_chip = self.api_client.post(
            f"/api/session/{session_id}/chip",
            json={"chip_id": chip_to_update, "status": "confirmed"}
        )
        self.assertEqual(res_chip.status_code, 200)
        updated_session = res_chip.json()
        updated_chip = next(c for c in updated_session["chips"] if c["id"] == chip_to_update)
        self.assertEqual(updated_chip["status"], "confirmed")

        # 5. Clusters Endpoint
        res_clusters = self.api_client.get("/api/clusters")
        self.assertEqual(res_clusters.status_code, 200)
        self.assertGreaterEqual(res_clusters.json()["total"], 5)

        # 6. Single Photo Endpoint
        photo_id = first_cand["photo_id"]
        res_photo = self.api_client.get(f"/api/photos/{photo_id}")
        self.assertEqual(res_photo.status_code, 200)
        self.assertEqual(res_photo.json()["filename"], "IMG_GOA_CAFE_4021.jpg")

    def test_07_static_files_served(self):
        """Test that static thumbnail and raw photo files are served correctly via HTTP."""
        res_thumb = self.api_client.get("/thumbnails/IMG_GOA_CAFE_4021_thumb.webp")
        self.assertEqual(res_thumb.status_code, 200)
        self.assertEqual(res_thumb.headers.get("content-type"), "image/webp")

        res_raw = self.api_client.get("/photos/IMG_GOA_CAFE_4021.jpg")
        self.assertEqual(res_raw.status_code, 200)
        self.assertEqual(res_raw.headers.get("content-type"), "image/jpeg")

if __name__ == "__main__":
    unittest.main()
