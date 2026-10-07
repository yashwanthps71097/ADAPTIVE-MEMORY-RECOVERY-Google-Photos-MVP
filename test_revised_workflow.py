"""
Test Suite: Revised Adaptive Memory Recovery Workflow
Verifies:
1. Primary Journey:
   Memory Input -> AI extracts Goa/Friend/Café/Trip -> Initial Search (Weak/Ambiguous)
   -> Ask "Do you remember what kind of place it was?" -> User selects "Not sure"
   -> Recognition Mode ("Which feels familiar?") -> User selects "Restaurant"
   -> Updated Retrieval Path (Goa → Friend → Trip → Café → Restaurant)
   -> Search Again -> Target Photo Surfaced at #1 -> User Confirms "Found it".

2. Alternate Journey:
   Initial Search (Weak) -> Meaningful Question -> User answers "Restaurant / Café"
   -> Search Again -> Target Photo Surfaced at #1 -> Confirmed "Found it".
"""

import time
import unittest
import httpx

class TestRevisedWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

    def test_01_primary_demo_journey(self):
        """
        Tests Primary Demo Journey:
        Input -> Extract -> Weak Initial Search -> Tier 1 'Not sure'
        -> Tier 2 'Restaurant' -> Path Updated -> Target Photo Found.
        """
        # 1. User describes memory naturally
        query = "That small café we went to during our Goa trip with my friend."
        session_id = f"test_primary_{int(time.time())}"

        # 2. AI Understands & extracts cues + Initial Search
        res1 = self.client.post("/api/search", json={
            "query": query,
            "session_id": session_id
        })
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()

        # Verify extracted cues include Goa, Friend, Café, Trip
        chips = [c.get("label", "").lower() for c in data1.get("chips", [])]
        chip_str = " ".join(chips)
        self.assertTrue(any("goa" in c for c in chips) or "goa" in chip_str, "Should extract Goa")
        self.assertTrue(any("friend" in c for c in chips) or "friend" in chip_str, "Should extract Friend")
        self.assertTrue(any("caf" in c for c in chips) or "caf" in chip_str, "Should extract Café")

        # Verify initial results are weak / ambiguous (Tier 1 recovery attached)
        self.assertEqual(data1["metrics"]["status"], "WEAK_TIER_1")
        rec_prompt = data1.get("recovery_prompt")
        self.assertIsNotNone(rec_prompt)
        tier1_options = (rec_prompt.get("tier1") or {}).get("options", [])
        self.assertTrue(any("not sure" in o.get("label", "").lower() for o in tier1_options))

        # 3. User selects "Not sure" in Tier 1 -> Escalate to Tier 2 Recognition
        refine_res1 = self.client.post("/api/session/refine", json={
            "session_id": session_id,
            "selected_option": "Not sure"
        })
        self.assertEqual(refine_res1.status_code, 200)
        refine_data1 = refine_res1.json()

        # Verify Tier 2 recognition prompt returned
        self.assertEqual(refine_data1["recovery_tier"], "tier_2_recognition")
        t2_prompt = refine_data1.get("recovery_prompt")
        self.assertIsNotNone(t2_prompt)
        self.assertEqual(t2_prompt.get("question_text"), "Which feels familiar?")

        # 4. User recognizes clue "Restaurant" in Tier 2
        refine_res2 = self.client.post("/api/session/refine", json={
            "session_id": session_id,
            "selected_cues": ["Restaurant"],
            "recognized_cues": ["Restaurant"]
        })
        self.assertEqual(refine_res2.status_code, 200)
        refine_data2 = refine_res2.json()

        # 5. Search again -> Target photo IMG_GOA_CAFE_4021.jpg surfaces at #1!
        candidates = refine_data2.get("candidates", [])
        self.assertGreater(len(candidates), 0)
        self.assertEqual(candidates[0]["filename"], "IMG_GOA_CAFE_4021.jpg")
        self.assertGreaterEqual(candidates[0]["score"], 0.75)

        # 6. User confirms photo found -> Complete session
        comp_res = self.client.post(f"/api/session/{session_id}/complete", json={
            "photo_id": candidates[0]["photo_id"],
            "target_confirmed": True,
            "effort_turns": 3,
            "retrieval_path": ["Goa", "Friend", "Trip", "Café", "Restaurant"]
        })
        self.assertEqual(comp_res.status_code, 200)

    def test_02_alternate_demo_journey(self):
        """
        Tests Alternate Demo Journey:
        Input -> Extract -> Weak Initial Search -> User answers 'Restaurant / Café'
        -> Target Photo Found at #1.
        """
        query = "That small café we went to during our Goa trip with my friend."
        session_id = f"test_alt_{int(time.time())}"

        # 1. Initial Search
        res1 = self.client.post("/api/search", json={
            "query": query,
            "session_id": session_id
        })
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertEqual(data1["metrics"]["status"], "WEAK_TIER_1")

        # 2. User answers meaningful question: "Restaurant / Café"
        refine_res = self.client.post("/api/session/refine", json={
            "session_id": session_id,
            "selected_option": "Restaurant / Café"
        })
        self.assertEqual(refine_res.status_code, 200)
        refine_data = refine_res.json()

        # 3. Search Again -> Target photo IMG_GOA_CAFE_4021.jpg surfaces at #1!
        candidates = refine_data.get("candidates", [])
        self.assertGreater(len(candidates), 0)
        self.assertEqual(candidates[0]["filename"], "IMG_GOA_CAFE_4021.jpg")
        self.assertGreaterEqual(candidates[0]["score"], 0.75)

        # 4. User confirms photo found
        comp_res = self.client.post(f"/api/session/{session_id}/complete", json={
            "photo_id": candidates[0]["photo_id"],
            "target_confirmed": True,
            "effort_turns": 2,
            "retrieval_path": ["Goa", "Friend", "Trip", "Café", "Restaurant / Café"]
        })
        self.assertEqual(comp_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
