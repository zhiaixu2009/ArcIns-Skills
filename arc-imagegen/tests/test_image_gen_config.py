import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "image_gen.py"


def load_image_gen():
    spec = importlib.util.spec_from_file_location("arc_image_gen", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ImageGenConfigTests(unittest.TestCase):
    def setUp(self):
        self.image_gen = load_image_gen()

    def test_loads_toml_config_regardless_of_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "doc.md"
            config_path.write_text(
                'base_url = "https://sub-api.example.com"\n'
                'api_key = "sk-test"\n'
                'default_model = "gpt-image-2"\n'
                'timeout_seconds = 123\n',
                encoding="utf-8",
            )

            config = self.image_gen._load_api_config(str(config_path))

        self.assertEqual(config.base_url, "https://sub-api.example.com/v1")
        self.assertEqual(config.api_key, "sk-test")
        self.assertEqual(config.default_model, "gpt-image-2")
        self.assertEqual(config.timeout_seconds, 123.0)

    def test_normalizes_existing_v1_base_url_without_duplication(self):
        result = self.image_gen._normalize_base_url("https://sub-api.example.com/v1/")

        self.assertEqual(result, "https://sub-api.example.com/v1")

    def test_default_config_path_is_skill_root_config_json(self):
        skill_root = SCRIPT_PATH.parents[1]

        self.assertEqual(self.image_gen.DEFAULT_SKILL_ROOT, skill_root)
        self.assertEqual(self.image_gen.DEFAULT_CONFIG_PATH, skill_root / "config.json")

    def test_default_output_paths_live_under_skill_root_output(self):
        skill_root = SCRIPT_PATH.parents[1]

        self.assertEqual(self.image_gen.DEFAULT_OUTPUT_DIR, skill_root / "output")
        self.assertEqual(
            Path(self.image_gen.DEFAULT_OUTPUT_PATH),
            skill_root / "output" / "output.png",
        )
        self.assertEqual(
            self.image_gen.DEFAULT_BATCH_OUTPUT_DIR,
            skill_root / "output" / "batch",
        )

    def test_environment_overrides_file_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                '{"base_url":"https://file.example.com","api_key":"sk-file","default_model":"gpt-image-1","timeout_seconds":111}',
                encoding="utf-8",
            )
            env = {
                "ARC_IMAGEGEN_BASE_URL": "https://env.example.com/v1/",
                "ARC_IMAGEGEN_API_KEY": "sk-env",
                "ARC_IMAGEGEN_DEFAULT_MODEL": "gpt-image-2",
                "ARC_IMAGEGEN_TIMEOUT_SECONDS": "222",
            }
            with patch.dict(os.environ, env, clear=False):
                config = self.image_gen._load_api_config(str(config_path))

        self.assertEqual(config.base_url, "https://env.example.com/v1")
        self.assertEqual(config.api_key, "sk-env")
        self.assertEqual(config.default_model, "gpt-image-2")
        self.assertEqual(config.timeout_seconds, 222.0)

    def test_dry_run_allows_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            config = self.image_gen._resolve_api_config(
                config_path=None,
                dry_run=True,
                default_model="gpt-image-2",
            )

        self.assertEqual(config.base_url, "https://api.openai.com/v1")
        self.assertEqual(config.api_key, "")
        self.assertEqual(config.default_model, "gpt-image-2")

    def test_api_error_message_redacts_configured_secret(self):
        config = self.image_gen.APIConfig(
            base_url="https://sub-api.example.com/v1",
            api_key="sk-secret",
            default_model="gpt-image-2",
            timeout_seconds=300,
        )
        error = RuntimeError("request failed for sk-secret")

        message = self.image_gen._safe_api_error_message(error, config)

        self.assertNotIn("sk-secret", message)
        self.assertIn("[redacted]", message)

    def test_generation_http_request_uses_clean_compatible_headers(self):
        config = self.image_gen.APIConfig(
            base_url="https://sub-api.example.com/v1",
            api_key="sk-test",
            default_model="gpt-image-2",
            timeout_seconds=10,
        )
        payload = {
            "model": "gpt-image-2",
            "prompt": "a blue circle",
            "size": "1024x1024",
            "quality": "low",
            "output_format": "png",
        }
        captured = {}

        def handler(request):
            captured["request"] = request
            return httpx.Response(200, json={"data": [{"b64_json": "aW1hZ2U="}]})

        response = self.image_gen._post_json_api(
            config,
            "/images/generations",
            payload,
            transport=httpx.MockTransport(handler),
        )

        request = captured["request"]
        self.assertEqual(str(request.url), "https://sub-api.example.com/v1/images/generations")
        self.assertEqual(request.headers["authorization"], "Bearer sk-test")
        self.assertEqual(request.headers["user-agent"], "arc-imagegen/1.0")
        self.assertEqual(request.headers["content-type"], "application/json")
        self.assertNotIn("OpenAI/Python", request.headers["user-agent"])
        self.assertFalse(any(name.lower().startswith("x-stainless") for name in request.headers))
        self.assertEqual(self.image_gen._extract_b64_images(response), ["aW1hZ2U="])

    def test_edit_http_request_uses_multipart_without_sdk_headers(self):
        config = self.image_gen.APIConfig(
            base_url="https://sub-api.example.com/v1",
            api_key="sk-test",
            default_model="gpt-image-2",
            timeout_seconds=10,
        )
        payload = {
            "model": "gpt-image-2",
            "prompt": "change the background",
            "size": "1024x1024",
            "quality": "low",
            "output_format": "png",
        }
        captured = {}

        def handler(request):
            captured["request"] = request
            return httpx.Response(200, json={"data": [{"b64_json": "ZWRpdA=="}]})

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "input.png"
            image_path.write_bytes(b"not-a-real-png-for-request-shape")

            response = self.image_gen._post_edit_api(
                config,
                payload,
                [image_path],
                None,
                transport=httpx.MockTransport(handler),
            )

        request = captured["request"]
        self.assertEqual(str(request.url), "https://sub-api.example.com/v1/images/edits")
        self.assertEqual(request.headers["authorization"], "Bearer sk-test")
        self.assertEqual(request.headers["user-agent"], "arc-imagegen/1.0")
        self.assertIn("multipart/form-data", request.headers["content-type"])
        self.assertNotIn("OpenAI/Python", request.headers["user-agent"])
        self.assertFalse(any(name.lower().startswith("x-stainless") for name in request.headers))
        self.assertEqual(self.image_gen._extract_b64_images(response), ["ZWRpdA=="])


if __name__ == "__main__":
    unittest.main()
