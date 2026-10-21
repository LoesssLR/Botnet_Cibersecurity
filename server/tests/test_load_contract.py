"""Pruebas del contrato y la validacion centralizada del comando load."""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c2.config import Config
from c2.console import MAX_CONCURRENCY, MAX_DURATION_S, Console, normalize_load_args


def make_config(**overrides) -> Config:
    values = {
        "bind_host": "127.0.0.1",
        "port": 0,
        "shared_secret": "",
        "netdata_url": "",
        "log_dir": Path("logs"),
        "data_dir": Path("data"),
        "target_host": "",
        "target_http_port": None,
    }
    values.update(overrides)
    return Config(**values)


class FakeAgent:
    def __init__(self, agent_id: str = "zombie-01") -> None:
        self.agent_id = agent_id
        self.requests: list[tuple[str, dict, float]] = []

    async def request(self, name: str, args: dict | None = None, timeout: float = 10.0) -> dict:
        self.requests.append((name, args or {}, timeout))
        return {"status": "ok", "data": {}}


class FakeManager:
    def __init__(self, agents: list[FakeAgent]) -> None:
        self.agents = agents
        self.calls: list[tuple[str, dict, float]] = []

    async def broadcast(self, name: str, args: dict | None = None, timeout: float = 10.0):
        payload = args or {}
        self.calls.append((name, payload, timeout))
        return [
            (
                agent,
                {
                    "status": "ok",
                    "data": {
                        "sent": 0,
                        "errors": 0,
                        "duration_s": payload.get("duration", 0),
                        "rps": 0.0,
                    },
                },
            )
            for agent in self.agents
        ]


def make_console(agents: list[FakeAgent], config: Config | None = None) -> Console:
    console = Console(FakeManager(agents), config or make_config(), after_delay=0)

    async def fake_snapshot(label: str = "manual", extra: dict | None = None) -> bool:
        return False

    console._snapshot = fake_snapshot
    return console


class SendLoadContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_load_envia_enteros(self):
        agent = FakeAgent()
        console = make_console([agent])
        console.selected = agent
        with redirect_stdout(io.StringIO()):
            await console._cmd_send(
                ["load", "target=http://127.0.0.1:8080", "duration=5", "concurrency=7"]
            )
        name, args, _ = agent.requests[0]
        self.assertEqual(name, "load")
        self.assertIs(type(args["duration"]), int)
        self.assertIs(type(args["concurrency"]), int)
        self.assertEqual(args["duration"], 5)
        self.assertEqual(args["concurrency"], 7)

    async def test_send_load_rechaza_https(self):
        agent = FakeAgent()
        console = make_console([agent])
        console.selected = agent
        with redirect_stdout(io.StringIO()):
            await console._cmd_send(
                ["load", "target=https://127.0.0.1", "duration=5", "concurrency=5"]
            )
        self.assertEqual(agent.requests, [])

    async def test_send_load_rechaza_target_fuera_de_allowlist(self):
        agent = FakeAgent()
        console = make_console([agent], make_config(target_host="10.0.0.1"))
        console.selected = agent
        with redirect_stdout(io.StringIO()):
            await console._cmd_send(
                ["load", "target=http://10.0.0.2", "duration=5", "concurrency=5"]
            )
        self.assertEqual(agent.requests, [])


class BroadcastLoadContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_load_envia_enteros(self):
        agent = FakeAgent()
        console = make_console([agent])
        with redirect_stdout(io.StringIO()):
            await console._cmd_broadcast(
                ["load", "target=http://127.0.0.1:8080", "duration=5", "concurrency=7"]
            )
        name, args, _ = console.manager.calls[0]
        self.assertEqual(name, "load")
        self.assertIs(type(args["duration"]), int)
        self.assertIs(type(args["concurrency"]), int)
        self.assertEqual(args["duration"], 5)
        self.assertEqual(args["concurrency"], 7)

    async def test_broadcast_load_rechaza_esquema_invalido(self):
        agent = FakeAgent()
        console = make_console([agent])
        with redirect_stdout(io.StringIO()):
            await console._cmd_broadcast(
                ["load", "target=ftp://127.0.0.1", "duration=5", "concurrency=5"]
            )
        self.assertEqual(console.manager.calls, [])

    async def test_broadcast_load_registra_metadatos(self):
        agent = FakeAgent()
        console = make_console([agent])
        calls: list[tuple[str, dict]] = []

        async def fake_snapshot(label: str = "manual", extra: dict | None = None) -> bool:
            calls.append((label, extra or {}))
            return False

        console._snapshot = fake_snapshot
        with redirect_stdout(io.StringIO()):
            await console._cmd_broadcast(
                ["load", "target=http://127.0.0.1:8080", "duration=5", "concurrency=7"]
            )
        self.assertEqual([label for label, _ in calls], ["antes", "despues"])
        before = calls[0][1]
        self.assertEqual(before["target"], "http://127.0.0.1:8080/")
        self.assertEqual(before["duration"], 5)
        self.assertEqual(before["concurrency"], 7)
        self.assertEqual(len(before["run_id"]), 8)
        after = calls[1][1]
        self.assertEqual(after["summary"]["ok"], 1)
        self.assertEqual(after["summary"]["sent"], 0)


class NormalizeLoadTests(unittest.TestCase):
    def test_recorta_duration_y_concurrency(self):
        result = normalize_load_args(
            {"target": "http://127.0.0.1:8080", "duration": "999", "concurrency": "999"},
            make_config(),
        )
        self.assertEqual(result["duration"], MAX_DURATION_S)
        self.assertEqual(result["concurrency"], MAX_CONCURRENCY)

    def test_rechaza_cero_y_negativos(self):
        with self.assertRaises(ValueError):
            normalize_load_args({"target": "http://127.0.0.1", "duration": "0"}, make_config())
        with self.assertRaises(ValueError):
            normalize_load_args(
                {"target": "http://127.0.0.1", "concurrency": "-1"},
                make_config(),
            )

    def test_rechaza_valores_no_numericos(self):
        with self.assertRaises(ValueError):
            normalize_load_args({"target": "http://127.0.0.1", "duration": "abc"}, make_config())

    def test_rechaza_esquemas_no_http(self):
        with self.assertRaises(ValueError):
            normalize_load_args({"target": "https://127.0.0.1"}, make_config())

    def test_allowlist_permite_localhost(self):
        result = normalize_load_args(
            {"target": "http://localhost:8080", "duration": "5", "concurrency": "5"},
            make_config(target_host="10.0.0.1"),
        )
        self.assertEqual(result["target"], "http://localhost:8080/")

    def test_allowlist_rechaza_otro_host(self):
        with self.assertRaises(ValueError):
            normalize_load_args(
                {"target": "http://10.0.0.2", "duration": "5", "concurrency": "5"},
                make_config(target_host="10.0.0.1"),
            )

    def test_aplica_puerto_configurado_si_falta(self):
        result = normalize_load_args(
            {"target": "http://10.0.0.1/ruta", "duration": "5", "concurrency": "5"},
            make_config(target_host="10.0.0.1", target_http_port=8080),
        )
        self.assertEqual(result["target"], "http://10.0.0.1:8080/ruta")

    def test_rechaza_puerto_distinto_al_configurado(self):
        with self.assertRaises(ValueError):
            normalize_load_args(
                {"target": "http://10.0.0.1:9090", "duration": "5", "concurrency": "5"},
                make_config(target_host="10.0.0.1", target_http_port=8080),
            )


if __name__ == "__main__":
    unittest.main()
