"""Credentialed clients must be able to read note version headers."""
import ast
import unittest
from pathlib import Path

class CorsETagTest(unittest.TestCase):
    def test_credentialed_configuration_exposes_etag(self):
        source = Path(__file__).resolve().parents[1] / "app" / "main.py"
        tree = ast.parse(source.read_text())
        config = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                      and node.args and isinstance(node.args[0], ast.Name)
                      and node.args[0].id == "CORSMiddleware")
        options = {kw.arg: ast.literal_eval(kw.value) for kw in config.keywords
                   if kw.arg != "allow_origins"}
        self.assertTrue(options["allow_credentials"])
        self.assertIn("etag", [header.lower() for header in options["expose_headers"]])
