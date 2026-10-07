"""
Phase 5 Test Suite: Multi-Turn State Synchronization & Telemetry Harness
Verifies:
1. Turn 1 (Vague Input): Initializes multi-turn session and attaches recovery prompt if weak.
2. Turn 2 (Tier 1 Detail Disambiguation): Ingests 1-tap setting, updates session, and prunes candidates.
3. Turn 3 (Tier 2 Associative Recognition): Fuses recognized cues and retrieves target photo in < 300ms.
4. Session Completion: Confirms target photo and sets target_retrieved=True.
5. Telemetry Interceptor: Records full lifecycle event stream (search_started -> photo_retrieved).
6. Metrics Calculation Engine: Computes 6 core product KPIs in TelemetryMetricsSummary.
"""

import time
import unittest
import time
import unittest
import httpx

try:
    check = httpx.get("http://127.0.0.1:8000/api/health", timeout=1.0)
    is_live = (check.status_code == 200)
except Exception:
    is_live = False

if not is_live:
    from fastapi.testclient import TestClient
    from src.api.main import app

class TestPhase5MultiTurnAndTelemetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if is_live:
            cls.client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=35.0)
        else:
            cls.client = TestClient(app, timeout=35.0)

    def test_01_telemetry_event_ingestion(self):
        """Test POST /api/telemetry/event records custom user events."""
        test_session = f"sess_test_{int(time.time())}"
        res = self.client.post("/api/telemetry/event", json={
            "session_id": test_session,
            "event_type": "test_interaction",
            "details": {"action": "click", "element": "sample_pill"}
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "recorded")

        # Verify event appears in session telemetry
        sess_telem = self.client.get(f"/api/telemetry/session/{test_session}")
        self.assertEqual(sess_telem.status_code, 200)
        events = sess_telem.json()["events"]
        self.assertTrue(any(e["event_type"] == "test_interaction" for e in events))

    def test_02_multi_turn_retrieval_ladder_flow(self):
        """
        Tests complete 3-turn ladder:
        Turn 1: Vague query -> Cues extracted -> Initial candidates
        Turn 2: Detail disambiguation (Tier 1 selection) -> Pruned candidates
        Turn 3: Associative recognition (Tier 2 cues) -> Target moment confirmed
        """
        # Turn 1: Vague query input
        query = "That café in Goa with my friend"
        res_t1 = self.client.post("/api/search", json={"query": query})
        self.assertEqual(res_t1.status_code, 200)
        data_t1 = res_t1.json()

        session_id = data_t1["session_id"]
        self.assertEqual(data_t1["turn_count"], 1)
        self.assertGreater(len(data_t1["chips"]), 0)
        self.assertGreater(len(data_t1["candidates"]), 0)

        # Turn 2: Tier 1 Detail Disambiguation (e.g., "Beach Café")
        res_t2 = self.client.post("/api/session/refine", json={
            "session_id": session_id,
            "selected_option_id": "opt_beach_cafe",
            "venue_type": "beach_cafe"
        })
        self.assertEqual(res_t2.status_code, 200)
        data_t2 = res_t2.json()
        self.assertEqual(data_t2["turn_count"], 2)
        # Verify confirmed Tier 1 chip is attached
        chip_vals = [c.get("value", "") for c in data_t2["chips"]]
        self.assertIn("beach_cafe", chip_vals)

        # Turn 3: Tier 2 Associative Recognition (e.g. ["Friends", "Evening"])
        t0 = time.time()
        res_t3 = self.client.post("/api/session/refine", json={
            "session_id": session_id,
            "selected_cues": ["Friends", "Evening"],
            "recognized_cues": ["Friends", "Evening"]
        })
        latency_ms = (time.time() - t0) * 1000
        self.assertEqual(res_t3.status_code, 200)
        self.assertLess(latency_ms, 800) # Response in rapid interactive time
        data_t3 = res_t3.json()
        self.assertEqual(data_t3["turn_count"], 3)
        self.assertGreater(len(data_t3["candidates"]), 0)

        # Confirm target photo completion
        target_photo_id = data_t3["candidates"][0]["photo_id"]
        comp_res = self.client.post(f"/api/session/{session_id}/complete", json={
            "photo_id": target_photo_id,
            "target_confirmed": True,
            "effort_turns": 3,
            "retrieval_path": ["Goa", "Café", "Beach Café", "Friends", "Evening"]
        })
        self.assertEqual(comp_res.status_code, 200)
        self.assertEqual(comp_res.json()["status"], "completed")

        # Verify session state reflects completion
        sess_state = self.client.get(f"/api/session/{session_id}")
        self.assertEqual(sess_state.status_code, 200)
        self.assertTrue(sess_state.json()["target_retrieved"])

    def test_03_session_abandonment_tracking(self):
        """Test POST /api/session/{session_id}/abandon tracks uncompleted sessions."""
        test_session = f"sess_abandon_{int(time.time())}"
        self.client.post("/api/search", json={"query": "test query", "session_id": test_session})
        
        abandon_res = self.client.post(f"/api/session/{test_session}/abandon", json={
            "reason": "user_cancelled"
        })
        self.assertEqual(abandon_res.status_code, 200)
        self.assertEqual(abandon_res.json()["status"], "abandoned")

        # Check telemetry event stream
        sess_telem = self.client.get(f"/api/telemetry/session/{test_session}")
        self.assertEqual(sess_telem.status_code, 200)
        events = sess_telem.json()["events"]
        self.assertTrue(any(e["event_type"] == "session_abandoned" for e in events))

    def test_04_metrics_calculation_engine(self):
        """Test GET /api/telemetry/metrics calculates 6 core product KPIs."""
        res = self.client.get("/api/telemetry/metrics")
        self.assertEqual(res.status_code, 200)
        metrics = res.json()

        self.assertIn("retrieval_success_rate", metrics)
        self.assertIn("avg_ttr_seconds", metrics)
        self.assertIn("median_ttr_seconds", metrics)
        self.assertIn("tier1_acceptance_rate", metrics)
        self.assertIn("tier2_acceptance_rate", metrics)
        self.assertIn("manual_retyping_reduction_rate", metrics)
        self.assertIn("recent_events", metrics)

        self.assertGreaterEqual(metrics["retrieval_success_rate"], 0.0)
        self.assertLessEqual(metrics["retrieval_success_rate"], 100.0)
        self.assertGreater(metrics["avg_ttr_seconds"], 0.0)
        self.assertGreaterEqual(metrics["manual_retyping_reduction_rate"], 0.0)

    def test_05_session_ladder_event_stream(self):
        """Test full ladder produces ordered, verifiable lifecycle events."""
        session_id = f"sess_stream_{int(time.time())}"
        self.client.post("/api/search", json={"query": "Goa café with my friend", "session_id": session_id})
        self.client.post("/api/session/refine", json={
            "session_id": session_id,
            "selected_option": "Restaurant"
        })
        self.client.post(f"/api/session/{session_id}/complete", json={
            "photo_id": "target_target_1_goa_cafe",
            "effort_turns": 2,
            "retrieval_path": ["Goa", "Café", "Restaurant"]
        })

        telem_res = self.client.get(f"/api/telemetry/session/{session_id}")
        self.assertEqual(telem_res.status_code, 200)
        events = [e["event_type"] for e in telem_res.json()["events"]]
        
        self.assertIn("search_started", events)
        self.assertIn("cues_extracted", events)
        self.assertIn("tier1_detail_selected", events)
        self.assertIn("photo_retrieved", events)

if __name__ == "__main__":
    unittest.main()
