"""Pruebas unitarias del parseo y calculo de metricas de Netdata."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c2.metrics import compute_metrics, parse_chart


class ParseChartTests(unittest.TestCase):
    def test_devuelve_la_ultima_fila(self):
        payload = {"labels": ["time", "idle"], "data": [[1, 86.1], [2, 90.0]]}
        self.assertEqual(parse_chart(payload), {"time": 2, "idle": 90.0})

    def test_payload_vacio_devuelve_none(self):
        self.assertIsNone(parse_chart({}))

    def test_sin_filas_devuelve_none(self):
        self.assertIsNone(parse_chart({"labels": ["time"], "data": []}))


class ComputeMetricsTests(unittest.TestCase):
    def test_calculo_completo(self):
        cpu = {"idle": 86.1}
        ram = {"free": 1200.0, "used": 2800.0, "cached": 900.0, "buffers": 100.0}
        net = {"eth0": 3456.7, "lo": 12.3}
        self.assertEqual(
            compute_metrics(cpu, ram, net),
            {"cpu_pct": 13.9, "ram_pct": 56.0, "net_kbit_s": 3469.0},
        )

    def test_sin_datos_devuelve_none_en_todo(self):
        self.assertEqual(
            compute_metrics(None, None, None),
            {"cpu_pct": None, "ram_pct": None, "net_kbit_s": None},
        )

    def test_ram_sin_total_no_calcula_porcentaje(self):
        result = compute_metrics(None, {"used": 0.0, "free": 0.0}, None)
        self.assertIsNone(result["ram_pct"])

    def test_cpu_sin_idle_suma_dimensiones_de_uso(self):
        # Netdata v2: system.cpu no trae idle; las dimensiones de uso suman la utilizacion
        result = compute_metrics({"user": 10.0, "system": 3.5}, None, None)
        self.assertEqual(result["cpu_pct"], 13.5)

    def test_valores_no_numericos_se_ignoran(self):
        cpu = {"idle": "n/a", "user": 5.0}
        result = compute_metrics(cpu, None, None)
        self.assertEqual(result["cpu_pct"], 5.0)
