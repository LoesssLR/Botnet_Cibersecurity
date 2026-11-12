"""Pruebas del protocolo JSON por línea."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.protocol import MAX_MESSAGE_BYTES, decode_message, encode_message


class TestProtocol(unittest.TestCase):
    def test_codificar_json(self):
        mensaje = {"type": "ping", "id": "123"}
        resultado = encode_message(mensaje)
        self.assertTrue(resultado.endswith(b"\n"))
        self.assertEqual(decode_message(resultado), mensaje)

    def test_caracteres_especiales(self):
        mensaje = {"type": "result", "data": {"text": "Conexión exitosa"}}
        resultado = encode_message(mensaje)
        self.assertEqual(decode_message(resultado), mensaje)

    def test_rechazar_lista_json(self):
        with self.assertRaises(ValueError):
            decode_message(b'["ping"]\n')

    def test_rechazar_sin_salto_de_linea(self):
        with self.assertRaises(ValueError):
            decode_message(b'{"type":"ping"}')

    def test_rechazar_json_invalido(self):
        with self.assertRaises(ValueError):
            decode_message(b"{no-json}\n")

    def test_rechazar_mensaje_grande(self):
        mensaje = {"data": "X" * MAX_MESSAGE_BYTES}
        with self.assertRaises(ValueError):
            encode_message(mensaje)


if __name__ == "__main__":
    unittest.main()
