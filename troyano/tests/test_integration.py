"""Pruebas de integración de la sesión TCP con el C2."""
from __future__ import annotations

import asyncio
import contextlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.c2_client import EXIT_STOP, receive_messages
from src.commands import handle_command
from src.protocol import decode_message, encode_message


async def _echo_handlers():
    """Devuelve helpers de sesión que registran los frames enviados."""
    sent = []

    async def send_message(message):
        sent.append(message)

    async def start_load(message):
        sent.append(
            {
                "type": "result",
                "id": message.get("id"),
                "status": "error",
                "data": {"error": "sin carga en esta prueba"},
            }
        )

    async def stop_load():
        pass

    return sent, send_message, start_load, stop_load


async def _safe_readline(reader, timeout=2):
    """Lee una línea tolerando cierre de la conexión y timeouts."""
    try:
        return await asyncio.wait_for(reader.readline(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError, OSError):
        return b""


async def _open_session(handler):
    """Levanta un servidor local, abre una sesión y devuelve (reader, writer, server)."""
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    await server.start_serving()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    return reader, writer, server


async def _close_session(writer, server):
    with contextlib.suppress(Exception):
        writer.close()
        await writer.wait_closed()
    server.close()
    await server.wait_closed()


class TestIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_ping_info_echo_generan_resultado_con_mismo_id(self):
        sent, send_message, start_load, stop_load = await _echo_handlers()

        async def handler(reader, writer):
            try:
                for name, command_id in (
                    ("ping", "p-1"),
                    ("info", "i-1"),
                    ("echo", "e-1"),
                ):
                    writer.write(
                        encode_message(
                            {
                                "type": "command",
                                "id": command_id,
                                "name": name,
                                "args": {"text": "hola"} if name == "echo" else {},
                            }
                        )
                    )
                    await writer.drain()
                for _ in range(3):
                    if not await _safe_readline(reader):
                        break
            finally:
                with contextlib.suppress(Exception):
                    writer.close()
                    await writer.wait_closed()

        reader, writer, server = await _open_session(handler)
        try:
            await receive_messages(
                reader,
                writer,
                send_message,
                start_load,
                stop_load,
            )
            self.assertEqual(
                [(item["id"], item["status"]) for item in sent],
                [("p-1", "ok"), ("i-1", "ok"), ("e-1", "ok")],
            )
            self.assertIn("hostname", sent[1]["data"])
            self.assertEqual(sent[2]["data"]["text"], "hola")
        finally:
            await _close_session(writer, server)

    async def test_stop_cierra_la_sesion_sin_reconectar(self):
        sent, send_message, start_load, stop_load = await _echo_handlers()

        async def handler(reader, writer):
            try:
                writer.write(
                    encode_message(
                        {"type": "command", "id": "s-1", "name": "stop", "args": {}}
                    )
                )
                await writer.drain()
                await _safe_readline(reader)
            finally:
                with contextlib.suppress(Exception):
                    writer.close()
                    await writer.wait_closed()

        reader, writer, server = await _open_session(handler)
        try:
            code = await receive_messages(
                reader,
                writer,
                send_message,
                start_load,
                stop_load,
            )
        finally:
            await _close_session(writer, server)

        self.assertEqual(code, EXIT_STOP)
        self.assertTrue(sent[0]["data"]["stopping"])

    async def test_bye_cierra_la_sesion(self):
        _, send_message, start_load, stop_load = await _echo_handlers()

        async def handler(reader, writer):
            try:
                writer.write(encode_message({"type": "bye", "reason": "kicked"}))
                await writer.drain()
                await asyncio.sleep(0.2)
            finally:
                with contextlib.suppress(Exception):
                    writer.close()
                    await writer.wait_closed()

        reader, writer, server = await _open_session(handler)
        try:
            code = await receive_messages(
                reader,
                writer,
                send_message,
                start_load,
                stop_load,
            )
        finally:
            await _close_session(writer, server)

        self.assertEqual(code, EXIT_STOP)

    async def test_comunicacion_cliente_servidor(self):
        responses = []

        async def server_handler(reader, writer):
            try:
                writer.write(
                    encode_message(
                        {
                            "type": "command",
                            "id": "test-001",
                            "name": "ping",
                            "args": {},
                        }
                    )
                )
                await writer.drain()
                line = await _safe_readline(reader, timeout=5)
                if line:
                    responses.append(decode_message(line))
            finally:
                with contextlib.suppress(Exception):
                    writer.close()
                    await writer.wait_closed()

        reader, writer, server = await _open_session(server_handler)
        try:
            line = await _safe_readline(reader, timeout=5)
            command = decode_message(line)
            response = handle_command(command)
            writer.write(encode_message(response))
            await writer.drain()
            await asyncio.sleep(0.1)
        finally:
            await _close_session(writer, server)

        self.assertEqual(len(responses), 1)
        response = responses[0]
        self.assertEqual(response["id"], "test-001")
        self.assertEqual(response["status"], "ok")
        self.assertTrue(response["data"]["pong"])


if __name__ == "__main__":
    unittest.main()
