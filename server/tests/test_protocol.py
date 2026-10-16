"""Pruebas unitarias del protocolo JSON por linea."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c2.protocol import MAX_MESSAGE_BYTES, decode, encode, read_message


class EncodeTests(unittest.TestCase):
    def test_termina_en_salto_de_linea(self):
        data = encode({"type": "hello"})
        self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(json.loads(data.decode("utf-8")), {"type": "hello"})

    def test_no_incluye_espacios_extra(self):
        self.assertNotIn(b" ", encode({"type": "result", "id": "x"}))


class DecodeTests(unittest.TestCase):
    def test_mensaje_valido(self):
        self.assertEqual(
            decode(b'{"type":"result","status":"ok"}\n'),
            {"type": "result", "status": "ok"},
        )

    def test_sin_type_falla(self):
        with self.assertRaises(ValueError):
            decode(b'{"id":"x"}\n')

    def test_no_objeto_falla(self):
        with self.assertRaises(ValueError):
            decode(b"[1,2,3]\n")

    def test_json_invalido_falla(self):
        with self.assertRaises(json.JSONDecodeError):
            decode(b"{no es json}\n")


class ReadMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_lee_un_mensaje(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b'{"type":"ping"}\n')
        reader.feed_eof()
        self.assertEqual(await read_message(reader), {"type": "ping"})

    async def test_eof_devuelve_none(self):
        reader = asyncio.StreamReader()
        reader.feed_eof()
        self.assertIsNone(await read_message(reader))

    async def test_limite_documentado(self):
        self.assertEqual(MAX_MESSAGE_BYTES, 64 * 1024)
