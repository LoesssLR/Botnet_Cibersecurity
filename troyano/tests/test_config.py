"""Pruebas de la configuración por variables de entorno."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config


class TestConfigDefaults(unittest.TestCase):
    def test_nombre_y_version(self):
        self.assertEqual(config.APP_NAME, "AgenteUTN")
        self.assertEqual(config.VERSION, "2.0")

    def test_valores_por_defecto(self):
        self.assertEqual(config.C2_HOST, "127.0.0.1")
        self.assertEqual(config.C2_PORT, 8443)
        self.assertEqual(config.DEFAULT_MAX_DURATION_S, 120)
        self.assertEqual(config.DEFAULT_MAX_CONCURRENCY, 200)
        self.assertEqual(config.DEFAULT_RECONNECT_ATTEMPTS, 3)
        self.assertEqual(config.DEFAULT_RECONNECT_DELAY_S, 5)

    def test_sin_variables_los_topes_usan_el_defecto(self):
        self.assertEqual(config.MAX_DURATION_S, 120)
        self.assertEqual(config.MAX_CONCURRENCY, 200)


class TestEnvInt(unittest.TestCase):
    def test_valor_vacio_usa_defecto(self):
        with patch.dict(os.environ, {"UTN_CAP": ""}, clear=False):
            self.assertEqual(config._env_int("UTN_CAP", 7), 7)

    def test_valor_numerico(self):
        with patch.dict(os.environ, {"UTN_CAP": "42"}, clear=False):
            self.assertEqual(config._env_int("UTN_CAP", 7), 42)

    def test_cero_se_conserva(self):
        with patch.dict(os.environ, {"UTN_CAP": "0"}, clear=False):
            self.assertEqual(config._env_int("UTN_CAP", 7), 0)

    def test_valor_no_numerico_usa_defecto(self):
        with patch.dict(os.environ, {"UTN_CAP": "abc"}, clear=False):
            self.assertEqual(config._env_int("UTN_CAP", 7), 7)


if __name__ == "__main__":
    unittest.main()
