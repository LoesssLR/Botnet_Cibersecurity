"""Pruebas unitarias de los ayudantes del agente de prueba (load y reconexion)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("lab_test_agent", REPO_ROOT / "agent" / "test_agent.py")
lab_agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab_agent)


class ParseTargetTests(unittest.TestCase):
    def test_host_ruta_y_puerto_por_defecto(self):
        self.assertEqual(lab_agent.parse_target("http://10.0.0.1"), ("10.0.0.1", 80, "/"))

    def test_puerto_y_ruta_explicitos(self):
        self.assertEqual(lab_agent.parse_target("http://10.0.0.1:8080/x/y"), ("10.0.0.1", 8080, "/x/y"))

    def test_conserva_query(self):
        self.assertEqual(lab_agent.parse_target("http://10.0.0.1/a?b=1"), ("10.0.0.1", 80, "/a?b=1"))

    def test_rechaza_https(self):
        with self.assertRaises(ValueError):
            lab_agent.parse_target("https://10.0.0.1")

    def test_rechaza_vacio(self):
        with self.assertRaises(ValueError):
            lab_agent.parse_target("")


class BuildRequestTests(unittest.TestCase):
    def test_primera_linea_http(self):
        request = lab_agent._build_request("10.0.0.1", "/x").decode("ascii")
        self.assertTrue(request.startswith("GET /x HTTP/1.1\r\n"))

    def test_incluye_host_y_cierre(self):
        request = lab_agent._build_request("10.0.0.1", "/").decode("ascii")
        self.assertIn("Host: 10.0.0.1\r\n", request)
        self.assertIn("Connection: close\r\n", request)
        self.assertTrue(request.endswith("\r\n\r\n"))


class LimitesTests(unittest.TestCase):
    def test_topes_documentados(self):
        self.assertEqual(lab_agent.MAX_DURATION_S, 120)
        self.assertEqual(lab_agent.MAX_CONCURRENCY, 200)


class ReconnectTests(unittest.TestCase):
    def test_reconecta_si_el_c2_no_esta_disponible(self):
        self.assertTrue(lab_agent.should_reconnect(1, 5.0))
        self.assertTrue(lab_agent.should_reconnect(2, 5.0))

    def test_no_reconecta_tras_stop(self):
        self.assertFalse(lab_agent.should_reconnect(0, 5.0))

    def test_sin_intervalo_no_reconecta(self):
        self.assertFalse(lab_agent.should_reconnect(1, 0.0))
