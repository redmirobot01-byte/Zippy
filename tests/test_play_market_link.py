"""Test suite for the Play Market link generator (zippy.playmarket)."""

from __future__ import annotations

import contextlib
import os
import unittest

from zippy.playmarket import (
    APPS,
    PLAY_STORE_BASE,
    ai_lookup,
    ai_settings,
    build_play_link,
    find_apps,
    format_result,
    is_package_id,
    parse_ai_package,
    resolve,
)

AI_ENV_KEYS = ("ZIPPY_AI_API_KEY", "OPENAI_API_KEY", "ZIPPY_AI_BASE_URL", "ZIPPY_AI_MODEL")


@contextlib.contextmanager
def _no_ai_env():
    """AI üýtgetmeleri aýryp, ýerine nulla goýup saklaýar."""
    saved = {key: os.environ.pop(key) for key in AI_ENV_KEYS if key in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


class BuildPlayLinkTests(unittest.TestCase):
    def test_builds_link_from_package(self):
        link = build_play_link("com.happproxy")
        self.assertEqual(link, f"{PLAY_STORE_BASE}?id=com.happproxy")

    def test_rejects_invalid_package(self):
        for bad in ("", "comhappproxy", "com.happ proxy", "123", "a..b"):
            with self.assertRaises(ValueError):
                build_play_link(bad)

    def test_is_package_id(self):
        self.assertTrue(is_package_id("com.example.app"))
        self.assertTrue(is_package_id("io.nekobox"))
        self.assertFalse(is_package_id("happ"))
        self.assertFalse(is_package_id("com.example app"))
        self.assertFalse(is_package_id(""))


class RegistryTests(unittest.TestCase):
    def test_registry_entries_have_valid_packages(self):
        self.assertGreater(len(APPS), 0)
        for app in APPS:
            self.assertTrue(is_package_id(app["package"]), app)
            self.assertTrue(app["name"], app)

    def test_registry_contains_happ(self):
        apps = find_apps("happ")
        self.assertTrue(apps)
        self.assertEqual(apps[0]["package"], "com.happproxy")

    def test_find_apps_case_insensitive(self):
        self.assertTrue(find_apps("V2RAYNG"))
        self.assertTrue(find_apps("hiddify"))

    def test_find_apps_unknown_returns_empty(self):
        self.assertEqual(find_apps("hatam_programmalyk_name"), [])


class ResolveTests(unittest.TestCase):
    def test_resolve_by_name(self):
        app, link = resolve("happ")
        self.assertIsNotNone(app)
        self.assertEqual(link, f"{PLAY_STORE_BASE}?id=com.happproxy")

    def test_resolve_by_package(self):
        app, link = resolve("com.v2ray.ng")
        self.assertIsNone(app)
        self.assertEqual(link, f"{PLAY_STORE_BASE}?id=com.v2ray.ng")

    def test_resolve_unknown(self):
        app, link = resolve("diňe_mälim_bolmaýan_programma")
        self.assertIsNone(app)
        self.assertIsNone(link)

    def test_resolve_empty(self):
        self.assertEqual(resolve("  "), (None, None))

    def test_format_result(self):
        app, link = resolve("happ")
        text = format_result(app, link)
        self.assertIn(link, text)
        self.assertIn("com.happproxy", text)


class AiRegistryTests(unittest.TestCase):
    def test_ai_apps_present_with_valid_packages(self):
        for name in ("ChatGPT", "Gemini", "Microsoft Copilot", "Perplexity", "Claude"):
            apps = find_apps(name)
            self.assertTrue(apps, name)
            self.assertTrue(is_package_id(apps[0]["package"]), name)

    def test_resolve_ai_app_by_name(self):
        app, link = resolve("chatgpt")
        self.assertIsNotNone(app)
        self.assertEqual(link, f"{PLAY_STORE_BASE}?id=com.openai.chatgpt")


class AiLookupTests(unittest.TestCase):
    def test_parse_ai_package_variants(self):
        self.assertEqual(parse_ai_package("com.openai.chatgpt"), "com.openai.chatgpt")
        self.assertEqual(parse_ai_package('"io.nekobox"'), "io.nekobox")
        self.assertEqual(parse_ai_package("Here it is: com.example.app"), "com.example.app")
        self.assertIsNone(parse_ai_package("bulany tapmadym"))

    def test_ai_settings_without_key(self):
        with _no_ai_env():
            self.assertIsNone(ai_settings())

    def test_ai_settings_reads_env(self):
        with _no_ai_env():
            os.environ["ZIPPY_AI_API_KEY"] = "test-key"
            os.environ["ZIPPY_AI_BASE_URL"] = "https://example.com/v1"
            os.environ["ZIPPY_AI_MODEL"] = "test-model"
            config = ai_settings()
            self.assertEqual(config["api_key"], "test-key")
            self.assertEqual(config["base_url"], "https://example.com/v1")
            self.assertEqual(config["model"], "test-model")

    def test_ai_lookup_without_key_returns_none(self):
        with _no_ai_env():
            self.assertIsNone(ai_lookup("ChatGPT"))

    def test_ai_lookup_handles_api_error(self):
        with _no_ai_env():
            os.environ["ZIPPY_AI_API_KEY"] = "test-key"
            os.environ["ZIPPY_AI_BASE_URL"] = "http://127.0.0.1:9"
            self.assertIsNone(ai_lookup("ChatGPT", timeout=2))

    def test_resolve_with_ai_falls_back_to_registry(self):
        with _no_ai_env():
            app, link = resolve("happ", use_ai=True)
            self.assertIsNotNone(app)
            self.assertEqual(link, f"{PLAY_STORE_BASE}?id=com.happproxy")


if __name__ == "__main__":
    unittest.main()
