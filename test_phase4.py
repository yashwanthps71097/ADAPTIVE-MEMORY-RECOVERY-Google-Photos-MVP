"""
Phase 4 End-to-End Test Suite: Client UI, Static Assets & Scaffolding Flow
Verifies:
1. Root '/' serves index.html with correct semantic markup.
2. '/static/index.css' serves CSS tokens and styling.
3. '/static/app.js' serves the client controller.
4. '/api' and '/api/health' provide API status and collection metrics.
5. Search & Refine flow mimics the 8-step cognitive recovery journey.
6. Static photo and thumbnail assets are served properly.
"""

import sys
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

from src.config import SQLITE_DB_PATH

class TestPhase4ClientAndScaffolding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if is_live:
            cls.client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=10.0)
        else:
            cls.client = TestClient(app)

    def test_01_root_serves_html(self):
        """Test GET / returns 200 and the index.html page."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("Adaptive Memory Recovery", response.text)
        self.assertIn("Find a photo you remember", response.text)
        self.assertIn('id="app"', response.text)
        self.assertIn('id="step-1"', response.text)
        self.assertIn('id="step-7"', response.text)

    def test_02_static_css_served(self):
        """Test GET /static/index.css returns CSS design system tokens."""
        response = self.client.get("/static/index.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response.headers.get("content-type", ""))
        self.assertIn("--font-display", response.text)
        self.assertIn("theme-light", response.text)
        self.assertIn("theme-dark", response.text)

    def test_03_static_js_served(self):
        """Test GET /static/app.js returns the application controller script."""
        response = self.client.get("/static/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AdaptiveMemoryApp", response.text)
        self.assertIn("executeConnectSearch", response.text)
        self.assertIn("triggerRecoveryStep", response.text)

    def test_04_api_overview_and_health(self):
        """Test GET /api and GET /api/health."""
        api_res = self.client.get("/api")
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.json()
        self.assertIn("/api/search", api_data["endpoints"])
        self.assertIn("/api/session/refine", api_data["endpoints"])

        health_res = self.client.get("/api/health")
        self.assertEqual(health_res.status_code, 200)
        health_data = health_res.json()
        self.assertEqual(health_data["status"], "healthy")
        self.assertGreater(health_data["database_photos_count"], 0)

    def test_05_client_retrieval_flow(self):
        """Test full client retrieval flow from Step 1 search to Step 6 refinement."""
        query = "Goa café with my friend"
        search_res = self.client.post("/api/search", json={"query": query})
        self.assertEqual(search_res.status_code, 200)
        data = search_res.json()

        session_id = data["session_id"]
        self.assertTrue(session_id.startswith("sess_"))
        self.assertGreater(len(data["candidates"]), 0)
        self.assertGreater(len(data["chips"]), 0)
        self.assertIn("metrics", data)

        # Disambiguation / Refinement step
        refine_res = self.client.post("/api/session/refine", json={
            "session_id": session_id,
            "selected_option": "Restaurant",
            "recognized_cues": ["Restaurant"]
        })
        self.assertEqual(refine_res.status_code, 200)
        refine_data = refine_res.json()
        self.assertEqual(refine_data["session_id"], session_id)
        self.assertGreater(len(refine_data["candidates"]), 0)
        
        # Verify confirmed tier 1 setting chip was attached
        chip_labels = [c.get("label", "") + " " + c.get("value", "") for c in refine_data["chips"]]
        self.assertTrue(any("restaurant" in text.lower() for text in chip_labels))

    def test_06_thumbnails_mounted(self):
        """Test that photo thumbnail URLs are reachable through static mount."""
        # Using a cached or existing photo from search
        search_res = self.client.post("/api/search", json={"query": "Goa café with my friend"})
        self.assertEqual(search_res.status_code, 200)
        candidates = search_res.json()["candidates"]
        if candidates:
            thumb_url = candidates[0]["thumbnail_url"]
            res = self.client.get(thumb_url)
            self.assertEqual(res.status_code, 200)

if __name__ == "__main__":
    unittest.main()
