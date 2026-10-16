"""Prueba de humo del servidor C2 (sin dependencias externas)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c2.manager import AgentManager


def encode(message: dict) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


class FakeAgent:
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.reader = None
        self.writer = None
        self._task: asyncio.Task | None = None

    async def connect(self, host: str, port: int) -> None:
        self.reader, self.writer = await asyncio.open_connection(host, port)
        hello = {
            "type": "hello",
            "agent_id": self.agent_id,
            "hostname": "fake-host",
            "os": "test",
            "user": "tester",
            "version": "0",
        }
        self.writer.write(encode(hello))
        await self.writer.drain()
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            line = await self.reader.readline()
            if not line:
                return
            message = json.loads(line.decode("utf-8"))
            if message.get("type") != "command":
                continue
            if message.get("name") == "ping":
                status, data = "ok", {"pong": True}
            else:
                status, data = "error", {"error": f"no soportado: {message.get('name')}"}
            self.writer.write(encode({"type": "result", "id": message.get("id"), "status": status, "data": data}))
            await self.writer.drain()

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
        self.writer.close()


async def wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condicion no cumplida dentro del tiempo limite")
        await asyncio.sleep(0.05)


async def main() -> int:
    events: list[str] = []
    manager = AgentManager("127.0.0.1", 0, on_event=events.append)
    await manager.start()
    try:
        agent = FakeAgent("zombie-test-01")
        await agent.connect("127.0.0.1", manager.port)
        await wait_for(lambda: len(manager.agents) == 1)

        found = manager.find("zombie")
        assert found is not None, "find() por prefijo fallo"

        result = await found.request("ping", {}, timeout=5)
        assert result["status"] == "ok" and result["data"]["pong"] is True

        responses = await manager.broadcast("ping", {}, timeout=5)
        assert len(responses) == 1 and not isinstance(responses[0][1], BaseException)

        result = await found.request("desconocido", {}, timeout=5)
        assert result["status"] == "error"

        second = FakeAgent("zombie-test-02")
        await second.connect("127.0.0.1", manager.port)
        await wait_for(lambda: len(manager.agents) == 2)

        await agent.close()
        await wait_for(lambda: len(manager.agents) == 1)
        await second.close()
        await wait_for(lambda: len(manager.agents) == 0)

        assert any("[+]" in event for event in events), "faltan eventos de conexion"
        assert any("[-]" in event for event in events), "faltan eventos de desconexion"
    finally:
        await manager.stop()

    print("OK: smoke test del C2 paso (registro, ping, broadcast, desconexion)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
