import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
CODEX_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"


class PluginManifestTests(unittest.TestCase):
    def test_codex_plugin_name_matches_marketplace(self):
        marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        codex_manifest = json.loads(CODEX_MANIFEST.read_text(encoding="utf-8"))

        marketplace_plugins = marketplace.get("plugins", [])
        root_plugin = next(
            (plugin for plugin in marketplace_plugins if plugin.get("source") == "."),
            None,
        )

        self.assertIsNotNone(root_plugin, "marketplace must include the root plugin")
        self.assertEqual(
            codex_manifest.get("name"),
            root_plugin.get("name"),
            "Codex manifest name must match the marketplace plugin name",
        )


if __name__ == "__main__":
    unittest.main()
