"""Pruebas de la interpretación de eventos del servidor."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from server_events import handle_server_event


class TestServerEvents(unittest.TestCase):
    def test_error_auth(self):
        result = handle_server_event(
            {"type": "error", "code": "auth", "status": "error"}
        )
        self.assertEqual(result["action"], "disconnect")
        self.assertFalse(result["reconnect"])

    def test_error_busy(self):
        result = handle_server_event(
            {"type": "error", "code": "busy", "status": "error"}
        )
        self.assertEqual(result["action"], "disconnect")
        self.assertTrue(result["reconnect"])

    def test_bye(self):
        result = handle_server_event({"type": "bye", "reason": "kicked"})
        self.assertEqual(result["action"], "disconnect")
        self.assertFalse(result["reconnect"])

    def test_unknown_message(self):
        result = handle_server_event({"type": "unknown"})
        self.assertEqual(result["action"], "ignore")
        self.assertFalse(result["reconnect"])


if __name__ == "__main__":
    unittest.main()
