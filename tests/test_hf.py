"""Offline tests: every API call is faked, nothing is charged."""
import json
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import hf  # noqa: E402

RID = "0f8c2d1e-4b6a-4c3d-9e8f-1a2b3c4d5e6f"
PRICING_TEXT = ("Token-metered pricing. Billable video tokens = ceil(...). "
                "At 480p or 720p, each 1,000 video tokens cost $0.0214. Rates shown are before any discount.")
REQUEST = {"prompt": "A calm lake at dawn", "duration": 4}


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.submit_reply = {"status": "queued", "request_id": RID,
                             "status_url": f"https://platform.higgsfield.ai/requests/{RID}/status"}
        self.statuses = ["in_progress", "completed"]
        self.estimate_reply = {"type": "description", "pricing_description": PRICING_TEXT}

    def __call__(self, method, path, body=None, timeout=60):
        self.calls.append((method, path))
        if path.startswith("/estimate/"):
            return self.estimate_reply
        if path.endswith("/status"):
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            reply = {"status": status, "request_id": RID}
            if status == "completed":
                reply["video"] = {"url": "https://cdn.example.com/v.mp4"}
            return reply
        if isinstance(self.submit_reply, Exception):
            raise self.submit_reply
        return self.submit_reply


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = hf.Store(Path(self.tmp.name) / "state")
        self.spec = hf.load_model("bytedance-seedance-2.5-text-to-video")
        self.api = FakeAPI()
        patcher = mock.patch.object(hf, "http", self.api)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.store.db.close)


class PricingTests(Base):
    def test_seedance_price_from_description(self):
        price = lambda p: hf.video_token_price(self.spec, {"prompt": "x", **p}, PRICING_TEXT)[0]
        self.assertEqual(price({"duration": 5}), Decimal("2.3112"))
        self.assertEqual(price({"duration": 4}), Decimal("1.8490"))
        self.assertEqual(price({"duration": 10, "resolution": "480p", "aspect_ratio": "9:16"}), Decimal("0.6500"))

    def test_image_to_video_uses_upper_bound(self):
        spec = hf.load_model("bytedance-seedance-2.5-image-to-video")
        price, source = hf.video_token_price(spec, {"duration": 5}, PRICING_TEXT)
        self.assertGreater(price, Decimal("2.3112"))
        self.assertIn("upper bound", source)

    def test_wan_per_second_price(self):
        spec = hf.load_model("alibaba-wan-3.0-text-to-video")
        text = "Priced per generated second by resolution: 480p $0.05, 720p $0.10, or 1080p $0.20."
        self.assertEqual(hf.per_second_price(spec, {"prompt": "x", "duration": 5, "resolution": "720p"}, text)[0],
                         Decimal("0.5000"))

    def test_unpriced_model_needs_flag(self):
        spec = hf.load_model("bytedance-seedance-2.0-text-to-video")
        self.api.estimate_reply = {"type": "description", "pricing_description": "Token-metered pricing."}
        with self.assertRaises(hf.UnpricedError):
            hf.submit(self.store, spec, {"prompt": "x"}, "u1")
        job = hf.submit(self.store, spec, {"prompt": "x"}, "u1", allow_unpriced=True)
        self.assertIsNone(job["estimate_usd"])

    def test_changed_pricing_text_stops(self):
        with self.assertRaises(hf.HFError):
            hf.video_token_price(self.spec, REQUEST, "A brand new pricing format")

    def test_usd_reply_is_used_directly(self):
        self.api.estimate_reply = {"credits": "1.5", "usd": "0.094"}
        self.assertEqual(hf.estimate(self.spec, REQUEST), (Decimal("0.094"), "api"))


class ValidationTests(Base):
    def test_rejects_bad_values(self):
        for bad in ({}, {"prompt": ""}, {"prompt": "x", "duration": 3}, {"prompt": "x", "resolution": "1080p"},
                    {"prompt": "x", "duration": True}, {"prompt": "x", "seed": 1}):
            with self.subTest(bad=bad), self.assertRaises(hf.HFError):
                hf.validate(self.spec, bad)

    def test_accepts_good_request(self):
        self.assertEqual(hf.validate(self.spec, REQUEST), REQUEST)

    def test_conditional_and_array_rules(self):
        spec = hf.load_model("bytedance-seedance-2.0-reference-to-video")
        with self.assertRaises(hf.HFError):
            hf.validate(spec, {"prompt": "x"})  # needs image_urls or video_urls
        hf.validate(spec, {"prompt": "x", "video_urls": ["https://cdn.example.com/a.mp4"]})
        with self.assertRaises(hf.HFError):
            hf.validate(spec, {"prompt": "x", "video_urls": ["C:/local/file.mp4"]})

    def test_every_bundled_model_loads(self):
        rows = hf.list_models()
        self.assertGreaterEqual(len(rows), 79)
        for row in rows:
            spec = hf.load_model(row["model"])
            if "properties" in spec["input_schema"]:
                self.assertEqual(spec["input_schema"].get("type"), "object")
            else:
                with self.assertRaises(hf.HFError):
                    hf.validate(spec, {})

    def test_model_lookup_by_endpoint(self):
        self.assertEqual(hf.load_model("kling-video/v3.0/pro/text-to-video")["id"], "kling-video-v3.0-pro-text-to-video")


