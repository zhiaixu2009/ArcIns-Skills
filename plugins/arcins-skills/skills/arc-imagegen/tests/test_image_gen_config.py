import importlib.util
import asyncio
import json
import os
from pathlib import Path
import subprocess
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


def find_plugin_root() -> Path:
    for parent in [SCRIPT_PATH.parent, *SCRIPT_PATH.parents]:
        if (parent / ".codex-plugin" / "plugin.json").exists():
            return parent
    raise AssertionError("arcins-skills plugin root was not found")


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
        with tempfile.TemporaryDirectory() as tmp:
            missing_config = Path(tmp) / "missing-config.json"
            with patch.dict(os.environ, {}, clear=True), patch.object(
                self.image_gen, "DEFAULT_CONFIG_PATH", missing_config
            ):
                config = self.image_gen._resolve_api_config(
                    config_path=None,
                    dry_run=True,
                    default_model="gpt-image-2",
                )

        self.assertEqual(config.base_url, "https://api.openai.com/v1")
        self.assertEqual(config.api_key, "")
        self.assertEqual(config.default_model, "gpt-image-2")

    def test_loads_config_from_codex_home_before_skill_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex-home"
            user_config = codex_home / "arc-imagegen" / "config.json"
            user_config.parent.mkdir(parents=True)
            user_config.write_text(
                json.dumps(
                    {
                        "base_url": "https://codex-home.example.com",
                        "api_key": "sk-codex-home",
                        "default_model": "gpt-image-2",
                        "timeout_seconds": 123,
                    }
                ),
                encoding="utf-8",
            )
            skill_config = Path(tmp) / "skill-config.json"
            skill_config.write_text(
                json.dumps(
                    {
                        "base_url": "https://skill-root.example.com",
                        "api_key": "sk-skill-root",
                        "default_model": "gpt-image-1",
                        "timeout_seconds": 456,
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=True), patch.object(
                self.image_gen, "DEFAULT_CONFIG_PATH", skill_config
            ):
                config = self.image_gen._load_api_config(None)

        self.assertEqual(config.base_url, "https://codex-home.example.com/v1")
        self.assertEqual(config.api_key, "sk-codex-home")
        self.assertEqual(config.default_model, "gpt-image-2")
        self.assertEqual(config.timeout_seconds, 123.0)

    def test_loads_config_from_default_user_codex_home_when_codex_home_unset(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            user_config = home / ".codex" / "arc-imagegen" / "config.json"
            user_config.parent.mkdir(parents=True)
            user_config.write_text(
                json.dumps(
                    {
                        "base_url": "https://user-home.example.com",
                        "api_key": "sk-user-home",
                        "default_model": "gpt-image-2",
                        "timeout_seconds": 234,
                    }
                ),
                encoding="utf-8",
            )
            skill_config = Path(tmp) / "skill-config.json"
            skill_config.write_text(
                json.dumps(
                    {
                        "base_url": "https://skill-root.example.com",
                        "api_key": "sk-skill-root",
                        "default_model": "gpt-image-1",
                        "timeout_seconds": 456,
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True), patch.object(
                self.image_gen.Path, "home", return_value=home
            ), patch.object(self.image_gen, "DEFAULT_CONFIG_PATH", skill_config):
                config = self.image_gen._load_api_config(None)

        self.assertEqual(config.base_url, "https://user-home.example.com/v1")
        self.assertEqual(config.api_key, "sk-user-home")
        self.assertEqual(config.default_model, "gpt-image-2")
        self.assertEqual(config.timeout_seconds, 234.0)

    def test_setup_script_writes_codex_home_config_without_leaking_key(self):
        plugin_root = find_plugin_root()
        setup_script = plugin_root / "scripts" / "setup-arc-imagegen-config.py"
        secret = "sk-test-secret-no-leak"

        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "CODEX_HOME": str(Path(tmp) / "codex-home")}
            result = subprocess.run(
                [
                    sys.executable,
                    str(setup_script),
                    "--base-url",
                    "https://sub-api.example.com",
                    "--api-key",
                    secret,
                    "--default-model",
                    "gpt-image-2",
                    "--timeout-seconds",
                    "321",
                    "--force",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            config_path = Path(env["CODEX_HOME"]) / "arc-imagegen" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))

        combined_output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertNotIn(secret, combined_output)
        self.assertNotIn("https://sub-api.example.com", combined_output)
        self.assertIn("base_url: [configured]", combined_output)
        self.assertEqual(config["base_url"], "https://sub-api.example.com")
        self.assertEqual(config["api_key"], secret)
        self.assertEqual(config["default_model"], "gpt-image-2")
        self.assertEqual(config["timeout_seconds"], 321.0)

    def test_setup_script_requires_explicit_base_url(self):
        plugin_root = find_plugin_root()
        setup_script = plugin_root / "scripts" / "setup-arc-imagegen-config.py"

        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "CODEX_HOME": str(Path(tmp) / "codex-home")}
            result = subprocess.run(
                [
                    sys.executable,
                    str(setup_script),
                    "--api-key",
                    "test-placeholder-key",
                    "--force",
                ],
                input="",
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            config_path = Path(env["CODEX_HOME"]) / "arc-imagegen" / "config.json"
            config_exists = config_path.exists()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("base_url is required", result.stderr)
        self.assertFalse(config_exists)

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

    def test_generation_stream_request_uses_event_stream_accept_header(self):
        config = self.image_gen.APIConfig(
            base_url="https://sub-api.example.com/v1",
            api_key="sk-test",
            default_model="gpt-image-2",
            timeout_seconds=10,
        )
        payload = {
            "model": "gpt-image-2",
            "prompt": "a blue circle",
            "stream": True,
            "response_format": "b64_json",
        }
        captured = {}

        def handler(request):
            captured["request"] = request
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text='data: {"type":"image_generation.completed","b64_json":"ZmluYWw="}\n\n',
            )

        response = self.image_gen._post_json_api(
            config,
            "/images/generations",
            payload,
            transport=httpx.MockTransport(handler),
        )

        request = captured["request"]
        self.assertEqual(request.headers["accept"], "text/event-stream")
        self.assertEqual(self.image_gen._extract_b64_images(response), ["ZmluYWw="])

    def test_generation_stream_dry_run_includes_stream_payload(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "generate",
                "--prompt",
                "a blue circle",
                "--stream",
                "--dry-run",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        request = json.loads(result.stdout)
        self.assertTrue(request["stream"])
        self.assertEqual(request["response_format"], "b64_json")

    def test_generation_dry_run_forces_stream_payload(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "generate",
                "--prompt",
                "a blue circle",
                "--dry-run",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        request = json.loads(result.stdout)
        self.assertTrue(request["stream"])
        self.assertEqual(request["response_format"], "b64_json")

    def test_batch_dry_run_forces_stream_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "jobs.jsonl"
            input_path.write_text('{"prompt":"a blue circle"}\n', encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "generate-batch",
                    "--input",
                    str(input_path),
                    "--dry-run",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        request = json.loads(result.stdout)
        self.assertTrue(request["stream"])
        self.assertEqual(request["response_format"], "b64_json")

    def test_edit_dry_run_forces_stream_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "input.png"
            image_path.write_bytes(b"not-a-real-png-for-dry-run")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "edit",
                    "--image",
                    str(image_path),
                    "--prompt",
                    "change the background",
                    "--dry-run",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        request = json.loads(result.stdout)
        self.assertTrue(request["stream"])
        self.assertEqual(request["response_format"], "b64_json")

    def test_generation_stream_response_extracts_completed_image(self):
        config = self.image_gen.APIConfig(
            base_url="https://sub-api.example.com/v1",
            api_key="sk-test",
            default_model="gpt-image-2",
            timeout_seconds=10,
        )
        payload = {
            "model": "gpt-image-2",
            "prompt": "a blue circle",
            "stream": True,
            "response_format": "b64_json",
        }
        captured = {}
        stream_body = (
            ":\n\n"
            "event: image_generation.partial_image\n"
            'data: {"type":"image_generation.partial_image","b64_json":"cGFydGlhbA=="}\n\n'
            "event: image_generation.completed\n"
            'data: {"type":"image_generation.completed","b64_json":"ZmluYWw="}\n\n'
            "data: [DONE]\n\n"
        )

        def handler(request):
            captured["request"] = request
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=stream_body,
            )

        response = self.image_gen._post_json_api(
            config,
            "/images/generations",
            payload,
            transport=httpx.MockTransport(handler),
        )

        request = captured["request"]
        sent_payload = json.loads(request.content)
        self.assertTrue(sent_payload["stream"])
        self.assertEqual(sent_payload["response_format"], "b64_json")
        self.assertEqual(self.image_gen._extract_b64_images(response), ["ZmluYWw="])

    def test_batch_default_max_attempts_is_one_retry(self):
        self.assertEqual(self.image_gen.DEFAULT_BATCH_MAX_ATTEMPTS, 2)

    def test_retry_happens_immediately_without_backoff_sleep(self):
        config = self.image_gen.APIConfig(
            base_url="https://sub-api.example.com/v1",
            api_key="sk-test",
            default_model="gpt-image-2",
            timeout_seconds=10,
        )
        payload = {"prompt": "a blue circle"}
        request_count = 0
        sleep_calls = []

        async def handler(request):
            nonlocal request_count
            request_count += 1
            if request_count == 1:
                return httpx.Response(500, json={"error": {"message": "temporary"}})
            return httpx.Response(200, json={"data": [{"b64_json": "ZmluYWw="}]})

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        async def run():
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                with patch.object(self.image_gen.asyncio, "sleep", new=fake_sleep):
                    return await self.image_gen._generate_one_with_retries(
                        client,
                        config,
                        payload,
                        attempts=2,
                        job_label="[job 1/1]",
                        quiet=True,
                    )

        images = asyncio.run(run())

        self.assertEqual(images, ["ZmluYWw="])
        self.assertEqual(request_count, 2)
        self.assertEqual(sleep_calls, [])

    def test_retry_gives_up_after_second_timeout(self):
        config = self.image_gen.APIConfig(
            base_url="https://sub-api.example.com/v1",
            api_key="sk-test",
            default_model="gpt-image-2",
            timeout_seconds=10,
        )
        payload = {"prompt": "a blue circle"}
        request_count = 0
        sleep_calls = []

        async def handler(request):
            nonlocal request_count
            request_count += 1
            raise httpx.ReadTimeout("timed out", request=request)

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        async def run():
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                with patch.object(self.image_gen.asyncio, "sleep", new=fake_sleep):
                    await self.image_gen._generate_one_with_retries(
                        client,
                        config,
                        payload,
                        attempts=2,
                        job_label="[job 1/1]",
                        quiet=True,
                    )

        with self.assertRaises(httpx.ReadTimeout):
            asyncio.run(run())

        self.assertEqual(request_count, 2)
        self.assertEqual(sleep_calls, [])

    def test_async_stream_response_extracts_completed_image(self):
        config = self.image_gen.APIConfig(
            base_url="https://sub-api.example.com/v1",
            api_key="sk-test",
            default_model="gpt-image-2",
            timeout_seconds=10,
        )
        payload = {
            "model": "gpt-image-2",
            "prompt": "a blue circle",
            "stream": True,
            "response_format": "b64_json",
        }
        stream_body = (
            "event: image_generation.partial_image\n"
            'data: {"type":"image_generation.partial_image","b64_json":"cGFydGlhbA=="}\n\n'
            "event: image_generation.completed\n"
            'data: {"type":"image_generation.completed","b64_json":"ZmluYWw="}\n\n'
        )

        async def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=stream_body,
            )

        async def run():
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                return await self.image_gen._post_json_api_async(
                    client,
                    config,
                    "/images/generations",
                    payload,
                )

        response = asyncio.run(run())

        self.assertEqual(self.image_gen._extract_b64_images(response), ["ZmluYWw="])

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

    def test_edit_stream_request_uses_event_stream_accept_header(self):
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
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text='data: {"type":"image_generation.completed","b64_json":"ZWRpdA=="}\n\n',
            )

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
        multipart_body = request.content.decode("latin-1")
        self.assertEqual(request.headers["accept"], "text/event-stream")
        self.assertIn('name="stream"', multipart_body)
        self.assertIn("\r\n\r\ntrue\r\n", multipart_body)
        self.assertIn('name="response_format"', multipart_body)
        self.assertIn("\r\n\r\nb64_json\r\n", multipart_body)
        self.assertEqual(self.image_gen._extract_b64_images(response), ["ZWRpdA=="])


if __name__ == "__main__":
    unittest.main()
