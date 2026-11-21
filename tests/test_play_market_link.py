"""Test suite for the Play Market link generator (zippy.playmarket)."""

from __future__ import annotations

import unittest

from zippy.playmarket import (
    APPS,
    PLAY_STORE_BASE,
    build_play_link,
    find_apps,
    format_result,
    is_package_id,
    resolve,
)


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


if __name__ == "__main__":
    unittest.main()