class JobTests(Base):
    def test_request_id_saved_even_with_foreign_status_url(self):
        job = hf.submit(self.store, self.spec, REQUEST, "shot-1")
        self.assertEqual(job["request_id"], RID)
        self.assertEqual(job["status"], "queued")
        hf.refresh(self.store, "shot-1")
        # Polling goes to the documented API path, never to the host in the reply.
        self.assertIn(("GET", f"/requests/{RID}/status"), self.api.calls)

    def test_same_job_name_never_charges_twice(self):
        hf.submit(self.store, self.spec, REQUEST, "shot-1")
        hf.submit(self.store, self.spec, REQUEST, "shot-1")
        self.assertEqual(sum(1 for m, p in self.api.calls if m == "POST" and not p.startswith("/estimate")), 1)

    def test_job_name_reuse_with_new_request_refused(self):
        hf.submit(self.store, self.spec, REQUEST, "shot-1")
        with self.assertRaises(hf.HFError):
            hf.submit(self.store, self.spec, {**REQUEST, "prompt": "Other"}, "shot-1")

    def test_identical_request_under_new_name_needs_flag(self):
        hf.submit(self.store, self.spec, REQUEST, "shot-1")
        with self.assertRaises(hf.HFError):
            hf.submit(self.store, self.spec, REQUEST, "shot-2")
        hf.submit(self.store, self.spec, REQUEST, "shot-2", allow_duplicate=True)

    def test_network_failure_marks_unknown_not_retried(self):
        self.api.submit_reply = hf.HFError("Network error")
        with self.assertRaises(hf.HFError):
            hf.submit(self.store, self.spec, REQUEST, "shot-1")
        self.assertEqual(self.store.get("shot-1")["status"], "unknown")

    def test_http_422_marks_rejected(self):
        self.api.submit_reply = hf.HFError("HTTP 422", http_status=422)
        with self.assertRaises(hf.HFError):
            hf.submit(self.store, self.spec, REQUEST, "shot-1")
        self.assertEqual(self.store.get("shot-1")["status"], "rejected")

    def test_max_usd_blocks_before_submit(self):
        with self.assertRaises(hf.HFError):
            hf.submit(self.store, self.spec, REQUEST, "shot-1", max_usd="1.00")
        self.assertIsNone(self.store.get("shot-1"))

    def test_budget_group(self):
        hf.submit(self.store, self.spec, REQUEST, "a", budget="b1", budget_usd="3")
        with self.assertRaises(hf.HFError):
            hf.submit(self.store, self.spec, {**REQUEST, "prompt": "two"}, "b", budget="b1", budget_usd="3")
        with self.assertRaises(hf.HFError):
            hf.submit(self.store, self.spec, {**REQUEST, "prompt": "two"}, "c", budget="b1", budget_usd="5")

    def test_wait_and_output_urls(self):
        hf.submit(self.store, self.spec, REQUEST, "shot-1")
        with mock.patch.object(hf.time, "sleep"):
            job = hf.wait(self.store, "shot-1", timeout=60)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(hf.output_urls(json.loads(job["response"])), ["https://cdn.example.com/v.mp4"])

    def test_attach_recovers_lost_job(self):
        job = hf.attach(self.store, "recovered", RID.upper(), model="bytedance/seedance-2.5/text-to-video")
        self.assertEqual(job["request_id"], RID)
        with self.assertRaises(hf.HFError):
            hf.attach(self.store, "x", "not-a-uuid")


class CredentialTests(unittest.TestCase):
    def test_env_file_is_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "creds.env"
            path.write_text('# keys\nHF_API_KEY_ID="abc"\nexport HF_API_KEY_SECRET=def\n', encoding="utf-8")
            env = {"HIGGSFIELD_ENV_FILE": str(path)}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(hf.credentials(), ("abc", "def"))

    def test_environment_wins(self):
        with mock.patch.dict(os.environ, {"HF_API_KEY_ID": "id1", "HF_API_KEY_SECRET": "s1",
                                          "HIGGSFIELD_ENV_FILE": "missing.env"}, clear=True):
            self.assertEqual(hf.credentials(), ("id1", "s1"))

    def test_missing_credentials_error(self):
        with mock.patch.dict(os.environ, {"HIGGSFIELD_ENV_FILE": "missing.env"}, clear=True):
            with self.assertRaises(hf.HFError):
                hf.credentials()

    def test_non_api_path_refused(self):
        with self.assertRaises(hf.HFError):
            hf.http("GET", "https://evil.example/steal")


class CliTests(unittest.TestCase):
    def test_validate_command(self):
        code = hf.main(["validate", "--model", "bytedance-seedance-2.5-text-to-video", "--json", json.dumps(REQUEST)])
        self.assertEqual(code, 0)

    def test_models_command(self):
        self.assertEqual(hf.main(["models"]), 0)


if __name__ == "__main__":
    unittest.main()
