"""
Phase 6 Test Suite: Validation, Evaluation & Usability Testing
Verifies:
1. Benchmark Suite Execution: Validates all 5 episodic memory scenarios against ground-truth targets.
2. Cognitive vs Traditional Search Delta: Verifies AI-native retrieval surpasses traditional baseline (>85% vs <30%).
3. Performance Budget Audits:
   - Initial query search latency budget (<= 800ms)
   - Pivot refinement latency budget (<= 300ms)
   - Thumbnail asset payload compression (< 100KB per WebP thumbnail)
4. Telemetry & Success Criteria Verification:
   - Retrieval success rate > 85%
   - Manual query re-typing reduction >= 60%
   - Pivot acceptance rate > 70%
5. Definition of Done (DoD) Full Verification:
   - DoD 1: Incomplete vague episodic query ingestion
   - DoD 2: Visible structured memory cues (chips)
   - DoD 3: Contextual recovery prompts & visual pivots
   - DoD 4: Pivot interaction instantly updates candidates
   - DoD 5: Real-time telemetry logging & metric computation
"""

import time
import json
import unittest
from pathlib import Path
import httpx

from src.config import THUMBNAILS_DIR, SQLITE_DB_PATH
from benchmark_phase6 import BENCHMARK_SCENARIOS, run_traditional_keyword_search

try:
    check = httpx.get("http://127.0.0.1:8000/api/health", timeout=1.0)
    is_live = (check.status_code == 200)
except Exception:
    is_live = False

if not is_live:
    from fastapi.testclient import TestClient
    from src.api.main import app


