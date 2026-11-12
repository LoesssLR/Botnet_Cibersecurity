"""Pruebas de la carga HTTP controlada (comando load)."""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.load_command import _as_int, _bounded, parse_target, run_load


class ParseTargetTests(unittest.TestCase):
    def test_puerto_por_defecto(self):
        self.assertEqual(
            parse_target("http://10.0.0.9"),
            ("10.0.0.9", 80, "/"),
        )

    def test_puerto_y_ruta(self):
        self.assertEqual(
            parse_target("http://10.0.0.9:8080/ruta?x=1"),
            ("10.0.0.9", 8080, "/ruta?x=1"),
        )

    def test_rechaza_https(self):
        with self.assertRaises(ValueError):
            parse_target("https://10.0.0.9")

    def test_rechaza_vacio(self):
        with self.assertRaises(ValueError):
            parse_target("")


class BoundedTests(unittest.TestCase):
    def test_aplica_el_tope(self):
        self.assertEqual(_bounded(999, 200), 200)

    def test_sin_tope_no_recorta(self):
        self.assertEqual(_bounded(999, None), 999)
        self.assertEqual(_bounded(999, 0), 999)

    def test_minimo_uno(self):
        self.assertEqual(_bounded(0, 200), 1)

    def test_as_int_usa_default(self):
        self.assertEqual(_as_int("no-numerico", 30), 30)
        self.assertEqual(_as_int(15, 30), 15)
        self.assertEqual(_as_int(None, 30), 30)


class RunLoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_inundacion_contra_servidor_local(self):
        async def handler(reader, writer):
            try:
                while True:
                    raw = await reader.readline()
                    if not raw:
                        break
                    if raw == b"\r\n":
                        writer.write(
                            b"HTTP/1.1 200 OK\r\n"
                            b"Content-Length: 2\r\n"
                            b"Connection: close\r\n"
                            b"\r\n"
                            b"ok"
                        )
                        await writer.drain()
                        break
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            data = await run_load(
                f"http://127.0.0.1:{port}/",
                duration=1,
                concurrency=3,
            )

        self.assertGreaterEqual(data["sent"], 1)
        self.assertGreaterEqual(data["errors"], 0)
        self.assertEqual(data["duration_s"], 1)
        self.assertGreater(data["rps"], 0)

    async def test_target_invalido_lanza_error(self):
        with self.assertRaises(ValueError):
            await run_load("ftp://nada", duration=1, concurrency=1)


if __name__ == "__main__":
    unittest.main()
