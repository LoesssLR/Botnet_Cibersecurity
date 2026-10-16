"""Pruebas unitarias del registro de agentes (AgentManager)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c2.agent import AgentConnection
from c2.manager import AgentManager


class FakeWriter:
    def write(self, data: bytes) -> None:
        pass

    def close(self) -> None:
        pass


class FakeReader:
    async def readline(self) -> bytes:
        return b""


def make_agent(agent_id: str, connected_at: float) -> AgentConnection:
    return AgentConnection(
        agent_id=agent_id,
        peer="10.0.0.5:1234",
        reader=FakeReader(),
        writer=FakeWriter(),
        connected_at=connected_at,
        last_seen=connected_at,
    )


def build_manager(agents: list[AgentConnection]) -> AgentManager:
    manager = AgentManager("127.0.0.1", 0)
    for agent in agents:
        manager._agents[agent.agent_id] = agent
    return manager


class FindTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old = make_agent("zombie-01", connected_at=100.0)
        self.new = make_agent("zombie-02", connected_at=200.0)
        self.manager = build_manager([self.new, self.old])

    def test_agents_ordenados_por_conexion(self):
        self.assertEqual([agent.agent_id for agent in self.manager.agents], ["zombie-01", "zombie-02"])

    def test_busqueda_por_indice(self):
        self.assertIs(self.manager.find("0"), self.old)
        self.assertIs(self.manager.find("1"), self.new)

    def test_busqueda_por_id_exacto(self):
        self.assertIs(self.manager.find("zombie-02"), self.new)

    def test_busqueda_por_prefijo_unico(self):
        single = build_manager([self.old])
        self.assertIs(single.find("zombie"), self.old)

    def test_prefijo_ambiguo_devuelve_none(self):
        self.assertIsNone(self.manager.find("zombie"))

    def test_indice_fuera_de_rango_devuelve_none(self):
        self.assertIsNone(self.manager.find("9"))

    def test_desconocido_devuelve_none(self):
        self.assertIsNone(self.manager.find("otro"))
