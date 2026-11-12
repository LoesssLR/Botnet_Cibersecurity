"""Servidor TCP mínimo para pruebas manuales del agente."""
from __future__ import annotations

import asyncio
import json

HOST = "127.0.0.1"
PORT = 9000


async def handle_client(reader, writer):
    print("Cliente conectado")
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=10)
        message = json.loads(line.decode("utf-8"))
        print("Mensaje recibido:", message)

        response = {
            "type": "result",
            "id": "local-001",
            "status": "ok",
            "data": {"connected": True},
        }
        writer.write((json.dumps(response) + "\n").encode("utf-8"))
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def main():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"Servidor de pruebas: {HOST}:{PORT}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
