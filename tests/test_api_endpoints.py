import unittest
from fastapi.testclient import TestClient
from backend.main import app, state

class TestApiEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("whisper_ready", data)
        self.assertIn("ollama_connected", data)
        self.assertIn("audio_devices", data)
        self.assertIn("stats", data)

    def test_stats_endpoint(self):
        response = self.client.get("/api/stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_transcriptions", data)
        self.assertIn("total_words", data)
        self.assertIn("total_duration_seconds", data)

    def test_audio_devices_endpoint(self):
        response = self.client.get("/api/audio-devices")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("devices", data)
        self.assertIn("default_name", data)

    def test_history_endpoint(self):
        response = self.client.get("/api/history?limit=5&offset=0")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_config_endpoints(self):
        # 1. GET config
        get_res = self.client.get("/api/config")
        self.assertEqual(get_res.status_code, 200)
        initial_cfg = get_res.json()
        self.assertIn("whisper_model", initial_cfg)
        self.assertIn("llm_cleanup_enabled", initial_cfg)

        # 2. POST update config
        update_payload = {
            "dictation_mode": "code",
            "llm_cleanup_enabled": False,
        }
        post_res = self.client.post("/api/config", json=update_payload)
        self.assertEqual(post_res.status_code, 200)
        updated_cfg = post_res.json()
        self.assertEqual(updated_cfg["dictation_mode"], "code")
        self.assertEqual(updated_cfg["llm_cleanup_enabled"], False)

        # Revert back to original
        self.client.post("/api/config", json={
            "dictation_mode": initial_cfg.get("dictation_mode", "auto"),
            "llm_cleanup_enabled": initial_cfg.get("llm_cleanup_enabled", True),
        })

if __name__ == "__main__":
    unittest.main()