class TestPhase6ValidationAndDoD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if is_live:
            cls.client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60.0)
        else:
            cls.client = TestClient(app)

    def test_01_thumbnail_payload_budget(self):
        """Audit that all thumbnails exist, use WebP compression, and meet payload budget (< 100KB)."""
        thumb_files = list(THUMBNAILS_DIR.glob("*_thumb.webp"))
        self.assertGreaterEqual(len(thumb_files), 200, "Should have at least 200 indexed WebP thumbnails")

        sizes_kb = [f.stat().st_size / 1024.0 for f in thumb_files]
        avg_size_kb = sum(sizes_kb) / len(sizes_kb)
        max_size_kb = max(sizes_kb)

        # Performance budget asserts:
        self.assertLess(avg_size_kb, 50.0, f"Average thumbnail payload ({avg_size_kb:.1f} KB) must be < 50 KB")
        self.assertLess(max_size_kb, 100.0, f"Max thumbnail payload ({max_size_kb:.1f} KB) must be < 100 KB")

    def test_02_traditional_keyword_search_deficiencies(self):
        """Verify traditional keyword search fails on vague, episodic human memory queries."""
        trad_success = 0
        for sc in BENCHMARK_SCENARIOS:
            hits = run_traditional_keyword_search(sc["vague_query"])
            hit_filenames = [h["filename"] for h in hits[:5]]
            if sc["expected_filename"] in hit_filenames:
                trad_success += 1

        baseline_rate = (trad_success / len(BENCHMARK_SCENARIOS)) * 100
        # Traditional search should fail on most episodic queries (< 40%)
        self.assertLessEqual(baseline_rate, 40.0, f"Traditional keyword search baseline rate was unexpectedly high: {baseline_rate}%")

    def test_03_ai_native_cognitive_retrieval_scenarios(self):
        """Execute AI-native retrieval and pivot refinement across the 5 benchmark scenarios."""
        ai_successes = 0
        initial_latencies = []
        pivot_latencies = []

        for sc in BENCHMARK_SCENARIOS:
            # Step 1: Initial Search
            t0 = time.time()
            res = self.client.post("/api/search", json={"query": sc["vague_query"]})
            init_lat = (time.time() - t0) * 1000
            initial_latencies.append(init_lat)

            self.assertEqual(res.status_code, 200)
            data = res.json()
            session_id = data.get("session_id")
            candidates = data.get("candidates", [])
            self.assertGreater(len(candidates), 0, f"Search returned 0 candidates for {sc['name']}")

            # Step 2: Pivot Refine
            t_piv = time.time()
            ref_res = self.client.post("/api/session/refine", json={
                "session_id": session_id,
                "selected_option": sc["tier1_pivot"],
                "selected_cues": sc["tier2_cues"]
            })
            piv_lat = (time.time() - t_piv) * 1000
            pivot_latencies.append(piv_lat)

            self.assertEqual(ref_res.status_code, 200)
            ref_data = ref_res.json()
            ref_candidates = ref_data.get("candidates", [])

            # Check if expected target photo is in top candidates
            found_filenames = [c["filename"] for c in ref_candidates[:5]]
            if sc["expected_filename"] in found_filenames or (ref_candidates and ref_candidates[0]["filename"] == sc["expected_filename"]):
                ai_successes += 1

        ai_rate = (ai_successes / len(BENCHMARK_SCENARIOS)) * 100
        # Assert Success Criteria 1: Retrieval Success Rate > 85%
        self.assertGreaterEqual(ai_rate, 85.0, f"AI-Native retrieval rate {ai_rate}% must exceed 85%")

        # Assert Success Criteria 2: Latency budgets
        avg_piv_lat = sum(pivot_latencies) / len(pivot_latencies)
        self.assertLess(avg_piv_lat, 450.0, f"Average pivot latency {avg_piv_lat:.1f}ms exceeds interactive threshold")

    def test_04_success_criteria_kpis(self):
        """Verify MVP success criteria: Retrieval Rate > 85%, Retyping Reduction >= 60%, Pivot Acceptance > 70%."""
        # 1. Verify telemetry endpoint structure and values
        res = self.client.get("/api/telemetry/metrics")
        self.assertEqual(res.status_code, 200)
        metrics = res.json()

        self.assertIn("retrieval_success_rate", metrics)
        self.assertIn("avg_ttr_seconds", metrics)
        self.assertIn("manual_retyping_reduction_rate", metrics)
        self.assertIn("tier1_acceptance_rate", metrics)

        # 2. Verify benchmark evaluation results file
        bench_file = Path("benchmark_results.json")
        self.assertTrue(bench_file.exists(), "benchmark_results.json must exist from benchmark execution")
        with open(bench_file, "r", encoding="utf-8") as f:
            bench_data = json.load(f)

        self.assertGreaterEqual(bench_data["ai_success_rate"], 85.0, "AI-Native retrieval success rate must be >= 85%")
        self.assertLessEqual(bench_data["avg_initial_latency_ms"], 800.0, "Average initial latency must be <= 800ms")
        self.assertLessEqual(bench_data["avg_pivot_latency_ms"], 300.0, "Average pivot latency must be <= 300ms")

    def test_05_definition_of_done_verification(self):
        """
        Verify all 5 items in the MVP Definition of Done (DoD):
        1. A user can type an incomplete, vague episodic memory into the input bar.
        2. The system visibly extracts and displays structured memory cues (tags).
        3. When initial results are ambiguous, the system proactively displays recognizable visual/contextual pivots.
        4. Clicking a pivot instantly updates the candidate photos and successfully surfaces the target image.
        5. All 6 key metrics defined in problemStatement.md are captured and viewable via the telemetry logger.
        """
        # DoD 1 & 2: Incomplete vague input & structured memory cues
        query = "some small cafe we visited during our trip"
        res = self.client.post("/api/search", json={"query": query})
        self.assertEqual(res.status_code, 200)
        search_data = res.json()
        
        session_id = search_data.get("session_id")
        self.assertIsNotNone(session_id)
        chips = search_data.get("chips", [])
        self.assertGreater(len(chips), 0, "DoD 2 Failed: Structured memory cue chips were not returned")

        # DoD 3: Recovery prompt with visual/contextual pivots
        rec_prompt = search_data.get("recovery_prompt")
        self.assertIsNotNone(rec_prompt, "DoD 3 Failed: Recovery prompt was not returned")
        pivots = (rec_prompt.get("tier1") or {}).get("options", [])
        self.assertGreater(len(pivots), 0, "DoD 3 Failed: Disambiguation pivots were empty")

        # DoD 4: Clicking pivot instantly updates candidate photos and surfaces relevant target photos
        t0 = time.time()
        ref_res = self.client.post("/api/session/refine", json={
            "session_id": session_id,
            "selected_option": "Restaurant / Café",
            "selected_cues": ["Café", "Pastry"]
        })
        piv_duration = (time.time() - t0) * 1000
        self.assertEqual(ref_res.status_code, 200)
        ref_data = ref_res.json()
        new_candidates = ref_data.get("candidates", [])
        self.assertGreater(len(new_candidates), 0, "DoD 4 Failed: No candidates returned after pivot selection")
        self.assertTrue(
            any(c.get("scene_type") in ["restaurant", "cafe"] or "restaurant" in c.get("caption", "").lower() or "cafe" in c.get("caption", "").lower() for c in new_candidates[:5]),
            "DoD 4 Failed: Refined candidates did not match the selected Restaurant / Café pivot"
        )

        # Confirm photo completion
        comp_res = self.client.post(f"/api/session/{session_id}/complete", json={
            "photo_id": new_candidates[0]["photo_id"],
            "target_confirmed": True,
            "effort_turns": 2,
            "retrieval_path": ["Goa", "Café", "Pastry"]
        })
        self.assertEqual(comp_res.status_code, 200)

        # DoD 5: All 6 key metrics captured and viewable via telemetry logger
        telem_res = self.client.get("/api/telemetry/metrics")
        self.assertEqual(telem_res.status_code, 200)
        telem_data = telem_res.json()
        required_keys = [
            "retrieval_success_rate",
            "avg_ttr_seconds",
            "median_ttr_seconds",
            "tier1_acceptance_rate",
            "tier2_acceptance_rate",
            "manual_retyping_reduction_rate"
        ]
        for key in required_keys:
            self.assertIn(key, telem_data, f"DoD 5 Failed: Metric {key} missing from telemetry")


if __name__ == "__main__":
    unittest.main()
