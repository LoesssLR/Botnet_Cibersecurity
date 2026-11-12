"""Pruebas de la construcción de frames result."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from response import build_result


class TestResponse(unittest.TestCase):
    def test_resultado_ping(self):
        comando = {
            "type": "command",
            "id": "a1b2c3d4",
            "name": "ping",
            "args": {},
        }
        resultado = build_result(comando, "ok", {"pong": True})
        self.assertEqual(
            resultado,
            {
                "type": "result",
                "id": "a1b2c3d4",
                "status": "ok",
                "data": {"pong": True},
            },
        )

    def test_id_obligatorio(self):
        with self.assertRaises(ValueError):
            build_result({"type": "command", "name": "ping"}, "ok", {"pong": True})

    def test_estado_invalido(self):
        with self.assertRaises(ValueError):
            build_result({"type": "command", "id": "123"}, "pendiente", {})


if __name__ == "__main__":
    unittest.main()
