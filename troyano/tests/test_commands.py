"""Pruebas de los comandos locales del agente."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from commands import handle_command


class TestCommands(unittest.TestCase):
    def test_ping(self):
        result = handle_command({"id": "001", "name": "ping"})
        self.assertEqual(result["data"]["pong"], True)
        self.assertEqual(result["id"], "001")

    def test_info(self):
        result = handle_command({"id": "002", "name": "info"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("hostname", result["data"])
        self.assertIn("os", result["data"])
        self.assertIn("user", result["data"])
        self.assertIn("cpus", result["data"])

    def test_stop(self):
        result = handle_command({"id": "003", "name": "stop"})
        self.assertEqual(result["data"]["stopping"], True)

    def test_echo(self):
        result = handle_command(
            {"id": "004", "name": "echo", "args": {"text": "hola laboratorio"}}
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["text"], "hola laboratorio")

    def test_comando_desconocido(self):
        result = handle_command({"id": "005", "name": "desconocido"})
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
