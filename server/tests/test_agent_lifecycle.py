"""Pruebas de ciclo de vida del agente de prueba (load concurrente y rechazo)."""
from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("lab_test_agent_lifecycle", REPO_ROOT / "agent" / "test_agent.py")
lab_agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab_agent)


def encode(message: dict) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


class AgentLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_cancela_load_y_responde_ping(self):
        sink_connected = asyncio.Event()
        sink_tasks: list[asyncio.Task] = []
        c2_tasks: list[asyncio.Task] = []
        result: dict = {}

        async def sink(reader, writer):
            sink_tasks.append(asyncio.current_task())
            sink_connected.set()
            try:
                await asyncio.sleep(30)
            finally:
                writer.close()

        async def c2_handler(reader, writer):
            c2_tasks.append(asyncio.current_task())
            try:
                if not await reader.readline():
                    return
                writer.write(
                    encode(
                        {
                            "type": "command",
                            "id": "load-1",
                            "name": "load",
                            "args": {
                                "target": f"http://127.0.0.1:{sink_port}",
                                "duration": 30,
                                "concurrency": 4,
                            },
                        }
                    )
                )
                await writer.drain()
                await asyncio.wait_for(sink_connected.wait(), timeout=2.0)
                writer.write(encode({"type": "command", "id": "ping-1", "name": "ping", "args": {}}))
                await writer.drain()
                while True:
                    line = await asyncio.wait_for(reader.readline(), timeout=3.0)
                    if not line:
                        break
                    message = json.loads(line.decode("utf-8"))
                    if message.get("id") == "ping-1":
                        result["ping"] = message
                        break
                writer.write(encode({"type": "command", "id": "stop-1", "name": "stop", "args": {}}))
                await writer.drain()
                while True:
                    line = await asyncio.wait_for(reader.readline(), timeout=3.0)
                    if not line:
                        break
                    message = json.loads(line.decode("utf-8"))
                    if message.get("id") == "stop-1":
                        result["stop"] = message
                        break
            finally:
                writer.close()

        sink_server = await asyncio.start_server(sink, "127.0.0.1", 0)
        sink_port = sink_server.sockets[0].getsockname()[1]
        c2_server = await asyncio.start_server(c2_handler, "127.0.0.1", 0)
        c2_port = c2_server.sockets[0].getsockname()[1]
        try:
            with redirect_stdout(io.StringIO()):
                code = await asyncio.wait_for(
                    lab_agent.run("127.0.0.1", c2_port, "zombie-test", ""),
                    timeout=8.0,
                )
            self.assertEqual(code, 0)
            self.assertEqual(result.get("ping", {}).get("data", {}).get("pong"), True)
            self.assertEqual(result.get("stop", {}).get("status"), "ok")
        finally:
            c2_server.close()
            sink_server.close()
            for task in sink_tasks + c2_tasks:
                task.cancel()
            pending = sink_tasks + c2_tasks
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            await c2_server.wait_closed()
            await sink_server.wait_closed()

    async def test_bye_de_expulsion_termina_limpio(self):
        async def c2_handler(reader, writer):
            try:
                await reader.readline()
                writer.write(encode({"type": "bye", "reason": "kicked"}))
                await writer.drain()
            finally:
                writer.close()

        server = await asyncio.start_server(c2_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with redirect_stdout(io.StringIO()):
                code = await asyncio.wait_for(
                    lab_agent.run("127.0.0.1", port, "zombie-test", ""),
                    timeout=5.0,
                )
            self.assertEqual(code, 0)
        finally:
            server.close()
            await server.wait_closed()

    async def test_rechazo_de_autenticacion_no_reconecta(self):
        async def c2_handler(reader, writer):
            try:
                await reader.readline()
                writer.write(
                    encode(
                        {
                            "type": "error",
                            "code": "auth",
                            "status": "error",
                            "error": "secreto invalido",
                        }
                    )
                )
                await writer.drain()
            finally:
                writer.close()

        server = await asyncio.start_server(c2_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with redirect_stdout(io.StringIO()):
                code = await asyncio.wait_for(
                    lab_agent.run("127.0.0.1", port, "zombie-test", "mala"),
                    timeout=5.0,
                )
            self.assertEqual(code, 0)
        finally:
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
