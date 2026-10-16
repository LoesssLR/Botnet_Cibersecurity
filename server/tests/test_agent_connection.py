"""Pruebas unitarias de AgentConnection (conexion de un agente con el C2)."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c2.agent import AgentConnection


class FakeWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    def close(self) -> None:
        self.closed = True


class FakeReader:
    async def readline(self) -> bytes:
        return b""


def make_agent() -> tuple[AgentConnection, FakeWriter]:
    writer = FakeWriter()
    agent = AgentConnection(agent_id="zombie-01", peer="10.0.0.5:1234", reader=FakeReader(), writer=writer)
    return agent, writer


def sent_messages(writer: FakeWriter) -> list[dict]:
    lines = bytes(writer.data).decode("utf-8").splitlines()
    return [json.loads(line) for line in lines]


async def wait_for_pending(agent: AgentConnection) -> None:
    for _ in range(200):
        if agent._pending:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("la solicitud no quedo pendiente")


class AgentConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_codifica_una_linea_json(self):
        agent, writer = make_agent()
        await agent.send({"type": "command", "id": "abc"})
        self.assertEqual(sent_messages(writer), [{"type": "command", "id": "abc"}])

    async def test_request_envia_comando_con_id_correlacionado(self):
        agent, writer = make_agent()
        task = asyncio.create_task(agent.request("ping", {}, timeout=2))
        await wait_for_pending(agent)
        message = sent_messages(writer)[0]
        self.assertEqual(message["type"], "command")
        self.assertEqual(message["name"], "ping")
        self.assertEqual(message["args"], {})
        self.assertTrue(
            agent.resolve({"type": "result", "id": message["id"], "status": "ok", "data": {"pong": True}})
        )
        result = await task
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["pong"], True)
        self.assertEqual(agent.commands_sent, 1)

    async def test_request_sin_respuesta_agota_el_tiempo(self):
        agent, _ = make_agent()
        with self.assertRaises(asyncio.TimeoutError):
            await agent.request("ping", {}, timeout=0.05)

    async def test_fail_pending_propaga_error_a_solicitudes(self):
        agent, _ = make_agent()
        task = asyncio.create_task(agent.request("ping", {}, timeout=5))
        await wait_for_pending(agent)
        agent.fail_pending(ConnectionError("agente desconectado"))
        with self.assertRaises(ConnectionError):
            await task

    async def test_resolve_ignora_id_desconocido(self):
        agent, _ = make_agent()
        self.assertFalse(agent.resolve({"type": "result", "id": "nope"}))

    async def test_close_cierra_el_writer(self):
        agent, writer = make_agent()
        agent.close()
        self.assertTrue(writer.closed)

    async def test_touch_actualiza_last_seen(self):
        agent, _ = make_agent()
        agent.last_seen = 0.0
        agent.touch()
        self.assertGreater(agent.last_seen, 0.0)
