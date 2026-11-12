"""Pruebas de los mensajes de identidad (hello y heartbeat)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from identity import build_heartbeat, build_hello


class TestIdentity(unittest.TestCase):
    def test_hello(self):
        message = build_hello("utn-prueba01")
        self.assertEqual(message["type"], "hello")
        self.assertTrue(message["agent_id"].startswith("utn-"))
        self.assertIn("hostname", message)
        self.assertIn("os", message)
        self.assertIn("user", message)
        self.assertIn("version", message)

    def test_hello_con_secreto(self):
        message = build_hello("utn-prueba01", secret="abc123")
        self.assertEqual(message["secret"], "abc123")

    def test_heartbeat(self):
        message = build_heartbeat()
        self.assertEqual(message["type"], "heartbeat")
        self.assertIsInstance(message["ts"], float)


if __name__ == "__main__":
    unittest.main()
