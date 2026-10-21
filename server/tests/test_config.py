"""Pruebas del cargador de variables de entorno (.env)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c2.config import load_env_file


class LoadEnvFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / ".env"

    def load(self, content: str, **initial: str) -> None:
        self.path.write_text(content, encoding="utf-8")
        patcher = patch.dict(os.environ, initial, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        load_env_file(self.path)

    def test_export_se_ignora(self):
        self.load("export C2_TEST_EXPORT=valor\n")
        self.assertEqual(os.environ["C2_TEST_EXPORT"], "valor")

    def test_comentario_inline_se_elimina(self):
        self.load("C2_TEST_INLINE=valor # comentario\n")
        self.assertEqual(os.environ["C2_TEST_INLINE"], "valor")

    def test_hash_dentro_de_comillas_se_conserva(self):
        self.load('C2_TEST_QUOTED="secreto # con espacio" # comentario\n')
        self.assertEqual(os.environ["C2_TEST_QUOTED"], "secreto # con espacio")

    def test_hash_sin_espacio_forma_parte_del_valor(self):
        self.load("C2_TEST_HASH=abc#123\n")
        self.assertEqual(os.environ["C2_TEST_HASH"], "abc#123")

    def test_comillas_simples_con_espacios_y_hash(self):
        self.load("C2_TEST_SINGLE='a b # c'\n")
        self.assertEqual(os.environ["C2_TEST_SINGLE"], "a b # c")

    def test_valor_solo_con_comentario_queda_vacio(self):
        self.load("C2_TEST_EMPTY=   # solo comentario\n")
        self.assertEqual(os.environ["C2_TEST_EMPTY"], "")

    def test_valor_con_igual_se_conserva(self):
        self.load("C2_TEST_EQ=a=b=c\n")
        self.assertEqual(os.environ["C2_TEST_EQ"], "a=b=c")

    def test_variable_del_entorno_tiene_prioridad(self):
        self.load("C2_TEST_PRECEDENCIA=del-archivo\n", C2_TEST_PRECEDENCIA="del-entorno")
        self.assertEqual(os.environ["C2_TEST_PRECEDENCIA"], "del-entorno")

    def test_archivo_inexistente_no_falla(self):
        load_env_file(Path(self._tmp.name) / "no-existe.env")


if __name__ == "__main__":
    unittest.main()
