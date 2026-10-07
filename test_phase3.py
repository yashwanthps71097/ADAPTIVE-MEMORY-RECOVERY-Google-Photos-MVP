import sys
import unittest

# Configure UTF-8 encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi.testclient import TestClient

from src.api.main import app
from src.engine.schemas import (
    CandidatePhoto, ExtractedMemoryCues, SpatialCue,
    RefineRequest
)
from src.engine.recover import RecoverEngine, global_recover_engine
from src.engine.session import global_session_manager

class TestPhase3RecoverEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_client = TestClient(app)
        cls.recover_engine = global_recover_engine
        cls.session_mgr = global_session_manager

    def _create_mock_ambiguous_candidates(self):
        """Creates realistic candidate photos with diverse venue settings in Goa."""
        return [
            CandidatePhoto(
                photo_id="mock_goa_rest_1",
                filename="IMG_GOA_REST_1.jpg",
                thumbnail_url="/thumbnails/mock_1_thumb.webp",
                full_photo_url="/photos/mock_1.jpg",
                score=0.62,
                vector_score=0.61,
                metadata_score=0.65,
                social_score=0.60,
                temporal_score=0.60,
                scene_type="restaurant",
                region="Goa",
                visual_tags=["restaurant", "dinner", "seafood", "table"]
            ),
            CandidatePhoto(
                photo_id="mock_goa_beach_cafe_2",
                filename="IMG_GOA_BEACH_CAFE_2.jpg",
                thumbnail_url="/thumbnails/mock_2_thumb.webp",
                full_photo_url="/photos/mock_2.jpg",
                score=0.61,
                vector_score=0.60,
                metadata_score=0.63,
                social_score=0.60,
                temporal_score=0.60,
                scene_type="beach_cafe",
                region="Goa",
                visual_tags=["beach cafe", "shack", "sunbeds", "sea"]
            ),
            CandidatePhoto(
                photo_id="mock_goa_hotel_3",
                filename="IMG_GOA_HOTEL_3.jpg",
                thumbnail_url="/thumbnails/mock_3_thumb.webp",
                full_photo_url="/photos/mock_3.jpg",
                score=0.60,
                vector_score=0.59,
                metadata_score=0.62,
                social_score=0.60,
                temporal_score=0.60,
                scene_type="hotel",
                region="Goa",
                visual_tags=["hotel", "resort", "patio", "pool"]
            ),
            CandidatePhoto(
                photo_id="mock_goa_cafe_4",
                filename="IMG_GOA_CAFE_4021.jpg",
                thumbnail_url="/thumbnails/IMG_GOA_CAFE_4021_thumb.webp",
                full_photo_url="/photos/IMG_GOA_CAFE_4021.jpg",
                score=0.60,
                vector_score=0.59,
                metadata_score=0.62,
                social_score=0.60,
                temporal_score=0.60,
                scene_type="cafe",
                region="Goa",
                visual_tags=["cafe", "coffee", "wood table"]
            )
        ]

    def test_01_tier1_prompt_generation_primary_scenario(self):
        """
        Deliverable Check 1:
        Automated test verifying Tier-1 prompt generation:
        querying 'That café in Goa with my friend' with ambiguous candidates
        produces 'Was it a restaurant, beach café, or hotel?'.
        """
        query = "That café in Goa with my friend"
        candidates = self._create_mock_ambiguous_candidates()
        cues = ExtractedMemoryCues(
            spatial=SpatialCue(region="Goa", setting="cafe"),
            raw_query=query
        )

        prompt = self.recover_engine.generate_tier1_prompt(candidates, cues, query)

        print("\n" + "=" * 70)
        print("TEST 01: TIER-1 DETAIL CLARIFICATION PROMPT GENERATION")
        print("=" * 70)
        print(f"Query: '{query}'")
        print(f"Generated Question: '{prompt.question_text}'")
        print(f"Options: {[(o.option_id, o.label, o.filter_modifier) for o in prompt.options]}")

        # Assert question text isolates the primary settings
        q_lower = prompt.question_text.lower()
        self.assertIn("restaurant", q_lower, "Question must mention restaurant")
        self.assertTrue("beach" in q_lower or "cafe" in q_lower or "café" in q_lower, "Question must mention beach café")
        self.assertIn("hotel", q_lower, "Question must mention hotel")

        # Assert options
        labels_lower = [o.label.lower() for o in prompt.options]
        self.assertTrue(any("restaurant" in l for l in labels_lower), "Must have Restaurant option")
        self.assertTrue(any("beach" in l for l in labels_lower), "Must have Beach Café option")
        self.assertTrue(any("hotel" in l for l in labels_lower), "Must have Hotel option")

    def test_02_tier2_prompt_generation_escalation(self):
        """
        Deliverable Check 2:
        Automated test verifying Tier-2 prompt escalation:
        if candidates remain weak after setting refinement,
        engine generates 'Which feels familiar?' with associative cue tags.
        """
        query = "That café in Goa with my friend"
        candidates = self._create_mock_ambiguous_candidates()
        cues = ExtractedMemoryCues(
            spatial=SpatialCue(region="Goa", setting="beach_cafe"),
            raw_query=query
        )

        tier2_prompt = self.recover_engine.generate_tier2_prompt(candidates, cues, query)

        print("\n" + "=" * 70)
        print("TEST 02: TIER-2 ASSOCIATIVE RECOGNITION MATRIX GENERATION")
        print("=" * 70)
        print(f"Anchor Question: '{tier2_prompt.question_text}'")
        for g in tier2_prompt.cue_groups:
            print(f"  Category: {g.category} -> Cues: {g.cues}")

        # Assert anchor question
        self.assertEqual(tier2_prompt.question_text.strip(), "Which feels familiar?")
        self.assertGreaterEqual(len(tier2_prompt.cue_groups), 2, "Must have at least 2 orthogonal cue groups")

        # Assert orthogonal categories
        categories = [g.category for g in tier2_prompt.cue_groups]
        self.assertTrue(any("setting" in c.lower() or "activity" in c.lower() for c in categories))
        self.assertTrue(any("social" in c.lower() or "atmosphere" in c.lower() for c in categories))

        # Flatten all cues
        all_cues = [c.lower() for g in tier2_prompt.cue_groups for c in g.cues]
        # Should include experiential recognition anchors
        has_venue_cue = any(v in all_cues for v in ["restaurant", "beach", "travel", "cafe", "café", "goa"])
        has_social_cue = any(s in all_cues for s in ["friends", "friend", "evening", "celebration", "casual"])
        self.assertTrue(has_venue_cue, "Must have venue/setting associative cues")
        self.assertTrue(has_social_cue, "Must have social/atmosphere associative cues")

    def test_03_refine_session_tier1_flow(self):
        """Test multi-turn Tier 1 refinement: user picks 'Beach Café'."""
        # 1. Create initial search
        search_res = self.api_client.post(
            "/api/search",
            json={"query": "small cafe in Goa with my friend"}
        )
        self.assertEqual(search_res.status_code, 200)
        session_id = search_res.json()["session_id"]

        # 2. Refine selecting "Beach Café"
        refine_payload = {
            "session_id": session_id,
            "selected_option_id": "opt_beach_cafe",
            "venue_type": "beach_cafe"
        }
        refine_res = self.api_client.post("/api/session/refine", json=refine_payload)
        self.assertEqual(refine_res.status_code, 200)
        data = refine_res.json()

        print("\n" + "=" * 70)
        print("TEST 03: REFINE SESSION (TIER 1 VENUE SELECTION)")
        print("=" * 70)
        print(f"Session ID: {data['session_id']}")
        print(f"Turn Count: {data['turn_count']}")
        print(f"Recovery Tier: {data['recovery_tier']}")
        print(f"Active Chips: {[c['label'] for c in data['chips']]}")
        print(f"Top Candidate: {data['candidates'][0]['filename']} ({data['candidates'][0]['score']})")

        self.assertEqual(data["turn_count"], 2)
        # Check that user_selected_tier_1 chip is present
        chip_statuses = [c["status"] for c in data["chips"]]
        self.assertIn("user_selected_tier_1", chip_statuses)

        # Candidates should be returned
        self.assertGreater(len(data["candidates"]), 0)

        # Verify escalation to Tier 2 if results remained ambiguous
        if data["recovery_tier"] == "tier_2_recognition":
            self.assertIsNotNone(data["recovery_prompt"], "Must include recovery_prompt when escalating to Tier 2")
            self.assertEqual(data["recovery_prompt"]["tier"], 2)
            self.assertEqual(data["recovery_prompt"]["question_text"], "Which feels familiar?")
            self.assertGreaterEqual(len(data["recovery_prompt"]["tier2"]["cue_groups"]), 2)

    def test_04_refine_session_tier2_cue_badges_flow(self):
        """Test multi-turn Tier 2 associative recognition: user taps ['Friends', 'Evening']."""
        # 1. Create a session
        search_res = self.api_client.post(
            "/api/search",
            json={"query": "That café in Goa with my friend"}
        )
        session_id = search_res.json()["session_id"]

        # 2. Refine with Tier 2 recognized cue badges
        refine_payload = {
            "session_id": session_id,
            "selected_cues": ["Friends", "Evening"]
        }
        refine_res = self.api_client.post("/api/session/refine", json=refine_payload)
        self.assertEqual(refine_res.status_code, 200)
        data = refine_res.json()

        print("\n" + "=" * 70)
        print("TEST 04: REFINE SESSION (TIER 2 RECOGNIZED CUE BADGES)")
        print("=" * 70)
        print(f"Turn Count: {data['turn_count']}")
        print(f"Top Candidate: {data['candidates'][0]['filename']}")
        print(f"Matched Cues: {data['candidates'][0]['matched_cues']}")

        # Verify Tier 2 chips were added
        chip_labels = [c["label"] for c in data["chips"]]
        self.assertTrue(any("Friends" in l for l in chip_labels))
        self.assertTrue(any("Evening" in l for l in chip_labels))

        # Target 1 should be prominently surfaced
        self.assertEqual(data["candidates"][0]["filename"], "IMG_GOA_CAFE_4021.jpg")

    def test_05_search_endpoint_with_recovery_prompt(self):
        """Test that /api/search attaches recovery_prompt when initial search confidence is weak."""
        search_res = self.api_client.post(
            "/api/search",
            json={"query": "That café in Goa with my friend"}
        )
        self.assertEqual(search_res.status_code, 200)
        data = search_res.json()

        # If weak confidence, Tier 1 prompt should be present
        if data["metrics"]["status"] == "WEAK_TIER_1":
            self.assertIsNotNone(data["recovery_prompt"])
            self.assertEqual(data["recovery_prompt"]["tier"], 1)
            self.assertTrue("restaurant" in data["recovery_prompt"]["question_text"].lower())

    def test_06_deterministic_offline_fallbacks(self):
        """Test that offline recover engine generates exact schemas without Groq."""
        offline_engine = RecoverEngine(api_key="")
        candidates = self._create_mock_ambiguous_candidates()

        t1 = offline_engine.generate_tier1_prompt(candidates, query="Goa cafe with friend")
        self.assertEqual(t1.question_text, "Was it a restaurant, beach café, or hotel?")
        self.assertEqual(len(t1.options), 3)
        self.assertEqual(t1.options[0].label, "Restaurant")
        self.assertEqual(t1.options[1].label, "Beach Café")
        self.assertEqual(t1.options[2].label, "Hotel")

        t2 = offline_engine.generate_tier2_prompt(candidates, query="Goa cafe with friend")
        self.assertEqual(t2.question_text, "Which feels familiar?")
        self.assertEqual(len(t2.cue_groups), 2)
        self.assertEqual(t2.cue_groups[0].cues, ["Restaurant", "Beach", "Travel"])
        self.assertEqual(t2.cue_groups[1].cues, ["Friends", "Evening", "Celebration"])

if __name__ == "__main__":
    unittest.main()
