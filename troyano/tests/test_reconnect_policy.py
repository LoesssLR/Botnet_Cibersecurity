"""Pruebas de la política de reconexión."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.reconnect_policy import reconnect_decision


class TestReconnectPolicy(unittest.TestCase):
    def test_busy_permite_reintento(self):
        result = reconnect_decision({"type": "error", "code": "busy"})
        self.assertTrue(result["retry"])
        self.assertGreater(result["delay"], 0)

    def test_auth_no_reconecta(self):
        result = reconnect_decision({"type": "error", "code": "auth"})
        self.assertFalse(result["retry"])

    def test_error_desconocido_no_reconecta(self):
        result = reconnect_decision({"type": "error", "code": "otro"})
        self.assertFalse(result["retry"])

    def test_bye_no_reconecta(self):
        result = reconnect_decision({"type": "bye", "reason": "kicked"})
        self.assertFalse(result["retry"])

    def test_perdida_conexion(self):
        result = reconnect_decision({"type": "connection_lost"}, attempts=1)
        self.assertTrue(result["retry"])

    def test_maximo_intentos(self):
        from src.config import DEFAULT_RECONNECT_ATTEMPTS

        result = reconnect_decision(
            {"type": "connection_lost"},
            attempts=DEFAULT_RECONNECT_ATTEMPTS,
        )
        self.assertFalse(result["retry"])


if __name__ == "__main__":
    unittest.main()
