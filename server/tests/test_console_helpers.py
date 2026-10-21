"""Pruebas unitarias de los ayudantes de la consola del C2."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c2.console import (
    REQUEST_TIMEOUT,
    _as_int,
    _command_timeout,
    _fit,
    _fmt_duration,
    _parse_command,
    _redact_url,
)


class FitTests(unittest.TestCase):
    def test_texto_corto_no_cambia(self):
        self.assertEqual(_fit("zombie-01", 16), "zombie-01")

    def test_texto_largo_se_trunca_con_marca(self):
        self.assertEqual(_fit("abcdefgh", 5), "abcd~")


class FmtDurationTests(unittest.TestCase):
    def test_segundos(self):
        self.assertEqual(_fmt_duration(45), "45s")

    def test_minutos(self):
        self.assertEqual(_fmt_duration(125), "2m05s")

    def test_horas(self):
        self.assertEqual(_fmt_duration(3725), "1h02m")

    def test_negativo_se_normaliza_a_cero(self):
        self.assertEqual(_fmt_duration(-5), "0s")


class AsIntTests(unittest.TestCase):
    def test_entero_valido(self):
        self.assertEqual(_as_int("30", 0), 30)

    def test_texto_invalido_usa_default(self):
        self.assertEqual(_as_int("abc", 7), 7)

    def test_none_usa_default(self):
        self.assertEqual(_as_int(None, 7), 7)


class CommandTimeoutTests(unittest.TestCase):
    def test_comando_normal_usa_el_timeout_estandar(self):
        self.assertEqual(_command_timeout("ping", {}), REQUEST_TIMEOUT)

    def test_load_suma_margen_a_la_duracion(self):
        self.assertEqual(_command_timeout("load", {"duration": "30"}), 50.0)

    def test_load_sin_duracion_usa_default_de_30(self):
        self.assertEqual(_command_timeout("load", {}), 50.0)


class ParseCommandTests(unittest.TestCase):
    def test_sin_argumentos(self):
        self.assertEqual(_parse_command(["ping"]), ("ping", {}))

    def test_clave_valor(self):
        name, args = _parse_command(["load", "target=http://10.0.0.1", "duration=5"])
        self.assertEqual(name, "load")
        self.assertEqual(args, {"target": "http://10.0.0.1", "duration": "5"})

    def test_posicionales_se_unen_como_texto(self):
        name, args = _parse_command(["echo", "hola", "mundo"])
        self.assertEqual(name, "echo")
        self.assertEqual(args, {"text": "hola mundo"})


class RedactUrlTests(unittest.TestCase):
    def test_url_sin_credenciales_no_cambia(self):
        self.assertEqual(
            _redact_url("http://10.0.0.9:19999/api/v1/data?chart=system.cpu"),
            "http://10.0.0.9:19999/api/v1/data?chart=system.cpu",
        )

    def test_elimina_usuario_y_clave(self):
        self.assertEqual(_redact_url("http://netdata:secreto123@10.0.0.9:19999"), "http://10.0.0.9:19999")

    def test_elimina_solo_usuario(self):
        self.assertEqual(_redact_url("http://operador@10.0.0.9:19999"), "http://10.0.0.9:19999")

    def test_conserva_ruta_y_query(self):
        self.assertEqual(
            _redact_url("http://u:p@10.0.0.9:19999/api/v1/data?chart=system.cpu"),
            "http://10.0.0.9:19999/api/v1/data?chart=system.cpu",
        )

    def test_url_invalida_se_devuelve_tal_cual(self):
        self.assertEqual(_redact_url("no-es-una-url"), "no-es-una-url")
