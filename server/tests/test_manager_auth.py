"""Pruebas de autenticacion, saneamiento y limites del servidor C2."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c2.manager import AgentManager, sanitize_agent_id


def encode(message: dict) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


async def wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condicion no cumplida dentro del tiempo limite")
        await asyncio.sleep(0.05)


class SanitizeAgentIdTests(unittest.TestCase):
    def test_limpia_ansi_y_caracteres_de_control(self):
        clean = sanitize_agent_id("\x1b[31mzombie\n-01\x1b[0m")
        self.assertNotIn("\x1b", clean)
        self.assertNotIn("\n", clean)
        self.assertLessEqual(len(clean), 64)
        self.assertRegex(clean, r"^[A-Za-z0-9._:-]+$")

    def test_limita_longitud(self):
        clean = sanitize_agent_id("a" * 200)
        self.assertEqual(len(clean), 64)


class ManagerAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_secreto_invalido_devuelve_error_y_no_registra(self):
        manager = AgentManager("127.0.0.1", 0, shared_secret="clave")
        await manager.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", manager.port)
            try:
                writer.write(encode({"type": "hello", "agent_id": "zombie-01", "secret": "mala"}))
                await writer.drain()
                line = await asyncio.wait_for(reader.readline(), timeout=3)
                message = json.loads(line.decode("utf-8"))
                self.assertEqual(message.get("type"), "error")
                self.assertEqual(message.get("code"), "auth")
                self.assertEqual(manager.agents, [])
            finally:
                writer.close()
        finally:
            await manager.stop()

    async def test_hello_con_ansi_guarda_id_limpio(self):
        manager = AgentManager("127.0.0.1", 0)
        await manager.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", manager.port)
            try:
                writer.write(encode({"type": "hello", "agent_id": "\x1b[31mzombie\x1b[0m"}))
                await writer.drain()
                await wait_for(lambda: len(manager.agents) == 1)
                self.assertEqual(manager.agents[0].agent_id, "zombie")
            finally:
                writer.close()
        finally:
            await manager.stop()

    async def test_limite_de_conexiones_concurrentes(self):
        manager = AgentManager("127.0.0.1", 0, max_connections=1)
        await manager.start()
        first_reader = None
        first_writer = None
        second_reader = None
        second_writer = None
        try:
            first_reader, first_writer = await asyncio.open_connection("127.0.0.1", manager.port)
            first_writer.write(encode({"type": "hello", "agent_id": "zombie-01"}))
            await first_writer.drain()
            await wait_for(lambda: len(manager.agents) == 1)

            second_reader, second_writer = await asyncio.open_connection("127.0.0.1", manager.port)
            second_writer.write(encode({"type": "hello", "agent_id": "zombie-02"}))
            await second_writer.drain()
            line = await asyncio.wait_for(second_reader.readline(), timeout=3)
            message = json.loads(line.decode("utf-8"))
            self.assertEqual(message.get("type"), "error")
            self.assertEqual(message.get("code"), "busy")
            self.assertEqual(len(manager.agents), 1)
        finally:
            for writer in (second_writer, first_writer):
                if writer is not None:
                    writer.close()
            await manager.stop()


if __name__ == "__main__":
    unittest.main()
